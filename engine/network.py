"""
Network module for online multiplayer.
Implements delay-based netcode with optional rollback.
"""

import asyncio
import socket
import struct
import time
import hashlib
from enum import Enum, auto
from typing import Optional, Dict, List, Tuple, Callable, Any
from dataclasses import dataclass, field
from collections import deque
import threading

from engine.input_handler import InputFrame, Button


class NetState(Enum):
    """Network connection states."""
    DISCONNECTED = auto()
    CONNECTING = auto()
    SYNCHRONIZING = auto()
    CONNECTED = auto()
    DESYNCED = auto()


class MessageType(Enum):
    """Network message types."""
    PING = 1
    PONG = 2
    INPUT = 3
    SYNC_REQUEST = 4
    SYNC_RESPONSE = 5
    GAME_STATE = 6
    SPECTATE_REQUEST = 7
    SPECTATE_DATA = 8
    CHAT = 9
    DISCONNECT = 10


@dataclass
class NetInput:
    """Network input packet."""
    frame: int
    buttons: int
    checksum: int = 0  # For desync detection


@dataclass
class InputBuffer:
    """Buffer for storing and predicting inputs."""
    local_inputs: Dict[int, NetInput] = field(default_factory=dict)
    remote_inputs: Dict[int, NetInput] = field(default_factory=dict)
    predicted_inputs: Dict[int, NetInput] = field(default_factory=dict)
    
    last_confirmed_frame: int = 0
    current_frame: int = 0


@dataclass
class NetStats:
    """Network statistics."""
    ping_ms: float = 0.0
    jitter_ms: float = 0.0
    packet_loss: float = 0.0
    rollback_frames: int = 0
    
    _ping_samples: List[float] = field(default_factory=list)


