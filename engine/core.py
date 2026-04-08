"""
Core game engine - main loop, state management, and subsystem coordination.
Optimized for low-spec hardware with software rendering.
"""

import pygame
import time
from enum import Enum, auto
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass
from config import CONFIG


class GameState(Enum):
    """Game state machine states."""
    INIT = auto()
    LOGO = auto()
    TITLE = auto()
    MAIN_MENU = auto()
    CHARACTER_SELECT = auto()
    STAGE_SELECT = auto()
    VS_SCREEN = auto()
    LOADING = auto()
    FIGHT = auto()
    ROUND_END = auto()
    MATCH_END = auto()
    CONTINUE = auto()
    GAME_OVER = auto()
    CREDITS = auto()
    OPTIONS = auto()
    REPLAY = auto()
    NETWORK_LOBBY = auto()


@dataclass
class GameTime:
    """Timing information for the current frame."""
    delta_time: float = 0.0  # Seconds since last frame
    total_time: float = 0.0  # Total time since start
    frame_count: int = 0
    fps: float = 60.0
    tick: int = 0  # MUGEN-style tick counter (increments each frame)


class Engine:
    """
    Main game engine class.
    Manages the game loop, state transitions, and coordinates all subsystems.
    """
    
    def __init__(self):
        self.running = False
        self.state = GameState.INIT
        self.previous_state = GameState.INIT
        self.time = GameTime()
        
        # Subsystems (initialized in init())
        self.renderer = None
        self.input_handler = None
        self.audio_manager = None
        self.content_manager = None
        
        # State handlers
        self._state_handlers: Dict[GameState, 'StateHandler'] = {}
        self._state_data: Dict[str, Any] = {}
        
        # Callbacks
        self._on_state_change: Optional[Callable] = None
        
        # Frame timing
        self._target_fps = CONFIG.video.fps_limit
        self._frame_time = 1.0 / self._target_fps
        self._last_frame_time = 0.0
        self._fps_samples = []
        
    def init(self) -> bool:
        """Initialize all engine subsystems."""
        try:
            # Initialize Pygame with software rendering for compatibility
            pygame.init()
            
            # Set up display
            flags = pygame.SWSURFACE  # Software surface for compatibility
            if CONFIG.video.fullscreen:
                flags |= pygame.FULLSCREEN
            
            self.screen = pygame.display.set_mode(
                (CONFIG.video.width, CONFIG.video.height),
                flags
            )
            pygame.display.set_caption("PyMugen Engine")
            
            # Create internal game surface at MUGEN resolution
            self.game_surface = pygame.Surface(
                (CONFIG.video.game_width, CONFIG.video.game_height)
            )
            
            # Initialize subsystems
            from engine.renderer import Renderer
            from engine.input_handler import InputHandler
            from engine.audio_manager import AudioManager
            
            self.renderer = Renderer(self.screen, self.game_surface)
            self.input_handler = InputHandler()
            self.audio_manager = AudioManager()
            
            # Initialize content manager
            from mugen.content_manager import ContentManager
            self.content_manager = ContentManager()
            
            self.running = True
            self._last_frame_time = time.perf_counter()
            
            return True
            
        except Exception as e:
            print(f"Engine initialization failed: {e}")
            return False
    
    def shutdown(self) -> None:
        """Clean shutdown of all subsystems."""
        self.running = False
        
        if self.audio_manager:
            self.audio_manager.shutdown()
        
        pygame.quit()
    
    def register_state_handler(self, state: GameState, handler: 'StateHandler') -> None:
        """Register a handler for a game state."""
        self._state_handlers[state] = handler
        handler.engine = self
    
    def change_state(self, new_state: GameState, data: Optional[Dict[str, Any]] = None) -> None:
        """Transition to a new game state."""
        # Exit current state
        if self.state in self._state_handlers:
            self._state_handlers[self.state].on_exit()
        
        self.previous_state = self.state
        self.state = new_state
        self._state_data = data or {}
        
        # Enter new state
        if new_state in self._state_handlers:
            self._state_handlers[new_state].on_enter(self._state_data)
        
        if self._on_state_change:
            self._on_state_change(self.previous_state, new_state)
    
    def run(self) -> None:
        """Main game loop."""
        while self.running:
            self._update_timing()
            self._process_events()
            self._update()
            self._render()
            self._limit_framerate()
    
    def _update_timing(self) -> None:
        """Update timing information."""
        current_time = time.perf_counter()
        self.time.delta_time = current_time - self._last_frame_time
        self._last_frame_time = current_time
        self.time.total_time += self.time.delta_time
        self.time.frame_count += 1
        self.time.tick += 1
        
        # Calculate FPS
        self._fps_samples.append(1.0 / max(self.time.delta_time, 0.001))
        if len(self._fps_samples) > 60:
            self._fps_samples.pop(0)
        self.time.fps = sum(self._fps_samples) / len(self._fps_samples)
    
    def _process_events(self) -> None:
        """Process pygame events."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type in (pygame.KEYDOWN, pygame.KEYUP):
                self.input_handler.process_key_event(event)
            elif event.type in (pygame.JOYBUTTONDOWN, pygame.JOYBUTTONUP,
                              pygame.JOYAXISMOTION, pygame.JOYHATMOTION):
                self.input_handler.process_joy_event(event)
    
    def _update(self) -> None:
        """Update game logic."""
        # Update input
        self.input_handler.update()
        
        # Update current state
        if self.state in self._state_handlers:
            self._state_handlers[self.state].update(self.time)
    
    def _render(self) -> None:
        """Render the current frame."""
        # Clear game surface
        self.game_surface.fill((0, 0, 0))
        
        # Render current state
        if self.state in self._state_handlers:
            self._state_handlers[self.state].render(self.renderer)
        
        # Scale game surface to screen
        scaled = pygame.transform.scale(
            self.game_surface,
            (CONFIG.video.width, CONFIG.video.height)
        )
        self.screen.blit(scaled, (0, 0))
        
        # Show FPS if enabled
        if CONFIG.video.show_fps:
            self._render_fps()
        
        pygame.display.flip()
    
    def _render_fps(self) -> None:
        """Render FPS counter."""
        font = pygame.font.SysFont('monospace', 16)
        fps_text = font.render(f"FPS: {self.time.fps:.1f}", True, (255, 255, 0))
        self.screen.blit(fps_text, (5, 5))
    
    def _limit_framerate(self) -> None:
        """Limit framerate to target FPS."""
        elapsed = time.perf_counter() - self._last_frame_time
        sleep_time = self._frame_time - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)


class StateHandler:
    """Base class for game state handlers."""
    
    def __init__(self):
        self.engine: Optional[Engine] = None
    
    def on_enter(self, data: Dict[str, Any]) -> None:
        """Called when entering this state."""
        pass
    
    def on_exit(self) -> None:
        """Called when leaving this state."""
        pass
    
    def update(self, time: GameTime) -> None:
        """Update state logic."""
        pass
    
    def render(self, renderer: 'Renderer') -> None:
        """Render state visuals."""
        pass
