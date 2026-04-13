"""
SDL2-based renderer using pygame.
Software-rendering pipeline — no GPU required.
"""

import pygame
from typing import Optional, Tuple
from config import CONFIG


class Renderer:
    """
    Handles all 2D rendering to the game surface.
    Scales the internal MUGEN-resolution game_surface to the display screen.
    """

    def __init__(self, screen: pygame.Surface, game_surface: pygame.Surface):
        self.screen = screen
        self.game_surface = game_surface

        self._debug = CONFIG.video.show_fps
        self._font: Optional[pygame.font.Font] = None
        # Ground Y in game_surface coordinates. Updated by Fight via set_ground_y().
        self._ground_y: int = CONFIG.video.game_height - 60  # safe default

    # ------------------------------------------------------------------
    # Core drawing helpers
    # ------------------------------------------------------------------

    def get_surface(self) -> pygame.Surface:
        """Return the internal game surface (MUGEN resolution)."""
        return self.game_surface

    def clear(self, color: Tuple[int, int, int] = (0, 0, 0)) -> None:
        """Clear the game surface with a solid color."""
        self.game_surface.fill(color)

    def draw_sprite(
        self,
        surface: pygame.Surface,
        x: float,
        y: float,
        flip_h: bool = False,
        flip_v: bool = False,
        alpha: int = 255,
    ) -> None:
        """
        Blit a sprite onto the game surface at (x, y).

        Coordinates are in MUGEN screen-space (origin top-left of game_surface).
        """
        if surface is None:
            return

        if flip_h or flip_v:
            surface = pygame.transform.flip(surface, flip_h, flip_v)

        if alpha != 255:
            surface = surface.copy()
            surface.set_alpha(alpha)

        self.game_surface.blit(surface, (int(x), int(y)))

    def draw_rect(
        self,
        rect: Tuple[int, int, int, int],
        color: Tuple[int, int, int, int],
        fill: bool = True,
        width: int = 1,
    ) -> None:
        """Draw a rectangle (for debug hitboxes, health bars, etc.)."""
        if fill:
            pygame.draw.rect(self.game_surface, color[:3], rect)
        else:
            pygame.draw.rect(self.game_surface, color[:3], rect, width)

    def draw_line(
        self,
        start: Tuple[int, int],
        end: Tuple[int, int],
        color: Tuple[int, int, int],
        width: int = 1,
    ) -> None:
        """Draw a line onto the game surface."""
        pygame.draw.line(self.game_surface, color, start, end, width)

    def draw_text(
        self,
        text: str,
        x: int,
        y: int,
        color: Tuple[int, int, int] = (255, 255, 255),
        size: int = 16,
    ) -> None:
        """Render a string with pygame's built-in monospace font."""
        font = pygame.font.SysFont("monospace", size)
        surf = font.render(text, True, color)
        self.game_surface.blit(surf, (x, y))

    # ------------------------------------------------------------------
    # World-to-screen coordinate helpers
    # ------------------------------------------------------------------

    def world_to_screen(
        self, world_x: float, world_y: float, camera_x: float = 0.0, camera_y: float = 0.0
    ) -> Tuple[int, int]:
        """
        Convert MUGEN world coordinates to game-surface pixel coordinates.

        MUGEN world:  x=0 is the horizontal center of the stage,
                      y=0 is ground level, y positive = downward (falling).
        Screen:       (0,0) is top-left of game_surface.

        ground_y: screen Y of the ground plane. Updated by Fight via set_ground_y().
        """
        cx = CONFIG.video.game_width // 2
        sx = int(cx + world_x - camera_x)
        sy = int(self._ground_y + world_y - camera_y)
        return sx, sy

    def set_ground_y(self, y: int) -> None:
        """Set the screen Y of the ground plane (from stage zoffset)."""
        self._ground_y = y

    # ------------------------------------------------------------------
    # Debug overlays
    # ------------------------------------------------------------------

    def draw_hitbox(
        self,
        x1: float, y1: float, x2: float, y2: float,
        camera_x: float = 0.0, camera_y: float = 0.0,
        color: Tuple[int, int, int] = (255, 0, 0),
    ) -> None:
        """Draw a collision box in world coordinates (debug mode)."""
        if not self._debug:
            return
        sx1, sy1 = self.world_to_screen(x1, y1, camera_x, camera_y)
        sx2, sy2 = self.world_to_screen(x2, y2, camera_x, camera_y)
        rect = (
            min(sx1, sx2),
            min(sy1, sy2),
            abs(sx2 - sx1),
            abs(sy2 - sy1),
        )
        pygame.draw.rect(self.game_surface, color, rect, 1)
