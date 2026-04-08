"""
MUGEN .fnt font loader.
MUGEN fonts are bitmap fonts stored as an SFF + a font descriptor.
"""

from pathlib import Path
from typing import Dict, Optional, Tuple
import pygame
from mugen.sprite_loader import SpriteLoader


class MugenFont:
    """
    Wraps a MUGEN bitmap font and provides a simple render() method.
    Falls back to pygame's built-in SysFont when the .fnt file is absent.
    """

    def __init__(self, fnt_path: str):
        self.path = Path(fnt_path)
        self._sprite_loader = None
        self._char_map: Dict[str, Tuple[int, int]] = {}   # char → (group, index)
        self._fallback: Optional[pygame.font.Font] = None
        self._load()

    # ------------------------------------------------------------------

    def _load(self) -> None:
        if not self.path.exists():
            self._fallback = pygame.font.SysFont("monospace", 16)
            return

        try:
            with open(self.path, "r", encoding="latin-1") as f:
                content = f.read()
            self._parse(content)
        except Exception as e:
            print(f"FontLoader: cannot read '{self.path}': {e}")
            self._fallback = pygame.font.SysFont("monospace", 16)

    def _parse(self, content: str) -> None:
        """Parse a minimal .fnt descriptor."""
        sprite_file = ""
        in_char_map = False

        for line in content.split("\n"):
            line = line.strip()
            if not line or line.startswith(";"):
                continue
            if ";" in line:
                line = line[: line.index(";")].strip()

            lower = line.lower()
            if lower.startswith("["):
                in_char_map = lower.startswith("[charmap]")
                continue

            if "=" not in line:
                continue

            key, _, val = line.partition("=")
            key = key.strip().lower()
            val = val.strip()

            if key == "file":
                sprite_file = val
            elif in_char_map:
                # key is the character, val is "group, index"
                parts = val.split(",")
                if len(parts) == 2:
                    try:
                        self._char_map[key] = (int(parts[0]), int(parts[1]))
                    except ValueError:
                        pass

        if sprite_file:
            sff_path = self.path.parent / sprite_file
            if sff_path.exists():
                try:
                    self._sprite_loader = SpriteLoader.load(str(sff_path))
                except Exception as e:
                    print(f"FontLoader: cannot load sprites '{sff_path}': {e}")

        if not self._sprite_loader:
            self._fallback = pygame.font.SysFont("monospace", 16)

    # ------------------------------------------------------------------

    def render(
        self,
        surface: pygame.Surface,
        text: str,
        x: int,
        y: int,
        color: Tuple[int, int, int] = (255, 255, 255),
    ) -> None:
        """Draw *text* onto *surface* at (x, y)."""
        if self._fallback:
            img = self._fallback.render(text, True, color)
            surface.blit(img, (x, y))
            return

        cx = x
        for ch in text:
            key = self._char_map.get(ch)
            if key is None:
                cx += 8   # Unknown char width fallback
                continue
            g, i = key
            glyph = self._sprite_loader.get_sprite(g, i)
            if glyph:
                surface.blit(glyph, (cx, y))
                cx += glyph.get_width()


class FontLoader:
    """Factory for loading MUGEN fonts."""

    @staticmethod
    def load(fnt_path: str) -> MugenFont:
        return MugenFont(fnt_path)
