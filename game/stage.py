"""
Stage class — runtime wrapper around a loaded StageLoader.
Handles parallax background rendering and camera bounds.
"""

from typing import TYPE_CHECKING
import pygame

if TYPE_CHECKING:
    from engine.renderer import Renderer
    from mugen.stage_loader import StageLoader, StageInfo


class Stage:
    """In-game stage instance."""

    def __init__(self, loader: "StageLoader"):
        info = loader.info

        self.name: str  = info.name
        self.sprites    = info.sprites          # SFF reader (may be None)
        self.bg_layers  = info.bg_layers        # List[BgLayer]

        # Camera / boundary info exposed to Fight
        self.bound_left:  int   = info.bound_left
        self.bound_right: int   = info.bound_right
        self.start_x:     int   = info.p1_start_x   # abs value used for P1 offset
        self.zoffset:     int   = info.zoffset

        # Background scroll state
        self._bg_offsets = [(float(layer.start[0]), float(layer.start[1]))
                            for layer in self.bg_layers]

    # ------------------------------------------------------------------

    def update(self) -> None:
        """Advance auto-scrolling background layers."""
        for i, layer in enumerate(self.bg_layers):
            ox, oy = self._bg_offsets[i]
            ox += layer.velocity[0]
            oy += layer.velocity[1]
            self._bg_offsets[i] = (ox, oy)

    # ------------------------------------------------------------------

    def render(self, renderer: "Renderer", camera_x: float, camera_y: float) -> None:
        """Render background layers (below foreground)."""
        self._render_layers(renderer, camera_x, camera_y, foreground=False)

    def render_foreground(self, renderer: "Renderer", camera_x: float, camera_y: float) -> None:
        """Render foreground layers (above characters)."""
        self._render_layers(renderer, camera_x, camera_y, foreground=True)

    def _render_layers(
        self,
        renderer: "Renderer",
        camera_x: float,
        camera_y: float,
        foreground: bool,
    ) -> None:
        if self.sprites is None:
            return

        surface = renderer.get_surface()
        sw, sh = surface.get_size()

        for i, layer in enumerate(self.bg_layers):
            if not layer.visible:
                continue

            # Simple foreground heuristic: layers after index midpoint
            is_fg = (i >= len(self.bg_layers) // 2)
            if is_fg != foreground:
                continue

            sprite = self.sprites.get_sprite(layer.sprite_group, layer.sprite_index)
            if sprite is None:
                continue

            ox, oy = self._bg_offsets[i]
            # Parallax delta: background moves slower than camera
            draw_x = int(ox - camera_x * layer.delta[0] + sw // 2)
            draw_y = int(oy - camera_y * layer.delta[1] + self.zoffset)

            tw, th = layer.tile
            if tw or th:
                self._tile_blit(surface, sprite, draw_x, draw_y, sw, sh, tw, th)
            else:
                surface.blit(sprite, (draw_x, draw_y))

    @staticmethod
    def _tile_blit(
        dest: pygame.Surface,
        sprite: pygame.Surface,
        x: int,
        y: int,
        screen_w: int,
        screen_h: int,
        tile_x: int,
        tile_y: int,
    ) -> None:
        """Tile-blit a sprite across the destination surface."""
        sw = sprite.get_width()
        sh = sprite.get_height()

        # Find starting coordinates
        sx = x % sw if sw else x
        if sx > 0:
            sx -= sw
        sy = y % sh if sh else y
        if sy > 0:
            sy -= sh

        cy = sy
        while cy < screen_h:
            cx = sx
            while cx < screen_w:
                dest.blit(sprite, (cx, cy))
                if not tile_x:
                    break
                cx += sw
            if not tile_y:
                break
            cy += sh
