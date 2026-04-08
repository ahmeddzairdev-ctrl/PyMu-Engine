"""
In-game HUD — health bars, power gauges, timer, round indicator.
"""

import pygame
from typing import TYPE_CHECKING
from config import CONFIG

if TYPE_CHECKING:
    from engine.renderer import Renderer
    from game.character import Character
    from game.fight import Fight, RoundInfo


# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------
_RED    = (220,  30,  30)
_YELLOW = (220, 200,   0)
_GREEN  = ( 30, 200,  30)
_BLUE   = ( 30,  80, 220)
_GRAY   = ( 80,  80,  80)
_WHITE  = (255, 255, 255)
_BLACK  = (  0,   0,   0)


def _lerp_color(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


class HUD:
    """
    Draws the fight HUD onto the renderer's game surface.
    Call render() once per frame after drawing characters.
    """

    BAR_W  = 140
    BAR_H  = 10
    PWR_H  = 6
    MARGIN = 4

    def __init__(self):
        self._font_big   = pygame.font.SysFont("monospace", 20)
        self._font_small = pygame.font.SysFont("monospace", 12)

    def render(self, renderer: "Renderer", fight: "Fight") -> None:
        surf = renderer.get_surface()
        self._draw_lifebar(surf, fight.p1, left=True)
        self._draw_lifebar(surf, fight.p2, left=False)
        self._draw_powerbar(surf, fight.p1, left=True)
        self._draw_powerbar(surf, fight.p2, left=False)
        self._draw_timer(surf, fight.round)
        self._draw_round_info(surf, fight.round)
        self._draw_combos(surf, fight)

    # ------------------------------------------------------------------

    def _draw_lifebar(self, surf: pygame.Surface, char: "Character",
                      left: bool) -> None:
        gw = CONFIG.video.game_width
        if left:
            bar_x = self.MARGIN
        else:
            bar_x = gw - self.MARGIN - self.BAR_W

        bar_y = self.MARGIN

        # Background (empty bar)
        pygame.draw.rect(surf, _GRAY, (bar_x, bar_y, self.BAR_W, self.BAR_H))

        # Filled portion
        ratio = max(0.0, char.life / max(1, char.max_life))
        fill_w = int(self.BAR_W * ratio)

        color = _lerp_color(_RED, _GREEN, ratio)
        if left:
            pygame.draw.rect(surf, color,
                             (bar_x, bar_y, fill_w, self.BAR_H))
        else:
            pygame.draw.rect(surf, color,
                             (bar_x + self.BAR_W - fill_w, bar_y,
                              fill_w, self.BAR_H))

        # Border
        pygame.draw.rect(surf, _WHITE,
                         (bar_x, bar_y, self.BAR_W, self.BAR_H), 1)

        # Name
        name = char.display_name[:10]
        txt  = self._font_small.render(name, True, _WHITE)
        nx   = bar_x if left else bar_x + self.BAR_W - txt.get_width()
        surf.blit(txt, (nx, bar_y + self.BAR_H + 2))

    def _draw_powerbar(self, surf: pygame.Surface, char: "Character",
                       left: bool) -> None:
        gw = CONFIG.video.game_width
        if left:
            bar_x = self.MARGIN
        else:
            bar_x = gw - self.MARGIN - self.BAR_W

        bar_y = self.MARGIN + self.BAR_H + 14

        pygame.draw.rect(surf, _GRAY, (bar_x, bar_y, self.BAR_W, self.PWR_H))
        ratio   = max(0.0, char.power / max(1, char.max_power))
        fill_w  = int(self.BAR_W * ratio)
        if left:
            pygame.draw.rect(surf, _BLUE,
                             (bar_x, bar_y, fill_w, self.PWR_H))
        else:
            pygame.draw.rect(surf, _BLUE,
                             (bar_x + self.BAR_W - fill_w, bar_y,
                              fill_w, self.PWR_H))
        pygame.draw.rect(surf, _WHITE,
                         (bar_x, bar_y, self.BAR_W, self.PWR_H), 1)

    def _draw_timer(self, surf: pygame.Surface, round_info: "RoundInfo") -> None:
        gw = CONFIG.video.game_width
        time_str = str(round_info.time_remaining).zfill(2)
        txt = self._font_big.render(time_str, True, _WHITE)
        surf.blit(txt, (gw // 2 - txt.get_width() // 2, self.MARGIN))

    def _draw_round_info(self, surf: pygame.Surface,
                         round_info: "RoundInfo") -> None:
        gw = CONFIG.video.game_width
        rnd_str = f"Round {round_info.round_number}"
        txt = self._font_small.render(rnd_str, True, _YELLOW)
        surf.blit(txt, (gw // 2 - txt.get_width() // 2, self.MARGIN + 22))

        # Win indicators (dots)
        for i in range(round_info.p1_rounds_won):
            pygame.draw.circle(surf, _YELLOW,
                               (self.MARGIN + 10 + i * 14, self.MARGIN + 34), 4)
        for i in range(round_info.p2_rounds_won):
            pygame.draw.circle(surf, _YELLOW,
                               (gw - self.MARGIN - 10 - i * 14, self.MARGIN + 34), 4)

    def _draw_combos(self, surf: pygame.Surface, fight: "Fight") -> None:
        gw = CONFIG.video.game_width
        gh = CONFIG.video.game_height

        if fight.p1_combo.is_active and fight.p1_combo.hit_count > 1:
            txt = self._font_small.render(
                f"{fight.p1_combo.hit_count} Hits!", True, _YELLOW)
            surf.blit(txt, (self.MARGIN + 10, gh - 40))

        if fight.p2_combo.is_active and fight.p2_combo.hit_count > 1:
            txt = self._font_small.render(
                f"{fight.p2_combo.hit_count} Hits!", True, _YELLOW)
            surf.blit(txt, (gw - self.MARGIN - 60, gh - 40))
