"""
Input handling for keyboard, gamepad, and network inputs.
Implements MUGEN-style command input detection with buffering.
"""

import pygame
from enum import IntFlag, auto
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, field
from collections import deque
from config import CONFIG


class Button(IntFlag):
    """Button flags matching MUGEN button constants."""
    NONE = 0
    UP = auto()
    DOWN = auto()
    LEFT = auto()
    RIGHT = auto()
    A = auto()      # Light Punch
    B = auto()      # Medium Punch
    C = auto()      # Hard Punch
    X = auto()      # Light Kick
    Y = auto()      # Medium Kick
    Z = auto()      # Hard Kick
    START = auto()
    BACK = auto()
    
    # Derived directions
    UP_LEFT = UP | LEFT
    UP_RIGHT = UP | RIGHT
    DOWN_LEFT = DOWN | LEFT
    DOWN_RIGHT = DOWN | RIGHT
    
    # Button release flags (for command detection)
    RELEASE_A = auto()
    RELEASE_B = auto()
    RELEASE_C = auto()
    RELEASE_X = auto()
    RELEASE_Y = auto()
    RELEASE_Z = auto()


@dataclass
class InputFrame:
    """Input state for a single frame."""
    buttons: Button = Button.NONE
    buttons_pressed: Button = Button.NONE   # Just pressed this frame
    buttons_released: Button = Button.NONE  # Just released this frame
    tick: int = 0


@dataclass
class CommandDef:
    """Definition of a command (special move input)."""
    name: str
    sequence: List[Tuple[Button, int]]  # (button_requirement, max_time)
    buffer_time: int = 15  # Frames to complete command
    
    # MUGEN command flags
    hold_dir: bool = False  # Hold direction requirement


class InputBuffer:
    """
    Circular buffer for input history.
    Used for detecting motion inputs (quarter circles, etc.)
    """
    
    def __init__(self, size: int = 60):
        self.buffer: deque[InputFrame] = deque(maxlen=size)
        self.current_tick = 0
    
    def add(self, frame: InputFrame) -> None:
        """Add a frame to the buffer."""
        frame.tick = self.current_tick
        self.buffer.append(frame)
        self.current_tick += 1
    
    def get_recent(self, frames: int) -> List[InputFrame]:
        """Get the most recent N frames."""
        return list(self.buffer)[-frames:]
    
    def check_sequence(self, sequence: List[Tuple[Button, int]], 
                       buffer_time: int) -> bool:
        """
        Check if a button sequence was performed within the buffer time.
        Returns True if sequence was detected.
        """
        if len(self.buffer) < len(sequence):
            return False
        
        recent = self.get_recent(buffer_time)
        if not recent:
            return False
        
        seq_idx = 0
        frames_since_last = 0
        
        for frame in recent:
            if seq_idx >= len(sequence):
                break
            
            required_buttons, max_gap = sequence[seq_idx]
            
            # Check if this frame matches the requirement
            if (frame.buttons_pressed & required_buttons) == required_buttons:
                if frames_since_last <= max_gap or seq_idx == 0:
                    seq_idx += 1
                    frames_since_last = 0
                else:
                    # Gap too large, reset
                    seq_idx = 0
                    frames_since_last = 0
            else:
                frames_since_last += 1
        
        return seq_idx >= len(sequence)


class PlayerInput:
    """Input state for a single player."""
    
    def __init__(self, player_id: int):
        self.player_id = player_id
        self.buffer = InputBuffer()
        self.current = InputFrame()
        self.previous = InputFrame()
        
        # Key mappings
        if player_id == 0:
            self.key_map = CONFIG.input.p1_keys.copy()
        else:
            self.key_map = CONFIG.input.p2_keys.copy()
        
        # Reverse map for quick lookup
        self._reverse_map: Dict[int, str] = {v: k for k, v in self.key_map.items()}
        
        # Currently held keys
        self._held_keys: Set[int] = set()
        
        # Gamepad
        self.joy_id: Optional[int] = None
        self.joy_deadzone: float = 0.3
        
        # Registered commands
        self.commands: Dict[str, CommandDef] = {}
        self._active_commands: Set[str] = set()
    
    def process_key_down(self, key: int) -> None:
        """Process a key press."""
        self._held_keys.add(key)
    
    def process_key_up(self, key: int) -> None:
        """Process a key release."""
        self._held_keys.discard(key)
    
    def update(self) -> None:
        """Update input state for this frame."""
        self.previous = self.current
        
        # Build current button state from held keys
        buttons = Button.NONE
        
        for key in self._held_keys:
            if key not in self._reverse_map:
                continue
            
            button_name = self._reverse_map[key]
            button_map = {
                'up': Button.UP,
                'down': Button.DOWN,
                'left': Button.LEFT,
                'right': Button.RIGHT,
                'a': Button.A,
                'b': Button.B,
                'c': Button.C,
                'x': Button.X,
                'y': Button.Y,
                'z': Button.Z,
                'start': Button.START,
                'back': Button.BACK,
            }
            
            if button_name in button_map:
                buttons |= button_map[button_name]
        
        # Calculate pressed/released
        pressed = buttons & ~self.previous.buttons
        released = self.previous.buttons & ~buttons
        
        self.current = InputFrame(
            buttons=buttons,
            buttons_pressed=pressed,
            buttons_released=released
        )
        
        self.buffer.add(self.current)
        
        # Check commands
        self._check_commands()
    
    def register_command(self, command: CommandDef) -> None:
        """Register a command for detection."""
        self.commands[command.name] = command
    
    def _check_commands(self) -> None:
        """Check all registered commands."""
        self._active_commands.clear()
        
        for name, cmd in self.commands.items():
            if self.buffer.check_sequence(cmd.sequence, cmd.buffer_time):
                self._active_commands.add(name)
    
    def command_active(self, name: str) -> bool:
        """Check if a command is currently active."""
        return name in self._active_commands
    
    def button_held(self, button: Button) -> bool:
        """Check if button(s) are currently held."""
        return (self.current.buttons & button) == button
    
    def button_pressed(self, button: Button) -> bool:
        """Check if button(s) were just pressed."""
        return (self.current.buttons_pressed & button) == button
    
    def button_released(self, button: Button) -> bool:
        """Check if button(s) were just released."""
        return (self.current.buttons_released & button) == button


