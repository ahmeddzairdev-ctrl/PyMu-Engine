"""
MUGEN stage loader — parses stage .def files and background definitions.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field

from mugen.sprite_loader import SpriteLoader


@dataclass
class BgLayer:
    """A single background layer."""
    name: str
    layer_type: str = "normal"   # normal | anim | parallax
    sprite_group: int = 0
    sprite_index: int = 0
    start: Tuple[int, int] = (0, 0)
    delta: Tuple[float, float] = (1.0, 1.0)
    velocity: Tuple[float, float] = (0.0, 0.0)
    tile: Tuple[int, int] = (0, 0)
    window: Optional[Tuple[int, int, int, int]] = None
    anim: int = -1
    visible: bool = True


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
    sprites: Optional[Any] = None   # SFFv1Reader | SFFv2Reader


class StageLoader:
    """Loads a MUGEN stage from its .def file."""

    def __init__(self, def_path: str):
        self.def_path = Path(def_path)
        self.stage_dir = self.def_path.parent
        self.info = StageInfo()
        self._load()

    # ------------------------------------------------------------------

    def _load(self) -> None:
        with open(self.def_path, "r", encoding="latin-1") as f:
            content = f.read()

        self._parse_def(content)

    def _parse_def(self, content: str) -> None:
        current_section = ""
        current_bg: Optional[Dict[str, str]] = None
        sections: Dict[str, Dict[str, str]] = {}

        for line in content.split("\n"):
            line = line.strip()
            if not line or line.startswith(";"):
                continue
            if ";" in line:
                line = line[: line.index(";")].strip()

            # Section header
            if line.startswith("[") and "]" in line:
                header = line[1 : line.index("]")].lower()

                # Save completed bg layer
                if current_bg is not None and current_section.startswith("bg "):
                    self._add_bg_layer(current_bg)

                current_section = header

                if header.startswith("bg ") or header == "bgdef":
                    current_bg = {} if not header == "bgdef" else None
                else:
                    current_bg = None
                    sections[header] = {}
                continue

            if "=" not in line:
                continue

            key, _, val = line.partition("=")
            key = key.strip().lower()
            val = val.strip()

            if current_bg is not None and current_section.startswith("bg "):
                current_bg[key] = val
            elif current_section in sections:
                sections[current_section][key] = val

        # Flush last bg layer
        if current_bg is not None:
            self._add_bg_layer(current_bg)

        self._apply_sections(sections)

    def _apply_sections(self, sections: Dict[str, Dict[str, str]]) -> None:
        def gi(sec, key, default=0):
            v = sections.get(sec, {}).get(key)
            return int(float(v)) if v is not None else default

        def gf(sec, key, default=0.0):
            v = sections.get(sec, {}).get(key)
            return float(v) if v is not None else default

        def gs(sec, key, default=""):
            return sections.get(sec, {}).get(key, default).strip('"')

        def gt(sec, key, default=(0, 0)):
            v = sections.get(sec, {}).get(key)
            if v:
                parts = [float(x) for x in v.split(",")]
                return tuple(parts) if len(parts) >= 2 else default
            return default

        self.info.name = gs("info", "name", "Unknown Stage")
        self.info.author = gs("info", "author", "")

        self.info.bound_left = gi("camera", "boundleft", -150)
        self.info.bound_right = gi("camera", "boundright", 150)
        self.info.floor_tension = gi("camera", "floortension", 20)
        self.info.vertical_follow = gf("camera", "verticalfollow", 0.2)
        self.info.zoffset = gi("camera", "zoffset", 200)

        p1_start = gt("playerinfo", "p1startx p1starty".split()[0].replace(" ", ""), (0, 0))
        self.info.p1_start_x = gi("playerinfo", "p1startx", -70)
        self.info.p2_start_x = gi("playerinfo", "p2startx", 70)

        self.info.bgmusic = gs("music", "bgmusic", "")

        # Load sprites
        sprite_file = sections.get("bgdef", {}).get("spr", "")
        if sprite_file:
            sprite_path = self.stage_dir / sprite_file
            if sprite_path.exists():
                try:
                    self.info.sprites = SpriteLoader.load(str(sprite_path))
                except Exception as e:
                    print(f"StageLoader: cannot load sprites '{sprite_path}': {e}")

    def _add_bg_layer(self, data: Dict[str, str]) -> None:
        def gi(key, default=0):
            v = data.get(key)
            return int(float(v)) if v else default

        def gf(key, default=0.0):
            v = data.get(key)
            return float(v) if v else default

        def gt(key, default=(0, 0)):
            v = data.get(key)
            if v:
                parts = [float(x) for x in v.split(",")]
                if len(parts) >= 2:
                    return (parts[0], parts[1])
            return default

        layer = BgLayer(
            name=data.get("name", ""),
            layer_type=data.get("type", "normal").lower(),
            sprite_group=gi("spriteno"),
            sprite_index=gi("spriteno"),  # Will be split below
            start=gt("start"),
            delta=gt("delta", (1.0, 1.0)),
            velocity=gt("velocity"),
            tile=gt("tile"),
            anim=gi("actionno", -1),
            visible=gi("visible", 1) != 0,
        )

        # spriteno = group, index
        spriteno = data.get("spriteno", "0,0")
        parts = spriteno.split(",")
        if len(parts) == 2:
            try:
                layer.sprite_group = int(parts[0])
                layer.sprite_index = int(parts[1])
            except ValueError:
                pass

        self.info.bg_layers.append(layer)

    # ------------------------------------------------------------------

    @staticmethod
    def load(def_path: str) -> "StageLoader":
        return StageLoader(def_path)
