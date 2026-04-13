"""Minimal fallback stage used when no stage file is available."""

import pygame
from config import CONFIG


class DummyStage:
    """A plain-colour stage for when no .def file loads successfully."""

    def __init__(self):
        self.bound_left  = -200
        self.bound_right =  200
        self.start_x     =   70
        # Use 75% of game height as ground — matches common MUGEN zoffset
        self.zoffset     = int(CONFIG.video.game_height * 0.75)
        self.name        = "Training"
        self.bg_layers   = []
        self.sprites     = None

    def update(self) -> None:
        pass

    def render(self, renderer, camera_x: float, camera_y: float) -> None:
        surf = renderer.get_surface()
        sw, sh = surf.get_size()
        gz = self.zoffset
        surf.fill((20, 20, 50))
        if 0 < gz < sh:
            pygame.draw.rect(surf, (35, 35, 35), (0, gz, sw, sh - gz))

    def render_shadows(self, renderer, characters, camera_x: float) -> None:
        surf = renderer.get_surface()
        sw   = surf.get_width()
        gz   = self.zoffset
        for char in characters:
            cx_world, _ = char.position
            cx_screen = int(sw // 2 + cx_world - camera_x)
            shadow = pygame.Surface((60, 14), pygame.SRCALPHA)
            pygame.draw.ellipse(shadow, (0, 0, 0, 55), (0, 0, 60, 14))
            surf.blit(shadow, (cx_screen - 30, gz - 7))

    def render_foreground(self, renderer, camera_x: float, camera_y: float) -> None:
        pass