class InputHandler:
    """
    Main input handler managing all player inputs.
    """
    
    def __init__(self):
        # Initialize joystick subsystem
        pygame.joystick.init()
        
        # Player inputs
        self.players: List[PlayerInput] = [
            PlayerInput(0),
            PlayerInput(1),
        ]
        
        # Detect and assign joysticks
        self._detect_joysticks()
        
        # Global inputs (menu navigation, etc.)
        self.menu_input = PlayerInput(-1)
    
    def _detect_joysticks(self) -> None:
        """Detect and assign joysticks to players."""
        joy_count = pygame.joystick.get_count()
        
        for i in range(min(joy_count, 2)):
            joy = pygame.joystick.Joystick(i)
            joy.init()
            self.players[i].joy_id = i
            print(f"Player {i+1} joystick: {joy.get_name()}")
    
    def process_key_event(self, event: pygame.event.Event) -> None:
        """Process a keyboard event."""
        key = event.key
        
        # Distribute to appropriate player
        for player in self.players:
            if key in player._reverse_map:
                if event.type == pygame.KEYDOWN:
                    player.process_key_down(key)
                else:
                    player.process_key_up(key)
                break
    
    def process_joy_event(self, event: pygame.event.Event) -> None:
        """Process a joystick event."""
        joy_id = event.joy if hasattr(event, 'joy') else None
        
        for player in self.players:
            if player.joy_id == joy_id:
                # Handle joystick input
                # (Simplified - full implementation would map axes/buttons)
                pass
    
    def update(self) -> None:
        """Update all player inputs."""
        for player in self.players:
            player.update()
        
        self.menu_input.update()
    
    def get_player(self, player_id: int) -> PlayerInput:
        """Get input for a specific player."""
        return self.players[player_id]


# Standard MUGEN command definitions
def create_standard_commands() -> List[CommandDef]:
    """Create standard motion commands used in fighting games."""
    return [
        # Quarter circle forward + punch (fireball motion)
        CommandDef(
            name="QCF_P",
            sequence=[
                (Button.DOWN, 8),
                (Button.DOWN_RIGHT, 8),
                (Button.RIGHT, 8),
                (Button.A | Button.B | Button.C, 3),  # Any punch
            ],
            buffer_time=20
        ),
        
        # Quarter circle back + punch
        CommandDef(
            name="QCB_P",
            sequence=[
                (Button.DOWN, 8),
                (Button.DOWN_LEFT, 8),
                (Button.LEFT, 8),
                (Button.A | Button.B | Button.C, 3),
            ],
            buffer_time=20
        ),
        
        # Dragon punch motion (forward, down, down-forward + punch)
        CommandDef(
            name="DP_P",
            sequence=[
                (Button.RIGHT, 8),
                (Button.DOWN, 8),
                (Button.DOWN_RIGHT, 8),
                (Button.A | Button.B | Button.C, 3),
            ],
            buffer_time=20
        ),
        
        # Charge back, forward + punch
        CommandDef(
            name="CHARGE_BF_P",
            sequence=[
                (Button.LEFT, 30),  # Hold back for 30 frames
                (Button.RIGHT, 8),
                (Button.A | Button.B | Button.C, 3),
            ],
            buffer_time=45,
            hold_dir=True
        ),
        
        # Super motion: double quarter circle forward + punch
        CommandDef(
            name="2QCF_P",
            sequence=[
                (Button.DOWN, 8),
                (Button.DOWN_RIGHT, 8),
                (Button.RIGHT, 8),
                (Button.DOWN, 8),
                (Button.DOWN_RIGHT, 8),
                (Button.RIGHT, 8),
                (Button.A | Button.B | Button.C, 3),
            ],
            buffer_time=30
        ),
    ]
