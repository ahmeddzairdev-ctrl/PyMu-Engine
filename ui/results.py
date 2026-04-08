"""
Round and match results screen.
"""

import pygame
from typing import Dict, Any, TYPE_CHECKING
from engine.core import StateHandler, GameTime, GameState
from engine.renderer import Renderer
from engine.input_handler import Button

if TYPE_CHECKING:
    from game.fight import Fight, RoundResult


class ResultsHandler(StateHandler):
    """Shows the outcome of a match and returns to the menu."""

    def __init__(self):
        super().__init__()
        self._timer:   int  = 0
        self._winner:  str  = ""
        self._p1_wins: int  = 0
        self._p2_wins: int  = 0
        self._auto_exit: int = 300   # Auto-advance after 5 seconds

    def on_enter(self, data: Dict[str, Any]) -> None:
        self._timer  = 0
        self._winner = data.get("winner", "")
        self._p1_wins = data.get("p1_wins", 0)
        self._p2_wins = data.get("p2_wins", 0)

    def update(self, time: GameTime) -> None:
        self._timer += 1

        p1 = self.engine.input_handler.get_player(0)
        if (p1.button_pressed(Button.START) or
                p1.button_pressed(Button.A) or
                self._timer >= self._auto_exit):
            self.engine.change_state(GameState.MAIN_MENU)

    def render(self, renderer: Renderer) -> None:
        from config import CONFIG
        cx = CONFIG.video.game_width  // 2
        cy = CONFIG.video.game_height // 2

        renderer.draw_text("Match Over",  cx - 36, cy - 40, (255, 215, 0), 16)

        if self._winner:
            renderer.draw_text(f"{self._winner} Wins!",
                               cx - 40, cy - 10, (255, 255, 255), 14)

        renderer.draw_text(
            f"P1: {self._p1_wins}  P2: {self._p2_wins}",
            cx - 48, cy + 20, (180, 180, 180), 12,
        )

        blink = (self._timer // 20) % 2 == 0
        if blink:
            renderer.draw_text("Press Start", cx - 36, cy + 50,
                               (200, 200, 0), 12)
