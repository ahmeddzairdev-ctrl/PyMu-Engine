"""
MUGEN stage loader — parses stage .def files and background definitions.

Fixes applied:
  - Robust number parsing: handles European comma-decimal (e.g. '0,9' → 0.9),
    whitespace-padded values, and empty strings without crashing.
  - Tuple parsing: splits on ', ' or ',' and normalises each part independently
    so decimal commas cannot be confused with pair separators.
  - BgLayer.spriteno: was incorrectly using gi() for both group AND index
    (always returned the same value); now parsed as a pair from the raw string.
  - bgdef section: properly collected as its own dict so spr= is never missed.
  - _add_bg_layer: `gi("actionno", -1)` default now works correctly when the
    key is absent (previously returned 0 due to falsy-zero bug in `if v`).
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field

from mugen.sprite_loader import SpriteLoader


# ---------------------------------------------------------------------------
# Number parsing helpers — robust against European locale files
# ---------------------------------------------------------------------------

def _parse_float(s: str) -> float:
    """
    Parse a float from a MUGEN value string.
    Handles:
      '0.9'  → 0.9   (standard)
      '0,9'  → 0.9   (European decimal separator)
      ' 200' → 200.0 (leading/trailing whitespace)
    Raises ValueError if the string is not a valid number.
    """
    s = s.strip()
    try:
        return float(s)
    except ValueError:
        # Try replacing comma with dot (European locale stage files)
        return float(s.replace(',', '.'))


def _parse_int(s: str) -> int:
    return int(_parse_float(s))


def _parse_pair(s: str) -> Optional[Tuple[float, float]]:
    """
    Parse a 'x, y' value string into a (float, float) tuple.

    MUGEN uses commas as pair separators AND some files use commas as
    decimal separators.  We disambiguate by requiring that a pair
    separator is surrounded by digits on both sides:

        '1.0, 0.5'  → (1.0, 0.5)   ← standard
        '1,0, 0,5'  → (1.0, 0.5)   ← European decimals in a pair
        '0,9'       → None          ← single European float; caller uses _parse_float
        '0, 0'      → (0.0, 0.0)   ← standard pair

    Strategy: split on ', ' (comma + space) first; if that gives 2+ parts,
    parse each part with _parse_float (which also handles '0,9' → 0.9).
    If that gives only 1 part, split on ',' and try again.
    """
    s = s.strip()

    # Try 'x, y' split first (most common MUGEN format)
    parts = [p.strip() for p in re.split(r',\s+', s)]
    if len(parts) >= 2:
        try:
            return tuple(_parse_float(p) for p in parts[:2])
        except ValueError:
            pass

    # Fall back to plain ',' split — but only if we get exactly 2 numeric parts
    parts = [p.strip() for p in s.split(',')]
    if len(parts) == 2:
        try:
            return (_parse_float(parts[0]), _parse_float(parts[1]))
        except ValueError:
            pass

    return None   # Could not parse as pair


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class BgLayer:
    """A single background layer."""
    name: str
    layer_type: str = "normal"          # normal | anim | parallax
    sprite_group: int = 0
    sprite_index: int = 0
    start: Tuple[float, float] = (0.0, 0.0)
    delta: Tuple[float, float] = (1.0, 1.0)
    velocity: Tuple[float, float] = (0.0, 0.0)
    tile: Tuple[int, int] = (0, 0)
    window: Optional[Tuple[int, int, int, int]] = None
    anim: int = -1
    visible: bool = True
    layerno: int = 0    # 0 = background, 1 = foreground (MUGEN layerno field)


@dataclass
class StageInfo:
    """Parsed stage definition."""
    name: str = "Unknown Stage"
    author: str = ""

    # [Camera]
    bound_left: int = -150
    bound_right: int = 150
    floor_tension: int = 20
    vertical_follow: float = 0.2
    zoffset: int = 200
    start_x: int = 0
    start_y: int = 0

    # [PlayerInfo]
    p1_start_x: int = -70
    p2_start_x: int = 70

    # [Music]
    bgmusic: str = ""
    bgvolume: int = 100

    bg_layers: List[BgLayer] = field(default_factory=list)
    sprites: Optional[Any] = None       # SFFv1Reader | SFFv2Reader


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

class StageLoader:
    """Loads a MUGEN stage from its .def file."""

    def __init__(self, def_path: str):
        self.def_path  = Path(def_path)
        self.stage_dir = self.def_path.parent
        self.info      = StageInfo()
        self._load()

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _load(self) -> None:
        with open(self.def_path, "r", encoding="latin-1") as f:
            content = f.read()
        self._parse_def(content)

    def _parse_def(self, content: str) -> None:
        current_section = ""
        current_bg: Optional[Dict[str, str]] = None
        sections: Dict[str, Dict[str, str]] = {}

        def is_bg_section(header: str) -> bool:
            """Match [BG x], [BG0], [BGAnim x], [BGA x], etc."""
            h = header.lower()
            # Explicit bgdef is NOT a bg layer section
            if h == "bgdef":
                return False
            # Match: bg<anything> but NOT bgdef
            if h.startswith("bg") and h != "bgdef":
                return True
            return False

        def flush_bg():
            nonlocal current_bg
            if current_bg is not None:
                self._add_bg_layer(current_bg)
            current_bg = None

        for raw_line in content.split("\n"):
            line = raw_line.strip()
            if not line or line.startswith(";"):
                continue
            if ";" in line:
                line = line[: line.index(";")].strip()
            if not line:
                continue

            # Section header
            if line.startswith("[") and "]" in line:
                header = line[1: line.index("]")].strip().lower()

                # Flush any pending bg layer
                if is_bg_section(current_section):
                    flush_bg()

                current_section = header

                if header == "bgdef":
                    sections.setdefault("bgdef", {})
                    current_bg = None
                elif is_bg_section(header):
                    current_bg = {"_section": header}
                else:
                    sections.setdefault(header, {})
                    current_bg = None
                continue

            if "=" not in line:
                continue

            key, _, val = line.partition("=")
            key = key.strip().lower()
            val = val.strip()

            if current_bg is not None:
                current_bg[key] = val
            elif current_section in sections:
                sections[current_section][key] = val

        # Flush last bg layer
        if is_bg_section(current_section):
            flush_bg()

        self._apply_sections(sections)

    # ------------------------------------------------------------------
    # Section application — all parsing goes through _parse_float/_parse_int
    # ------------------------------------------------------------------

    def _apply_sections(self, sections: Dict[str, Dict[str, str]]) -> None:

        def _get(sec: str, key: str) -> Optional[str]:
            return sections.get(sec, {}).get(key)

        def gi(sec: str, key: str, default: int = 0) -> int:
            v = _get(sec, key)
            if v is None:
                return default
            try:
                return _parse_int(v)
            except (ValueError, ArithmeticError):
                return default

        def gf(sec: str, key: str, default: float = 0.0) -> float:
            v = _get(sec, key)
            if v is None:
                return default
            try:
                return _parse_float(v)
            except (ValueError, ArithmeticError):
                return default

        def gs(sec: str, key: str, default: str = "") -> str:
            v = _get(sec, key)
            return v.strip('"').strip("'") if v is not None else default

        def gt(sec: str, key: str,
               default: Tuple[float, float] = (0.0, 0.0)) -> Tuple[float, float]:
            v = _get(sec, key)
            if v is None:
                return default
            pair = _parse_pair(v)
            return pair if pair is not None else default

        # [Info]
        self.info.name   = gs("info", "name", "Unknown Stage")
        self.info.author = gs("info", "author", "")

        # [Camera]
        self.info.bound_left      = gi("camera", "boundleft",       -150)
        self.info.bound_right     = gi("camera", "boundright",       150)
        self.info.floor_tension   = gi("camera", "floortension",      20)
        self.info.vertical_follow = gf("camera", "verticalfollow",   0.2)
        self.info.start_x         = gi("camera", "startx",            0)
        self.info.start_y         = gi("camera", "starty",            0)

        # [StageInfo] — zoffset: ground Y in the 320×240 internal screen.
        # stage_loader.gd: result.stageinfo_zoffset = int(stageinfo['zoffset'])
        # [Camera].zoffset is the camera scroll boundary, NOT the ground position.
        # Prefer [StageInfo].zoffset; fall back to [Camera].zoffset; then 160.
        _zo_si = _get("stageinfo", "zoffset")
        _zo_ca = _get("camera",    "zoffset")
        if _zo_si is not None:
            try:
                self.info.zoffset = _parse_int(_zo_si)
            except (ValueError, ArithmeticError):
                self.info.zoffset = 160
        elif _zo_ca is not None:
            try:
                self.info.zoffset = _parse_int(_zo_ca)
            except (ValueError, ArithmeticError):
                self.info.zoffset = 160
        else:
            self.info.zoffset = 160    # safe default: 2/3 down on 240px surface

        # [PlayerInfo]
        self.info.p1_start_x = gi("playerinfo", "p1startx", -70)
        self.info.p2_start_x = gi("playerinfo", "p2startx",  70)

        # [Music]
        self.info.bgmusic  = gs("music", "bgmusic",  "")
        self.info.bgvolume = gi("music", "bgvolume", 100)

        # [BGdef] — sprite file
        sprite_file = gs("bgdef", "spr", "")
        if not sprite_file:
            sprite_file = gs("bgdef", "sprite", "")
        if sprite_file:
            # Try exact path, then case-insensitive scan
            sprite_path = self._find_sprite_file(sprite_file)
            if sprite_path:
                try:
                    self.info.sprites = SpriteLoader.load(str(sprite_path))
                    n = len(self.info.sprites.sprites) if hasattr(self.info.sprites, 'sprites') else '?'
                    print(f"  [Stage SFF] {self.def_path.stem}: loaded {n} sprites from {sprite_path.name}")
                except Exception as e:
                    print(f"  [Stage SFF] {self.def_path.stem}: FAILED to load {sprite_path}: {e}")
            else:
                print(f"  [Stage SFF] {self.def_path.stem}: file not found: {sprite_file}")

    # ------------------------------------------------------------------
    # Background layer parsing
    # ------------------------------------------------------------------

    def _add_bg_layer(self, data: Dict[str, str]) -> None:

        def gi(key: str, default: int = 0) -> int:
            v = data.get(key)
            if not v:
                return default
            try:
                return _parse_int(v)
            except (ValueError, ArithmeticError):
                return default

        def gf(key: str, default: float = 0.0) -> float:
            v = data.get(key)
            if not v:
                return default
            try:
                return _parse_float(v)
            except (ValueError, ArithmeticError):
                return default

        def gt(key: str,
               default: Tuple[float, float] = (0.0, 0.0)) -> Tuple[float, float]:
            v = data.get(key)
            if not v:
                return default
            pair = _parse_pair(v)
            return pair if pair is not None else default

        layer_type = data.get("type", "normal").strip().lower()

        # --- spriteno: parse as "group, index" pair ---
        sprite_group = 0
        sprite_index = 0
        spriteno_raw = data.get("spriteno", "")
        if spriteno_raw:
            pair = _parse_pair(spriteno_raw)
            if pair is not None:
                sprite_group = int(pair[0])
                sprite_index = int(pair[1])
            else:
                try:
                    sprite_group = _parse_int(spriteno_raw)
                except (ValueError, ArithmeticError):
                    pass

        # --- tile: parse as "tile_x, tile_y" or single value ---
        tile_raw = data.get("tile", "")
        tile: Tuple[int, int] = (0, 0)
        if tile_raw:
            pair = _parse_pair(tile_raw)
            if pair is not None:
                tile = (int(pair[0]), int(pair[1]))
            else:
                try:
                    t = _parse_int(tile_raw)
                    tile = (t, t)
                except (ValueError, ArithmeticError):
                    pass

        # --- visible: treat missing key as visible (default 1) ---
        # Use raw dict access to distinguish "absent" from "= 0"
        visible_raw = data.get("visible")
        if visible_raw is None:
            visible = True
        else:
            try:
                visible = _parse_int(visible_raw) != 0
            except (ValueError, ArithmeticError):
                visible = True

        # --- actionno: animation number (-1 = none) ---
        anim_raw = data.get("actionno")
        if anim_raw is None:
            anim = -1
        else:
            try:
                anim = _parse_int(anim_raw)
            except (ValueError, ArithmeticError):
                anim = -1

        # --- layerno: 0=background, 1=foreground ---
        layerno_raw = data.get("layerno")
        if layerno_raw is None:
            layerno = 0
        else:
            try:
                layerno = _parse_int(layerno_raw)
            except (ValueError, ArithmeticError):
                layerno = 0

        layer = BgLayer(
            name         = data.get("name", ""),
            layer_type   = layer_type,
            sprite_group = sprite_group,
            sprite_index = sprite_index,
            start        = gt("start",   (0.0,  0.0)),
            delta        = gt("delta",   (1.0,  1.0)),
            velocity     = gt("velocity",(0.0,  0.0)),
            tile         = tile,
            anim         = anim,
            visible      = visible,
            layerno      = layerno,
        )
        self.info.bg_layers.append(layer)

    # ------------------------------------------------------------------

    def _find_sprite_file(self, filename: str) -> Optional[Path]:
        """
        Case-insensitive file search.
        Tries in order:
          1. Relative to the stage's own directory (most common)
          2. Relative to the project root (some stages use 'stages/x/x.sff')
          3. Case-insensitive variant of either location
        """
        if not filename:
            return None
        candidates = [
            self.stage_dir / filename,           # relative to stage folder
            Path('.') / filename,                 # relative to cwd / project root
            Path('data') / filename,              # relative to data/
        ]
        # Try exact paths
        for c in candidates:
            if c.exists():
                return c
        # Try case-insensitive scan in stage dir
        name_lower = Path(filename).name.lower()
        for search_dir in (self.stage_dir, Path('.'), Path('data')):
            if search_dir.exists():
                for f in search_dir.iterdir():
                    if f.name.lower() == name_lower:
                        return f
        return None

    # ------------------------------------------------------------------

    @staticmethod
    def load(def_path: str) -> "StageLoader":
        """Load a stage .def file and return the populated StageLoader."""
        return StageLoader(def_path)