class NetworkManager:
    """
    Manages network connections for online play.
    Supports both hosting and joining games.
    """
    
    PACKET_MAGIC = b'PMUG'  # PyMugen
    VERSION = 1
    
    def __init__(self, port: int = 7500):
        self.port = port
        self.state = NetState.DISCONNECTED
        
        self.socket: Optional[socket.socket] = None
        self.remote_addr: Optional[Tuple[str, int]] = None
        
        self.is_host = False
        self.local_player = 0  # 0 = P1, 1 = P2
        
        self.input_buffer = InputBuffer()
        self.stats = NetStats()
        
        # Input delay (in frames)
        self.input_delay = 2
        
        # Callbacks
        self.on_connected: Optional[Callable] = None
        self.on_disconnected: Optional[Callable] = None
        self.on_input_received: Optional[Callable] = None
        
        # Threading
        self._running = False
        self._recv_thread: Optional[threading.Thread] = None
        self._send_queue: deque = deque()
        
        # Sync
        self._sync_rng_seed: int = 0
        self._game_state_hash: int = 0
    
    def host(self, port: Optional[int] = None) -> bool:
        """Start hosting a game."""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind(('', port or self.port))
            self.socket.setblocking(False)
            
            self.is_host = True
            self.local_player = 0  # Host is P1
            self.state = NetState.CONNECTING
            
            self._running = True
            self._recv_thread = threading.Thread(target=self._receive_loop)
            self._recv_thread.daemon = True
            self._recv_thread.start()
            
            print(f"Hosting on port {port or self.port}")
            return True
            
        except Exception as e:
            print(f"Failed to host: {e}")
            return False
    
    def join(self, host: str, port: int) -> bool:
        """Join a hosted game."""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setblocking(False)
            
            self.remote_addr = (host, port)
            self.is_host = False
            self.local_player = 1  # Joiner is P2
            self.state = NetState.CONNECTING
            
            self._running = True
            self._recv_thread = threading.Thread(target=self._receive_loop)
            self._recv_thread.daemon = True
            self._recv_thread.start()
            
            # Send connection request
            self._send_sync_request()
            
            print(f"Connecting to {host}:{port}")
            return True
            
        except Exception as e:
            print(f"Failed to join: {e}")
            return False
    
    def disconnect(self) -> None:
        """Disconnect from the current game."""
        self._running = False
        
        if self.socket:
            try:
                # Send disconnect message
                self._send_message(MessageType.DISCONNECT, b'')
            except:
                pass
            
            self.socket.close()
            self.socket = None
        
        self.state = NetState.DISCONNECTED
        self.remote_addr = None
        
        if self.on_disconnected:
            self.on_disconnected()
    
    def send_input(self, frame: int, input_frame: InputFrame) -> None:
        """Send local input to remote player."""
        # Store locally
        net_input = NetInput(
            frame=frame,
            buttons=int(input_frame.buttons),
            checksum=self._game_state_hash
        )
        self.input_buffer.local_inputs[frame] = net_input
        
        # Build packet
        data = struct.pack('<IIi', frame, net_input.buttons, net_input.checksum)
        self._send_message(MessageType.INPUT, data)
    
    def get_remote_input(self, frame: int) -> Optional[InputFrame]:
        """Get remote input for a frame (with prediction if needed)."""
        # Check if we have confirmed input
        if frame in self.input_buffer.remote_inputs:
            net_input = self.input_buffer.remote_inputs[frame]
            return self._net_to_frame(net_input)
        
        # Predict based on last known input
        if self.input_buffer.remote_inputs:
            last_frame = max(self.input_buffer.remote_inputs.keys())
            last_input = self.input_buffer.remote_inputs[last_frame]
            
            # Simple prediction: repeat last input
            predicted = NetInput(
                frame=frame,
                buttons=last_input.buttons
            )
            self.input_buffer.predicted_inputs[frame] = predicted
            return self._net_to_frame(predicted)
        
        # No input available
        return InputFrame()
    
    def _net_to_frame(self, net_input: NetInput) -> InputFrame:
        """Convert network input to InputFrame."""
        return InputFrame(
            buttons=Button(net_input.buttons),
            buttons_pressed=Button.NONE,  # Calculated by input handler
            buttons_released=Button.NONE
        )
    
    def update(self) -> None:
        """Update network state."""
        if self.state == NetState.DISCONNECTED:
            return
        
        # Process send queue
        while self._send_queue:
            msg_type, data = self._send_queue.popleft()
            self._send_raw(msg_type, data)
        
        # Update ping
        if self.state == NetState.CONNECTED:
            self._send_ping()
    
    def _send_message(self, msg_type: MessageType, data: bytes) -> None:
        """Queue a message to send."""
        self._send_queue.append((msg_type, data))
    
    def _send_raw(self, msg_type: MessageType, data: bytes) -> None:
        """Send a message immediately."""
        if not self.socket or not self.remote_addr:
            return
        
        # Build packet: magic + version + type + length + data
        packet = (
            self.PACKET_MAGIC +
            struct.pack('<BBI', self.VERSION, msg_type.value, len(data)) +
            data
        )
        
        try:
            self.socket.sendto(packet, self.remote_addr)
        except Exception as e:
            print(f"Send error: {e}")
    
    def _receive_loop(self) -> None:
        """Background thread for receiving packets."""
        while self._running:
            try:
                if self.socket:
                    self.socket.settimeout(0.01)
                    try:
                        data, addr = self.socket.recvfrom(1024)
                        self._handle_packet(data, addr)
                    except socket.timeout:
                        pass
            except Exception as e:
                if self._running:
                    print(f"Receive error: {e}")
            
            time.sleep(0.001)
    
    def _handle_packet(self, data: bytes, addr: Tuple[str, int]) -> None:
        """Handle received packet."""
        if len(data) < 11:  # Minimum packet size
            return
        
        # Verify magic
        if data[:4] != self.PACKET_MAGIC:
            return
        
        version, msg_type, length = struct.unpack('<BBI', data[4:11])
        
        if version != self.VERSION:
            return
        
        payload = data[11:11+length]
        
        # Update remote address if connecting
        if self.state == NetState.CONNECTING and not self.remote_addr:
            self.remote_addr = addr
        
        # Handle message type
        try:
            msg = MessageType(msg_type)
            
            if msg == MessageType.PING:
                self._handle_ping(payload, addr)
            elif msg == MessageType.PONG:
                self._handle_pong(payload)
            elif msg == MessageType.INPUT:
                self._handle_input(payload)
            elif msg == MessageType.SYNC_REQUEST:
                self._handle_sync_request(payload, addr)
            elif msg == MessageType.SYNC_RESPONSE:
                self._handle_sync_response(payload)
            elif msg == MessageType.DISCONNECT:
                self._handle_disconnect()
                
        except ValueError:
            pass  # Unknown message type
    
    def _send_ping(self) -> None:
        """Send ping message."""
        timestamp = struct.pack('<d', time.time())
        self._send_message(MessageType.PING, timestamp)
    
    def _handle_ping(self, data: bytes, addr: Tuple[str, int]) -> None:
        """Handle ping message, send pong."""
        self._send_raw(MessageType.PONG, data)
    
    def _handle_pong(self, data: bytes) -> None:
        """Handle pong message, calculate RTT."""
        if len(data) >= 8:
            sent_time = struct.unpack('<d', data[:8])[0]
            rtt = (time.time() - sent_time) * 1000  # ms
            
            self.stats._ping_samples.append(rtt)
            if len(self.stats._ping_samples) > 30:
                self.stats._ping_samples.pop(0)
            
            self.stats.ping_ms = sum(self.stats._ping_samples) / len(self.stats._ping_samples)
    
    def _handle_input(self, data: bytes) -> None:
        """Handle received input."""
        if len(data) >= 12:
            frame, buttons, checksum = struct.unpack('<IIi', data[:12])
            
            net_input = NetInput(frame=frame, buttons=buttons, checksum=checksum)
            self.input_buffer.remote_inputs[frame] = net_input
            
            # Check for rollback
            if frame in self.input_buffer.predicted_inputs:
                predicted = self.input_buffer.predicted_inputs[frame]
                if predicted.buttons != buttons:
                    # Misprediction! Need rollback
                    self.stats.rollback_frames += 1
            
            if self.on_input_received:
                self.on_input_received(frame, net_input)
    
    def _send_sync_request(self) -> None:
        """Send synchronization request."""
        # Include character/stage selection info
        self._send_message(MessageType.SYNC_REQUEST, b'')
    
    def _handle_sync_request(self, data: bytes, addr: Tuple[str, int]) -> None:
        """Handle sync request from joining player."""
        self.remote_addr = addr
        
        # Generate sync seed
        self._sync_rng_seed = int(time.time() * 1000) & 0xFFFFFFFF
        
        response = struct.pack('<I', self._sync_rng_seed)
        self._send_raw(MessageType.SYNC_RESPONSE, response)
        
        self.state = NetState.CONNECTED
        
        if self.on_connected:
            self.on_connected()
    
    def _handle_sync_response(self, data: bytes) -> None:
        """Handle sync response from host."""
        if len(data) >= 4:
            self._sync_rng_seed = struct.unpack('<I', data[:4])[0]
        
        self.state = NetState.CONNECTED
        
        if self.on_connected:
            self.on_connected()
    
    def _handle_disconnect(self) -> None:
        """Handle disconnect message."""
        self.state = NetState.DISCONNECTED
        
        if self.on_disconnected:
            self.on_disconnected()
    
    def set_game_state_hash(self, state_hash: int) -> None:
        """Set current game state hash for desync detection."""
        self._game_state_hash = state_hash
    
    def check_desync(self, frame: int) -> bool:
        """Check if game states are desynced."""
        if frame not in self.input_buffer.local_inputs:
            return False
        if frame not in self.input_buffer.remote_inputs:
            return False
        
        local = self.input_buffer.local_inputs[frame]
        remote = self.input_buffer.remote_inputs[frame]
        
        # Compare checksums
        if local.checksum != 0 and remote.checksum != 0:
            if local.checksum != remote.checksum:
                self.state = NetState.DESYNCED
                return True
        
        return False
