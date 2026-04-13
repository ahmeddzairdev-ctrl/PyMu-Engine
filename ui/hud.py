"""
In-game HUD — MUGEN-style health/power bars, timer, round indicator.

Renders directly onto the game_surface (internal 320×240 resolution).
All positions are expressed in internal pixels and scale automatically
when the surface is upscaled to the display resolution.

Layout (at 320×240):
  P1 lifebar:   x=4,   y=6  (left-aligned, fills right)
  P2 lifebar:   x=176, y=6  (right-aligned, fills left)
  Timer:        x=160, y=4  (centred)
  Power bars:   below life bars
  Round wins:   small dots near timer
"""

import pygame
from typing import TYPE_CHECKING, Optional, Tuple
from config import CONFIG

if TYPE_CHECKING:
    from engine.renderer import Renderer
    from game.character import Character
    from game.fight import Fight, RoundInfo, ComboInfo

# ── Palette ──────────────────────────────────────────────────────────────────
_C_BG       = (10,  10,  10)    # bar background
_C_BORDER   = (200, 200, 200)   # bar border
_C_LIFE_HI  = (0,   200,  30)   # full health
_C_LIFE_MID = (220, 200,   0)   # ~50 %
_C_LIFE_LOW = (220,  30,  30)   # danger
_C_POWER    = ( 30,  80, 220)
_C_WHITE    = (255, 255, 255)
_C_YELLOW   = (255, 210,   0)
_C_RED      = (220,  30,  30)
_C_SHADOW   = (0,    0,   0)

# ── Bar geometry (internal-pixel units) ──────────────────────────────────────
_BAR_W   = 132   # lifebar width
_BAR_H   = 9     # lifebar height
_PWR_H   = 5     # powerbar height
_MARGIN  = 4     # edge margin
_NAME_Y  = 1     # name label Y
_LIFE_Y  = 10    # lifebar Y
_PWR_Y   = 20    # powerbar Y
# P1 bar starts at _MARGIN.  P2 bar ends at game_width - _MARGIN.
_P2_X    = CONFIG.video.game_width - _MARGIN - _BAR_W   # left edge of P2 bar


def _life_color(ratio: float) -> Tuple[int, int, int]:
    ratio = max(0.0, min(1.0, ratio))
    if ratio > 0.5:
        t = (ratio - 0.5) * 2
        r = int(_C_LIFE_MID[0] * (1 - t) + _C_LIFE_HI[0] * t)
        g = int(_C_LIFE_MID[1] * (1 - t) + _C_LIFE_HI[1] * t)
        b = int(_C_LIFE_MID[2] * (1 - t) + _C_LIFE_HI[2] * t)
    else:
        t = ratio * 2
        r = int(_C_LIFE_LOW[0] * (1 - t) + _C_LIFE_MID[0] * t)
        g = int(_C_LIFE_LOW[1] * (1 - t) + _C_LIFE_MID[1] * t)
        b = int(_C_LIFE_LOW[2] * (1 - t) + _C_LIFE_MID[2] * t)
    return (r, g, b)


