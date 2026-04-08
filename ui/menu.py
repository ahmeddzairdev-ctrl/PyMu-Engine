"""
Main menu and title screen state handlers.
"""

import pygame
from typing import Dict, Any, List
from engine.core import StateHandler, GameTime, GameState
from engine.renderer import Renderer
from engine.input_handler import Button


class TitleHandler(StateHandler):
    """Splash / title screen — press any button to continue."""

    def __init__(self):
        super().__init__()
        self._timer: int = 0
        self._blink:  bool = True

    def on_enter(self, data: Dict[str, Any]) -> None:
        self._timer = 0
        self._blink = True

    def update(self, time: GameTime) -> None:
        self._timer += 1
        self._blink = (self._timer // 30) % 2 == 0

        p1 = self.engine.input_handler.get_player(0)
        if (p1.button_pressed(Button.START) or
                p1.button_pressed(Button.A) or
                p1.button_pressed(Button.B)):
            self.engine.change_state(GameState.MAIN_MENU)

    def render(self, renderer: Renderer) -> None:
        from config import CONFIG
        cx = CONFIG.video.game_width  // 2
        cy = CONFIG.video.game_height // 2

        renderer.draw_text("PyMugen Engine",  cx - 56, cy - 30, (255, 255, 255), 16)
        if self._blink:
            renderer.draw_text("Press Start",  cx - 36, cy + 10, (200, 200, 0),  12)


# ---------------------------------------------------------------------------

class MainMenuHandler(StateHandler):
    """Main menu with navigable items."""

    ITEMS: List[str] = [
        "Arcade",
        "Versus",
        "Survival",
        "Training",
        "Online",
        "Options",
        "Exit",
    ]

    def __init__(self):
        super().__init__()
        self._cursor: int = 0
        self._delay:  int = 0   # Debounce delay in ticks

    def on_enter(self, data: Dict[str, Any]) -> None:
        self._cursor = 0
        self._delay  = 0

    def update(self, time: GameTime) -> None:
        p1 = self.engine.input_handler.get_player(0)

        if self._delay > 0:
            self._delay -= 1
            return

        if p1.button_pressed(Button.UP):
            self._cursor = (self._cursor - 1) % len(self.ITEMS)
            self._delay  = 10
        elif p1.button_pressed(Button.DOWN):
            self._cursor = (self._cursor + 1) % len(self.ITEMS)
            self._delay  = 10
        elif p1.button_pressed(Button.A) or p1.button_pressed(Button.START):
            self._select()

    def _select(self) -> None:
        choice = self.ITEMS[self._cursor]
        if choice == "Arcade":
            self.engine.change_state(GameState.CHARACTER_SELECT,
                                     {"mode": "arcade"})
        elif choice == "Versus":
            self.engine.change_state(GameState.CHARACTER_SELECT,
                                     {"mode": "versus"})
        elif choice == "Survival":
            self.engine.change_state(GameState.CHARACTER_SELECT,
                                     {"mode": "survival"})
        elif choice == "Training":
            self.engine.change_state(GameState.CHARACTER_SELECT,
                                     {"mode": "training"})
        elif choice == "Online":
            self.engine.change_state(GameState.NETWORK_LOBBY)
        elif choice == "Options":
            self.engine.change_state(GameState.OPTIONS)
        elif choice == "Exit":
            self.engine.running = False

    def render(self, renderer: Renderer) -> None:
        from config import CONFIG
        cx = CONFIG.video.game_width // 2
        y_start = 60

        renderer.draw_text("Main Menu", cx - 32, 20, (255, 215, 0), 16)

        for i, item in enumerate(self.ITEMS):
            color  = (255, 255, 255) if i != self._cursor else (255, 255, 0)
            prefix = "> " if i == self._cursor else "  "
            renderer.draw_text(f"{prefix}{item}", cx - 48, y_start + i * 22,
                                color, 14)
