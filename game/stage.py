"""
Stage rendering — correct MUGEN/Ikemen GO coordinate system.

MUGEN background coordinate system:
  - The stage .def [Camera] section defines `zoffset` = screen Y of the ground
    plane in the game's internal resolution (320×240).
  - Each BG layer has a `start` = (x, y) position relative to the CENTRE of the
    screen (x) and the GROUND LINE (y). Negative y = above ground.
  - `delta` = parallax factor. Camera panning × delta = bg scrolling amount.
  - `layerno` = 0 → background (draw before characters), 1 → foreground (after).

Coordinate mapping:
  screen_x = sw/2  +  start_x  -  camera_x × delta_x
  screen_y = zoffset  +  start_y  -  camera_y × delta_y

Ground shadows:
  Simple drop shadow: semi-transparent dark ellipse drawn under each character
  at the ground plane (world_y = 0 → screen_y = zoffset).

Alpha blending:
  Sprites with alpha < 255 use pygame.SRCALPHA surfaces, blitted directly.
  Hit sparks / foreground layers are drawn last (layerno=1) so they appear
  on top of characters.
"""

from typing import TYPE_CHECKING, List, Optional
import pygame

from config import CONFIG

if TYPE_CHECKING:
    from engine.renderer import Renderer
    from mugen.stage_loader import StageLoader


_SKY_COLOR    = (20, 20, 50)
_GROUND_COLOR = (35, 35, 35)


class Stage:
    """In-game stage instance."""

    def __init__(self, loader: "StageLoader"):
        info = loader.info

        self.name        = info.name
        self.sprites     = info.sprites          # SFF reader (may be None)
        self.bg_layers   = info.bg_layers        # List[BgLayer]

        # Exposed to Fight
        self.bound_left  = info.bound_left
        self.bound_right = info.bound_right
        self.start_x     = abs(info.p1_start_x)
        # zoffset: ground Y on the internal 320×240 surface
        self.zoffset     = info.zoffset if info.zoffset > 0 else 180

        # Make sure zoffset is within the game surface height
        gw = CONFIG.video.game_width
        gh = CONFIG.video.game_height
        if self.zoffset <= 0 or self.zoffset >= gh:
            self.zoffset = int(gh * 0.75)   # sensible default: 75% down

        # Auto-scroll accumulator
        self._scroll_x = [float(layer.start[0]) for layer in self.bg_layers]
        self._scroll_y = [float(layer.start[1]) for layer in self.bg_layers]

        print(f"  [Stage] '{self.name}': zoffset={self.zoffset}, "
              f"{len(self.bg_layers)} bg layers, sprites={'yes' if self.sprites else 'NO'}")

    # ------------------------------------------------------------------

    def update(self) -> None:
        for i, layer in enumerate(self.bg_layers):
            self._scroll_x[i] += layer.velocity[0]
            self._scroll_y[i] += layer.velocity[1]

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def render(self, renderer: "Renderer", camera_x: float, camera_y: float) -> None:
        """Draw background layers (layerno=0) and the ground/sky fallback."""
        surf = renderer.get_surface()
        sw, sh = surf.get_size()

        # Sky gradient fallback
        surf.fill(_SKY_COLOR)

        # Ground fill fallback
        gz = self.zoffset
        if 0 < gz < sh:
            pygame.draw.rect(surf, _GROUND_COLOR, (0, gz, sw, sh - gz))

        if self.sprites is not None:
            self._draw_layers(surf, camera_x, camera_y, sw, sh, foreground=False)

    def render_shadows(self, renderer: "Renderer",
                       characters, camera_x: float) -> None:
        """
        Draw ground-plane drop shadows under each character.
        Called after stage background but before character sprites.
        """
        surf  = renderer.get_surface()
        sw, _ = surf.get_size()
        gz    = self.zoffset

        for char in characters:
            cx_world, _ = char.position
            # Screen X using same math as world_to_screen
            cx_screen = int(sw // 2 + cx_world - camera_x)
            # Shadow ellipse: 50px wide, 12px tall, centred at ground Y
            shadow = pygame.Surface((60, 14), pygame.SRCALPHA)
            pygame.draw.ellipse(shadow, (0, 0, 0, 60), (0, 0, 60, 14))
            surf.blit(shadow, (cx_screen - 30, gz - 7))

    def render_foreground(self, renderer: "Renderer",
                           camera_x: float, camera_y: float) -> None:
        """Draw foreground layers (layerno=1) over characters."""
        if self.sprites is not None:
            surf = renderer.get_surface()
            sw, sh = surf.get_size()
            self._draw_layers(surf, camera_x, camera_y, sw, sh, foreground=True)

    # ------------------------------------------------------------------

    def _draw_layers(self, surf: pygame.Surface,
                     camera_x: float, camera_y: float,
                     sw: int, sh: int, foreground: bool) -> None:
        """
        Draw all bg layers matching the foreground flag.
        Uses MUGEN coordinate system:
          screen_x = sw/2 + start_x - camera_x * delta_x
          screen_y = zoffset + start_y - camera_y * delta_y
        """
        for i, layer in enumerate(self.bg_layers):
            if not layer.visible:
                continue

            # layerno: 0=background, 1=foreground
            is_fg = (layer.layerno == 1)
            if is_fg != foreground:
                continue

            sprite = self.sprites.get_sprite(layer.sprite_group, layer.sprite_index)
            if sprite is None:
                continue

            sx = self._scroll_x[i]
            sy = self._scroll_y[i]

            draw_x = int(sw / 2 + sx - camera_x * layer.delta[0])
            draw_y = int(self.zoffset + sy - camera_y * layer.delta[1])

            tw = int(layer.tile[0])
            th = int(layer.tile[1])

            # Apply transparency if the sprite has an alpha channel
            # (pygame handles SRCALPHA surfaces automatically via blit)

            if tw or th:
                self._tile_blit(surf, sprite, draw_x, draw_y, sw, sh, tw, th)
            else:
                surf.blit(sprite, (draw_x, draw_y))

    @staticmethod
    def _tile_blit(dest: pygame.Surface, sprite: pygame.Surface,
                   x: int, y: int,
                   screen_w: int, screen_h: int,
                   tile_x: int, tile_y: int) -> None:
        """Tile a sprite across the destination surface."""
        sw = sprite.get_width()
        sh = sprite.get_height()
        if sw == 0 or sh == 0:
            return

        # Starting position: leftmost/topmost tile that covers the screen
        start_x = (x % sw) - sw if tile_x else x
        start_y = (y % sh) - sh if tile_y else y

        cy = start_y
        while cy < screen_h:
            cx = start_x
            while cx < screen_w:
                dest.blit(sprite, (cx, cy))
                if not tile_x:
                    break
                cx += sw
            if not tile_y:
                break
            cy += sh
