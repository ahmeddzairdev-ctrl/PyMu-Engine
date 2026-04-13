"""
MUGEN character loader - parses .def, .cmd, .cns, and .air files.
Handles both WinMUGEN and MUGEN 1.1 formats.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum, auto

from mugen.sprite_loader import SpriteLoader
from mugen.sound_loader import SoundLoader
from mugen.expression_parser import ExpressionParser


class StateType(Enum):
    """MUGEN state types."""
    STANDING = 'S'
    CROUCHING = 'C'
    AIRBORNE = 'A'
    LYING = 'L'
    UNCHANGED = 'U'


class MoveType(Enum):
    """MUGEN move types."""
    IDLE = 'I'
    ATTACK = 'A'
    HIT = 'H'
    UNCHANGED = 'U'


class Physics(Enum):
    """MUGEN physics types."""
    STAND = 'S'
    CROUCH = 'C'
    AIR = 'A'
    NONE = 'N'
    UNCHANGED = 'U'


@dataclass
class AnimationFrame:
    """Single frame of animation."""
    group: int
    index: int
    x_offset: int
    y_offset: int
    duration: int  # Ticks (-1 for infinite)
    flip_h: bool = False
    flip_v: bool = False
    
    # Collision boxes (if defined in .air)
    clsn1: List[Tuple[int, int, int, int]] = field(default_factory=list)  # Attack boxes
    clsn2: List[Tuple[int, int, int, int]] = field(default_factory=list)  # Hit boxes


@dataclass
class Animation:
    """Animation sequence."""
    id: int
    frames: List[AnimationFrame]
    loop_start: int = 0


@dataclass
class CommandInput:
    """Parsed command input requirement."""
    direction: Optional[str] = None  # D, F, B, U, DF, DB, UF, UB
    button: Optional[str] = None     # a, b, c, x, y, z, s
    hold: bool = False               # ~
    release: bool = False            # $
    negate: bool = False             # /
    time: int = 1                    # Number of ticks to hold


@dataclass
class Command:
    """Character command definition."""
    name: str
    inputs: List[CommandInput]
    time: int = 15  # Buffer time
    buffer_time: int = 1


@dataclass
class StateController:
    """MUGEN state controller."""
    type: str
    trigger_all: List[str] = field(default_factory=list)
    triggers: Dict[int, List[str]] = field(default_factory=dict)
    params: Dict[str, Any] = field(default_factory=dict)
    
    # Common controller fields
    persistent: int = 1
    ignore_hitpause: bool = False


@dataclass
class StateDef:
    """MUGEN state definition."""
    number: int
    type: StateType = StateType.STANDING
    movetype: MoveType = MoveType.IDLE
    physics: Physics = Physics.STAND
    anim: Optional[int] = None
    velset: Tuple[Optional[float], Optional[float]] = (None, None)
    ctrl: Optional[int] = None
    poweradd: int = 0
    juggle: int = 0
    facep2: bool = False
    hitdefpersist: bool = False
    movehitpersist: bool = False
    hitcountpersist: bool = False
    sprpriority: int = 0
    
    controllers: List[StateController] = field(default_factory=list)


@dataclass
class CharacterConstants:
    """Character constants from .cns [Data] and [Size] sections."""
    # [Data]
    life: int = 1000
    attack: int = 100
    defence: int = 100
    fall_defence_up: int = 50
    liedown_time: int = 60
    airjuggle: int = 15
    sparkno: int = 2
    guard_sparkno: int = 40
    ko_echo: int = 0
    volume: int = 0
    intpersistindex: int = 60
    floatpersistindex: int = 40
    
    # [Size]
    xscale: float = 1.0
    yscale: float = 1.0
    ground_back: int = 15
    ground_front: int = 16
    air_back: int = 12
    air_front: int = 12
    height: int = 60
    attack_dist: int = 160
    proj_attack_dist: int = 90
    proj_doscale: int = 0
    head_pos: Tuple[int, int] = (-5, -90)
    mid_pos: Tuple[int, int] = (-5, -60)
    shadowoffset: int = 0
    draw_offset: Tuple[int, int] = (0, 0)
    
    # [Velocity]
    walk_fwd: float = 2.4
    walk_back: float = -2.2
    run_fwd: Tuple[float, float] = (4.6, 0.0)
    run_back: Tuple[float, float] = (-4.5, -3.8)
    jump_neu: Tuple[float, float] = (0.0, -8.4)
    jump_back: float = -2.55
    jump_fwd: float = 2.5
    runjump_back: float = -2.55
    runjump_fwd: float = 4.0
    airjump_neu: Tuple[float, float] = (0.0, -8.1)
    airjump_back: float = -2.55
    airjump_fwd: float = 2.5
    
    # [Movement]
    airjump_num: int = 1
    airjump_height: int = 35
    yaccel: float = 0.44
    stand_friction: float = 0.85
    crouch_friction: float = 0.82


class INIParser:
    """
    Parser for MUGEN INI-style configuration files.
    Handles .def, .cns, .cmd, and .air files.
    """
    
    def __init__(self, content: str):
        self.content = content
        self.sections: Dict[str, Dict[str, str]] = {}
        self.section_order: List[str] = []
        self._parse()
    
    def _parse(self) -> None:
        """Parse the INI content."""
        current_section = ""
        current_data: Dict[str, str] = {}
        
        for line in self.content.split('\n'):
            line = line.strip()
            
            # Skip empty lines and comments
            if not line or line.startswith(';'):
                continue
            
            # Remove inline comments
            if ';' in line:
                line = line[:line.index(';')].strip()
            
            # Section header
            if line.startswith('[') and ']' in line:
                # Save previous section
                if current_section:
                    self.sections[current_section] = current_data
                    self.section_order.append(current_section)
                
                current_section = line[1:line.index(']')].lower()
                current_data = {}
                continue
            
            # Key-value pair
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip().lower()
                value = value.strip()
                current_data[key] = value
        
        # Save last section
        if current_section:
            self.sections[current_section] = current_data
            self.section_order.append(current_section)
    
    def get(self, section: str, key: str, default: Any = None) -> Any:
        """Get a value from a section."""
        section = section.lower()
        key = key.lower()
        
        if section in self.sections:
            return self.sections[section].get(key, default)
        return default
    
    def get_int(self, section: str, key: str, default: int = 0) -> int:
        """Get an integer value."""
        value = self.get(section, key)
        if value is None:
            return default
        try:
            return int(float(value))
        except ValueError:
            return default
    
    def get_float(self, section: str, key: str, default: float = 0.0) -> float:
        """Get a float value."""
        value = self.get(section, key)
        if value is None:
            return default
        try:
            return float(value)
        except ValueError:
            return default
    
    def get_tuple(self, section: str, key: str, 
                  default: Tuple = (0, 0)) -> Tuple:
        """Get a tuple value (comma-separated)."""
        value = self.get(section, key)
        if value is None:
            return default
        
        try:
            parts = [float(x.strip()) for x in value.split(',')]
            return tuple(parts)
        except ValueError:
            return default


class CharacterLoader:
    """
    Loads a complete MUGEN character from its folder.
    """
    
    def __init__(self, char_path: str):
        self.path = Path(char_path)
        
        # Find the main .def file
        def_files = list(self.path.glob('*.def'))
        if not def_files:
            raise FileNotFoundError(f"No .def file found in {char_path}")
        
        self.def_file = def_files[0]
        
        # Loaded data
        self.name: str = ""
        self.displayname: str = ""
        self.author: str = ""
        self.versiondate: str = ""
        
        self.sprites: Optional[Any] = None  # SFF loader
        self.sounds: Optional[Any] = None   # SND loader
        self.animations: Dict[int, Animation] = {}
        self.commands: List[Command] = []
        self.states: Dict[int, StateDef] = {}
        self.constants = CharacterConstants()
        
        # File references
        self._sprite_file: str = ""
        self._anim_file: str = ""
        self._sound_file: str = ""
        self._cmd_file: str = ""
        self._cns_files: List[str] = []
        self._st_files: List[str] = []
        
        self._load()

    def _find_file(self, filename: str) -> Optional[Path]:
        """
        Case-insensitive file search: look in char dir first, then data/ dir.
        Returns the Path if found, None otherwise.
        """
        if not filename:
            return None
        # Try exact path relative to char folder
        p = self.path / filename
        if p.exists():
            return p
        # Case-insensitive scan of char folder
        name_lower = Path(filename).name.lower()
        for f in self.path.iterdir():
            if f.name.lower() == name_lower:
                return f
        # Try relative to data/ directory (for stcommon etc.)
        data_path = self.path.parent.parent / filename
        if data_path.exists():
            return data_path
        # Case-insensitive scan of same directory
        parent = data_path.parent
        if parent.exists():
            for f in parent.iterdir():
                if f.name.lower() == name_lower:
                    return f
        return None
    
    def _load(self) -> None:
        """Load all character data."""
        # Parse main .def file
        with open(self.def_file, 'r', encoding='latin-1') as f:
            def_content = f.read()
        
        def_parser = INIParser(def_content)
        
        # Get character info
        self.name = def_parser.get('info', 'name', self.path.name)
        self.displayname = def_parser.get('info', 'displayname', self.name)
        self.author = def_parser.get('info', 'author', 'Unknown')
        self.versiondate = def_parser.get('info', 'versiondate', '')
        
        # Get file references
        self._sprite_file = def_parser.get('files', 'sprite', f'{self.path.name}.sff')
        self._anim_file   = def_parser.get('files', 'anim',   f'{self.path.name}.air')
        self._sound_file  = def_parser.get('files', 'sound',  '')
        self._cmd_file    = def_parser.get('files', 'cmd',    f'{self.path.name}.cmd')
        
        # CNS files — always prepend global common1.cns so state 0 exists
        cns_file = def_parser.get('files', 'cns', f'{self.path.name}.cns')
        stcommon = def_parser.get('files', 'stcommon', '')

        # Try to resolve stcommon path (may be relative to char dir or data/)
        self._cns_files = []
        if stcommon:
            self._cns_files.append(stcommon)   # load stcommon first (base states)
        self._cns_files.append(cns_file)        # then char-specific states

        # Additional state files (st0, st1, st2, etc.)
        for i in range(12):
            st_file = def_parser.get('files', f'st{i}', '')
            if st_file:
                self._st_files.append(st_file)

        # Load sprites — case-insensitive search for macOS/Linux
        sprite_path = self._find_file(self._sprite_file)
        if sprite_path:
            try:
                self.sprites = SpriteLoader.load(str(sprite_path))
                sprite_count = len(self.sprites.sprites) if hasattr(self.sprites, 'sprites') else '?'
                print(f"  [SFF] {self.name}: loaded {sprite_count} sprites from {sprite_path.name}")
            except Exception as e:
                print(f"  [SFF] {self.name}: FAILED to load {sprite_path.name}: {e}")
        else:
            print(f"  [SFF] {self.name}: sprite file not found: {self._sprite_file}")
        
        # Load sounds
        if self._sound_file:
            sound_path = self._find_file(self._sound_file)
            if sound_path:
                try:
                    self.sounds = SoundLoader.load(str(sound_path))
                except Exception:
                    pass
        
        # Load animations
        self._load_animations()
        
        # Load commands
        self._load_commands()
        
        # Load states
        self._load_states()
    
    def _load_animations(self) -> None:
        """Load animations from .air file."""
        anim_path = self._find_file(self._anim_file)
        if not anim_path:
            return
        
        with open(anim_path, 'r', encoding='latin-1') as f:
            content = f.read()
        
        current_anim: Optional[Animation] = None
        current_clsn1: List[Tuple[int, int, int, int]] = []
        current_clsn2: List[Tuple[int, int, int, int]] = []
        clsn1_default: List[Tuple[int, int, int, int]] = []
        clsn2_default: List[Tuple[int, int, int, int]] = []
        
        for line in content.split('\n'):
            line = line.strip()
            
            # Skip empty lines and comments
            if not line or line.startswith(';'):
                continue
            
            # Remove inline comments
            if ';' in line:
                line = line[:line.index(';')].strip()
            
            # Animation header: [Begin Action XXX]
            match = re.match(r'\[begin action (\d+)\]', line, re.IGNORECASE)
            if match:
                # Save previous animation
                if current_anim is not None:
                    self.animations[current_anim.id] = current_anim
                
                anim_id = int(match.group(1))
                current_anim = Animation(id=anim_id, frames=[])
                current_clsn1 = []
                current_clsn2 = []
                clsn1_default = []
                clsn2_default = []
                continue
            
            if current_anim is None:
                continue
            
            # Collision boxes: Clsn1Default, Clsn2Default, Clsn1, Clsn2
            clsn_default_match = re.match(r'clsn(\d)default:\s*(\d+)', line, re.IGNORECASE)
            if clsn_default_match:
                clsn_type = clsn_default_match.group(1)
                # Following lines will be box definitions
                continue
            
            clsn_match = re.match(r'clsn(\d):\s*(\d+)', line, re.IGNORECASE)
            if clsn_match:
                clsn_type = clsn_match.group(1)
                if clsn_type == '1':
                    current_clsn1 = []
                else:
                    current_clsn2 = []
                continue
            
            # Box definition: Clsn1[0] = x1,y1,x2,y2
            box_match = re.match(r'clsn(\d)\[\d+\]\s*=\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)', 
                                line, re.IGNORECASE)
            if box_match:
                clsn_type = box_match.group(1)
                box = (
                    int(box_match.group(2)),
                    int(box_match.group(3)),
                    int(box_match.group(4)),
                    int(box_match.group(5))
                )
                if clsn_type == '1':
                    current_clsn1.append(box)
                else:
                    current_clsn2.append(box)
                continue
            
            # Animation frame: group, index, x, y, duration, [flip flags]
            frame_match = re.match(
                r'(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)(?:\s*,\s*([HhVvAa]+))?',
                line
            )
            if frame_match:
                flip_flags = frame_match.group(6) or ""
                
                frame = AnimationFrame(
                    group=int(frame_match.group(1)),
                    index=int(frame_match.group(2)),
                    x_offset=int(frame_match.group(3)),
                    y_offset=int(frame_match.group(4)),
                    duration=int(frame_match.group(5)),
                    flip_h='H' in flip_flags.upper(),
                    flip_v='V' in flip_flags.upper(),
                    clsn1=current_clsn1.copy() or clsn1_default.copy(),
                    clsn2=current_clsn2.copy() or clsn2_default.copy()
                )
                current_anim.frames.append(frame)
                
                # Clear non-default boxes
                current_clsn1 = []
                current_clsn2 = []
            
            # Loopstart marker
            if line.lower() == 'loopstart':
                current_anim.loop_start = len(current_anim.frames)
        
        # Save last animation
        if current_anim is not None:
            self.animations[current_anim.id] = current_anim
    
    def _load_commands(self) -> None:
        """Load commands from .cmd file."""
        cmd_path = self._find_file(self._cmd_file)
        if not cmd_path:
            return
        
        with open(cmd_path, 'r', encoding='latin-1') as f:
            content = f.read()
        
        parser = INIParser(content)
        
        # Parse command definitions
        # Commands are in sections like [Command], [Command], etc.
        current_cmd: Optional[Command] = None
        
        for line in content.split('\n'):
            line = line.strip()
            
            if not line or line.startswith(';'):
                continue
            
            # Remove inline comments
            if ';' in line:
                line = line[:line.index(';')].strip()
            
            # Command section header
            if line.lower() == '[command]':
                if current_cmd and current_cmd.name:
                    self.commands.append(current_cmd)
                current_cmd = Command(name='', inputs=[])
                continue
            
            if current_cmd is None:
                continue
            
            # Parse command properties
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip().lower()
                value = value.strip()
                
                if key == 'name':
                    current_cmd.name = value.strip('"')
                elif key == 'command':
                    current_cmd.inputs = self._parse_command_input(value)
                elif key == 'time':
                    current_cmd.time = int(value)
                elif key == 'buffer.time':
                    current_cmd.buffer_time = int(value)
        
        # Save last command
        if current_cmd and current_cmd.name:
            self.commands.append(current_cmd)
    
    def _parse_command_input(self, input_str: str) -> List[CommandInput]:
        """Parse a MUGEN command input string."""
        inputs = []
        
        # Split by comma for simultaneous presses, space for sequence
        parts = re.split(r'[\s,]+', input_str)
        
        for part in parts:
            if not part:
                continue
            
            cmd_input = CommandInput()
            
            # Check modifiers
            if part.startswith('~'):
                cmd_input.hold = True
                # Check for hold duration (e.g., ~30)
                match = re.match(r'~(\d+)?(.+)?', part)
                if match:
                    if match.group(1):
                        cmd_input.time = int(match.group(1))
                    part = match.group(2) or ''
            
            if part.startswith('/'):
                cmd_input.negate = True
                part = part[1:]
            
            if part.startswith('$'):
                cmd_input.release = True
                part = part[1:]
            
            # Direction
            direction_map = {
                'D': 'D', 'F': 'F', 'B': 'B', 'U': 'U',
                'DF': 'DF', 'DB': 'DB', 'UF': 'UF', 'UB': 'UB'
            }
            
            upper_part = part.upper()
            for dir_key, dir_val in direction_map.items():
                if upper_part == dir_key:
                    cmd_input.direction = dir_val
                    break
            
            # Button
            if part.lower() in ('a', 'b', 'c', 'x', 'y', 'z', 's'):
                cmd_input.button = part.lower()
            
            if cmd_input.direction or cmd_input.button:
                inputs.append(cmd_input)
        
        return inputs
    
    def _load_states(self) -> None:
        """Load state definitions from .cns and .st files."""
        all_state_files = self._cns_files + self._st_files
        
        for state_file in all_state_files:
            state_path = self.path / state_file
            if not state_path.exists():
                continue
            
            with open(state_path, 'r', encoding='latin-1') as f:
                content = f.read()
            
            # First pass: load constants from [Data], [Size], [Velocity], [Movement]
            parser = INIParser(content)
            self._load_constants(parser)
            
            # Second pass: load state definitions
            self._parse_states(content)
    
    def _load_constants(self, parser: INIParser) -> None:
        """Load character constants from parsed CNS file."""
        # [Data] section
        self.constants.life = parser.get_int('data', 'life', 1000)
        self.constants.attack = parser.get_int('data', 'attack', 100)
        self.constants.defence = parser.get_int('data', 'defence', 100)
        self.constants.fall_defence_up = parser.get_int('data', 'fall.defence_up', 50)
        self.constants.liedown_time = parser.get_int('data', 'liedown.time', 60)
        self.constants.airjuggle = parser.get_int('data', 'airjuggle', 15)
        self.constants.sparkno = parser.get_int('data', 'sparkno', 2)
        self.constants.guard_sparkno = parser.get_int('data', 'guard.sparkno', 40)
        
        # [Size] section
        self.constants.xscale = parser.get_float('size', 'xscale', 1.0)
        self.constants.yscale = parser.get_float('size', 'yscale', 1.0)
        self.constants.ground_back = parser.get_int('size', 'ground.back', 15)
        self.constants.ground_front = parser.get_int('size', 'ground.front', 16)
        self.constants.air_back = parser.get_int('size', 'air.back', 12)
        self.constants.air_front = parser.get_int('size', 'air.front', 12)
        self.constants.height = parser.get_int('size', 'height', 60)
        self.constants.attack_dist = parser.get_int('size', 'attack.dist', 160)
        
        head_pos = parser.get_tuple('size', 'head.pos', (-5, -90))
        self.constants.head_pos = (int(head_pos[0]), int(head_pos[1]))
        
        mid_pos = parser.get_tuple('size', 'mid.pos', (-5, -60))
        self.constants.mid_pos = (int(mid_pos[0]), int(mid_pos[1]))
        
        # [Velocity] section
        self.constants.walk_fwd = parser.get_float('velocity', 'walk.fwd', 2.4)
        self.constants.walk_back = parser.get_float('velocity', 'walk.back', -2.2)
        
        run_fwd = parser.get_tuple('velocity', 'run.fwd', (4.6, 0.0))
        self.constants.run_fwd = (float(run_fwd[0]), float(run_fwd[1]))
        
        run_back = parser.get_tuple('velocity', 'run.back', (-4.5, -3.8))
        self.constants.run_back = (float(run_back[0]), float(run_back[1]))
        
        jump_neu = parser.get_tuple('velocity', 'jump.neu', (0.0, -8.4))
        self.constants.jump_neu = (float(jump_neu[0]), float(jump_neu[1]))
        
        self.constants.jump_back = parser.get_float('velocity', 'jump.back', -2.55)
        self.constants.jump_fwd = parser.get_float('velocity', 'jump.fwd', 2.5)
        
        # [Movement] section
        self.constants.airjump_num = parser.get_int('movement', 'airjump.num', 1)
        self.constants.airjump_height = parser.get_int('movement', 'airjump.height', 35)
        self.constants.yaccel = parser.get_float('movement', 'yaccel', 0.44)
        self.constants.stand_friction = parser.get_float('movement', 'stand.friction', 0.85)
        self.constants.crouch_friction = parser.get_float('movement', 'crouch.friction', 0.82)
    
    def _parse_states(self, content: str) -> None:
        """Parse state definitions and controllers from CNS content."""
        current_state: Optional[StateDef] = None
        current_controller: Optional[StateController] = None
        in_controller = False
        
        lines = content.split('\n')
        i = 0
        
        while i < len(lines):
            line = lines[i].strip()
            i += 1
            
            # Skip empty lines and comments
            if not line or line.startswith(';'):
                continue
            
            # Remove inline comments
            if ';' in line:
                line = line[:line.index(';')].strip()
            
            # Statedef header: [Statedef XXX]
            statedef_match = re.match(r'\[statedef\s+(-?\d+)\]', line, re.IGNORECASE)
            if statedef_match:
                # Save previous state
                if current_state is not None:
                    if current_controller is not None:
                        current_state.controllers.append(current_controller)
                    self.states[current_state.number] = current_state
                
                state_num = int(statedef_match.group(1))
                current_state = StateDef(number=state_num)
                current_controller = None
                in_controller = False
                continue
            
            # State controller header: [State XXX, ControllerName]
            state_match = re.match(r'\[state\s+(-?\d+)\s*(?:,\s*(.+))?\]', line, re.IGNORECASE)
            if state_match:
                # Save previous controller
                if current_controller is not None and current_state is not None:
                    current_state.controllers.append(current_controller)
                
                controller_name = state_match.group(2) or ""
                current_controller = StateController(type="", params={'name': controller_name.strip()})
                in_controller = True
                continue
            
            if current_state is None:
                continue
            
            # Parse key-value pairs
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip().lower()
                value = value.strip()
                
                if not in_controller:
                    # Statedef properties
                    self._parse_statedef_property(current_state, key, value)
                else:
                    # State controller properties
                    if current_controller:
                        self._parse_controller_property(current_controller, key, value)
        
        # Save last state
        if current_state is not None:
            if current_controller is not None:
                current_state.controllers.append(current_controller)
            self.states[current_state.number] = current_state
    
    def _parse_statedef_property(self, state: StateDef, key: str, value: str) -> None:
        """Parse a statedef property."""
        if key == 'type':
            state.type = StateType(value.upper()[0]) if value else StateType.STANDING
        elif key == 'movetype':
            state.movetype = MoveType(value.upper()[0]) if value else MoveType.IDLE
        elif key == 'physics':
            state.physics = Physics(value.upper()[0]) if value else Physics.STAND
        elif key == 'anim':
            state.anim = int(value)
        elif key == 'velset':
            parts = value.split(',')
            vel_x = float(parts[0]) if parts[0].strip() else None
            vel_y = float(parts[1]) if len(parts) > 1 and parts[1].strip() else None
            state.velset = (vel_x, vel_y)
        elif key == 'ctrl':
            state.ctrl = int(value)
        elif key == 'poweradd':
            state.poweradd = int(value)
        elif key == 'juggle':
            state.juggle = int(value)
        elif key == 'facep2':
            state.facep2 = value.lower() in ('1', 'true')
        elif key == 'sprpriority':
            state.sprpriority = int(value)
    
    def _parse_controller_property(self, controller: StateController, 
                                   key: str, value: str) -> None:
        """Parse a state controller property."""
        if key == 'type':
            controller.type = value
        elif key.startswith('triggerall'):
            controller.trigger_all.append(value)
        elif key.startswith('trigger'):
            # Extract trigger number
            match = re.match(r'trigger(\d+)', key)
            if match:
                trigger_num = int(match.group(1))
                if trigger_num not in controller.triggers:
                    controller.triggers[trigger_num] = []
                controller.triggers[trigger_num].append(value)
        elif key == 'persistent':
            controller.persistent = int(value)
        elif key == 'ignorehitpause':
            controller.ignore_hitpause = value.lower() in ('1', 'true')
        else:
            # Store as generic parameter
            controller.params[key] = value