class HUD:
    def __init__(self):
        pygame.font.init()
        # All fonts sized for internal 320×240 resolution
        self._fn  = pygame.font.SysFont("monospace",  8)   # small (names, values)
        self._fm  = pygame.font.SysFont("monospace", 11)   # medium (combo, round text)
        self._fl  = pygame.font.SysFont("monospace", 14, bold=True)  # large (timer, KO)

    # ── Public entry point ───────────────────────────────────────────────────

    def render(self, renderer: "Renderer", fight: "Fight") -> None:
        surf = renderer.get_surface()
        gw   = CONFIG.video.game_width    # 320
        gh   = CONFIG.video.game_height   # 240

        p1, p2 = fight.p1, fight.p2
        rnd    = fight.round

        self._draw_hud_background(surf, gw)
        self._draw_lifebar(surf, p1, left=True)
        self._draw_lifebar(surf, p2, left=False)
        self._draw_powerbar(surf, p1, left=True)
        self._draw_powerbar(surf, p2, left=False)
        self._draw_names(surf, p1, p2, gw)
        self._draw_timer(surf, rnd, gw)
        self._draw_round_wins(surf, rnd, gw)
        self._draw_combo(surf, fight, gw, gh)
        self._draw_round_message(surf, fight, gw, gh)

    # ── HUD background strip ─────────────────────────────────────────────────

    def _draw_hud_background(self, surf: pygame.Surface, gw: int) -> None:
        strip_h = _PWR_Y + _PWR_H + 3
        pygame.draw.rect(surf, _C_BG,     (0, 0, gw, strip_h))
        pygame.draw.rect(surf, (30,30,30), (0, strip_h, gw, 1))  # separator line

    # ── Life bars ────────────────────────────────────────────────────────────

    def _draw_lifebar(self, surf: pygame.Surface,
                      char: "Character", left: bool) -> None:
        bx = _MARGIN if left else _P2_X

        # Background (empty bar)
        pygame.draw.rect(surf, (50, 50, 50), (bx, _LIFE_Y, _BAR_W, _BAR_H))

        # Filled portion
        ratio  = max(0.0, char.life / max(1, char.max_life))
        fill_w = int(_BAR_W * ratio)
        color  = _life_color(ratio)

        if left:
            pygame.draw.rect(surf, color, (bx, _LIFE_Y, fill_w, _BAR_H))
        else:
            pygame.draw.rect(surf, color,
                             (bx + _BAR_W - fill_w, _LIFE_Y, fill_w, _BAR_H))

        # Border
        pygame.draw.rect(surf, _C_BORDER, (bx, _LIFE_Y, _BAR_W, _BAR_H), 1)

        # HP number (small, inside bar)
        hp_str = str(char.life)
        hp_txt = self._fn.render(hp_str, True, _C_WHITE)
        if left:
            surf.blit(hp_txt, (bx + 2, _LIFE_Y + 1))
        else:
            surf.blit(hp_txt, (bx + _BAR_W - hp_txt.get_width() - 2, _LIFE_Y + 1))

    # ── Power bars ───────────────────────────────────────────────────────────

    def _draw_powerbar(self, surf: pygame.Surface,
                       char: "Character", left: bool) -> None:
        bx = _MARGIN if left else _P2_X

        pygame.draw.rect(surf, (30, 30, 50), (bx, _PWR_Y, _BAR_W, _PWR_H))

        ratio  = max(0.0, char.power / max(1, char.max_power))
        fill_w = int(_BAR_W * ratio)
        if left:
            pygame.draw.rect(surf, _C_POWER, (bx, _PWR_Y, fill_w, _PWR_H))
        else:
            pygame.draw.rect(surf, _C_POWER,
                             (bx + _BAR_W - fill_w, _PWR_Y, fill_w, _PWR_H))

        pygame.draw.rect(surf, _C_BORDER, (bx, _PWR_Y, _BAR_W, _PWR_H), 1)

    # ── Names ────────────────────────────────────────────────────────────────

    def _draw_names(self, surf: pygame.Surface,
                    p1: "Character", p2: "Character", gw: int) -> None:
        n1 = p1.display_name[:14]
        n2 = p2.display_name[:14]
        t1 = self._fn.render(n1, True, (180, 220, 255))
        t2 = self._fn.render(n2, True, (255, 180, 180))
        surf.blit(t1, (_MARGIN, _NAME_Y))
        surf.blit(t2, (gw - _MARGIN - t2.get_width(), _NAME_Y))

    # ── Timer ────────────────────────────────────────────────────────────────

    def _draw_timer(self, surf: pygame.Surface,
                    rnd: "RoundInfo", gw: int) -> None:
        t   = str(rnd.time_remaining).zfill(2)
        col = _C_RED if rnd.time_remaining <= 10 else _C_WHITE
        txt = self._fl.render(t, True, col)
        # Drop shadow
        shd = self._fl.render(t, True, _C_SHADOW)
        cx  = gw // 2 - txt.get_width() // 2
        surf.blit(shd, (cx + 1, _NAME_Y + 1))
        surf.blit(txt, (cx,     _NAME_Y))

    # ── Round wins (small dots) ───────────────────────────────────────────────

    def _draw_round_wins(self, surf: pygame.Surface,
                         rnd: "RoundInfo", gw: int) -> None:
        cx = gw // 2
        y  = _LIFE_Y + _BAR_H + 3
        r  = 2
        gap = 7
        for i in range(rnd.p1_rounds_won):
            pygame.draw.circle(surf, _C_YELLOW, (cx - 18 - i * gap, y), r)
        for i in range(rnd.p2_rounds_won):
            pygame.draw.circle(surf, _C_YELLOW, (cx + 18 + i * gap, y), r)

    # ── Combo counter ────────────────────────────────────────────────────────

    def _draw_combo(self, surf: pygame.Surface, fight: "Fight",
                    gw: int, gh: int) -> None:
        from game.fight import FightState
        if fight.state != FightState.FIGHTING:
            return

        c1, c2 = fight.p1_combo, fight.p2_combo
        y = gh - 40

        if c1.is_active and c1.hit_count > 1:
            txt = self._fm.render(f"{c1.hit_count} Hits!", True, _C_YELLOW)
            surf.blit(txt, (_MARGIN + 4, y))

        if c2.is_active and c2.hit_count > 1:
            txt = self._fm.render(f"{c2.hit_count} Hits!", True, _C_YELLOW)
            surf.blit(txt, (gw - _MARGIN - txt.get_width() - 4, y))

    # ── Round / KO / Win messages ────────────────────────────────────────────

    def _draw_round_message(self, surf: pygame.Surface, fight: "Fight",
                             gw: int, gh: int) -> None:
        from game.fight import FightState, RoundResult

        cx = gw // 2
        cy = gh // 2 - 16

        def centred(text: str, y: int, color: Tuple, font=None) -> None:
            f   = font or self._fl
            shd = f.render(text, True, _C_SHADOW)
            txt = f.render(text, True, color)
            surf.blit(shd, (cx - txt.get_width() // 2 + 1, y + 1))
            surf.blit(txt, (cx - txt.get_width() // 2,     y))

        st = fight.state

        if st == FightState.ROUND_START:
            t = fight.state_timer
            rno = fight.round.round_number
            if t < 60:
                centred(f"Round {rno}", cy - 10, _C_WHITE)
            if t > 45:
                centred("FIGHT!", cy + 8, _C_YELLOW)

        elif st == FightState.KO:
            result = fight.round.result
            if result == RoundResult.DOUBLE_KO:
                centred("DOUBLE K.O.", cy, _C_RED)
            elif result in (RoundResult.TIME_OVER_P1, RoundResult.TIME_OVER_P2):
                centred("TIME OVER", cy, _C_YELLOW)
            elif result == RoundResult.DRAW:
                centred("DRAW", cy, _C_YELLOW)
            else:
                centred("K.O.", cy, _C_RED)

        elif st == FightState.MATCH_END:
            result = fight.round.result
            if result in (RoundResult.P1_WIN, RoundResult.TIME_OVER_P1):
                winner = fight.p1.display_name
            elif result in (RoundResult.P2_WIN, RoundResult.TIME_OVER_P2):
                winner = fight.p2.display_name
            else:
                winner = ""

            if winner:
                centred(f"{winner[:14]} WINS!", cy, _C_YELLOW)
