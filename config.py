"""
Global configuration for the MUGEN-compatible engine.
Designed to run on low-spec hardware without dedicated GPU.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import json
import os


@dataclass
class VideoConfig:
    """Video/rendering settings optimized for low-end hardware."""
    width: int = 640
    height: int = 480
    fullscreen: bool = False
    vsync: bool = True
    fps_limit: int = 60
    render_scale: float = 1.0  # Can reduce for performance
    use_software_renderer: bool = True  # No GPU required
    show_fps: bool = False
    
    # MUGEN compatibility
    game_width: int = 320  # Internal game resolution (MUGEN standard)
    game_height: int = 240
    localcoord: Tuple[int, int] = (320, 240)


@dataclass
class AudioConfig:
    """Audio settings."""
    master_volume: float = 1.0
    bgm_volume: float = 0.7
    sfx_volume: float = 1.0
    voice_volume: float = 1.0
    sample_rate: int = 44100
    channels: int = 32  # Mixer channels for simultaneous sounds
    buffer_size: int = 1024


@dataclass
class GameplayConfig:
    """Gameplay settings."""
    rounds_to_win: int = 2
    round_time: int = 99  # Seconds, 0 for infinite
    life: int = 1000  # Starting life
    team_life_share: bool = False
    
    # AI settings
    default_ai_level: int = 4  # 1-8 scale
    
    # Speed settings (MUGEN compatibility)
    game_speed: int = 0  # -9 to +9
    
    # Draw games
    max_draw_games: int = 1


@dataclass
class InputConfig:
    """Input/control settings."""
    # Player 1 default keyboard mapping
    p1_keys: Dict[str, int] = field(default_factory=lambda: {
        'up': 119,      # W
        'down': 115,    # S
        'left': 97,     # A
        'right': 100,   # D
        'a': 117,       # U
        'b': 105,       # I
        'c': 111,       # O
        'x': 106,       # J
        'y': 107,       # K
        'z': 108,       # L
        'start': 13,    # Enter
        'back': 27,     # Escape
    })
    
    # Player 2 default keyboard mapping
    p2_keys: Dict[str, int] = field(default_factory=lambda: {
        'up': 1073741906,     # Arrow Up
        'down': 1073741905,   # Arrow Down
        'left': 1073741904,   # Arrow Left
        'right': 1073741903,  # Arrow Right
        'a': 1073741922,      # Numpad 4
        'b': 1073741923,      # Numpad 5
        'c': 1073741924,      # Numpad 6
        'x': 1073741919,      # Numpad 1
        'y': 1073741920,      # Numpad 2
        'z': 1073741921,      # Numpad 3
        'start': 1073741922,  # Numpad Enter
        'back': 8,            # Backspace
    })
    
    input_buffer_frames: int = 15  # For motion inputs
    simultaneous_press_window: int = 3  # Frames


@dataclass
class NetworkConfig:
    """Network/online play settings."""
    default_port: int = 7500
    input_delay: int = 2  # Frames of input delay for netplay
    rollback_frames: int = 7  # Max rollback frames
    timeout_ms: int = 10000
    spectator_enabled: bool = True


@dataclass 
class PathConfig:
    """Content paths."""
    base_path: Path = field(default_factory=lambda: Path('.'))
    chars_path: Path = field(default_factory=lambda: Path('data/chars'))
    stages_path: Path = field(default_factory=lambda: Path('data/stages'))
    sound_path: Path = field(default_factory=lambda: Path('data/sound'))
    font_path: Path = field(default_factory=lambda: Path('data/font'))
    data_path: Path = field(default_factory=lambda: Path('data/data'))
    save_path: Path = field(default_factory=lambda: Path('save'))


class Config:
    """Main configuration manager."""
    
    def __init__(self, config_file: Optional[str] = None):
        self.video = VideoConfig()
        self.audio = AudioConfig()
        self.gameplay = GameplayConfig()
        self.input = InputConfig()
        self.network = NetworkConfig()
        self.paths = PathConfig()
        
        if config_file and os.path.exists(config_file):
            self.load(config_file)
    
    def load(self, filepath: str) -> None:
        """Load configuration from JSON file."""
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        for section_name, section_data in data.items():
            if hasattr(self, section_name):
                section = getattr(self, section_name)
                for key, value in section_data.items():
                    if hasattr(section, key):
                        setattr(section, key, value)
    
    def save(self, filepath: str) -> None:
        """Save configuration to JSON file."""
        data = {
            'video': self.video.__dict__,
            'audio': self.audio.__dict__,
            'gameplay': self.gameplay.__dict__,
            'input': {k: v for k, v in self.input.__dict__.items()},
            'network': self.network.__dict__,
        }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, default=str)


# Global config instance
CONFIG = Config()
