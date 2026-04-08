"""
Local 2-player versus mode.
Both players use local input (keyboard / gamepad).
"""

from typing import Dict, Any, Optional
from engine.core import StateHandler, GameTime, GameState
from engine.renderer import Renderer


class VersusMode(StateHandler):
    """Head-to-head local match."""

    def __init__(self, content_manager):
        super().__init__()
        self.content_manager = content_manager
        self._fight = None

    def on_enter(self, data: Dict[str, Any]) -> None:
        p1_info = data.get("p1_character")
        p2_info = data.get("p2_character")
        stage_info = data.get("stage")

        if not p1_info or not p2_info:
            print("VersusMode: missing character selection — returning to menu")
            self.engine.change_state(GameState.MAIN_MENU)
            return

        p1 = self._load_char(p1_info)
        p2 = self._load_char(p2_info)

        if p1 is None or p2 is None:
            self.engine.change_state(GameState.MAIN_MENU)
            return

        stage = self._load_stage(stage_info)
        if stage is None:
            stage = self._make_dummy_stage()

        from game.fight import Fight
        self._fight = Fight(p1, p2, stage)

    def on_exit(self) -> None:
        self._fight = None

    def update(self, time: GameTime) -> None:
        if self._fight is None:
            return

        p1_input = self.engine.input_handler.get_player(0)
        p2_input = self.engine.input_handler.get_player(1)
        self._fight.update(p1_input, p2_input)

        from game.fight import FightState
        if self._fight.state == FightState.MATCH_END:
            self.engine.change_state(GameState.MAIN_MENU)

    def render(self, renderer: Renderer) -> None:
        if self._fight:
            self._fight.render(renderer)

    # ------------------------------------------------------------------

    def _load_char(self, info: Dict[str, Any]):
        loader = self.content_manager.load_character(info["path"])
        if loader is None:
            return None
        from game.character import Character
        return Character(loader)

    def _load_stage(self, info: Optional[Dict[str, Any]]):
        if info is None:
            return None
        try:
            from mugen.stage_loader import StageLoader
            from game.stage import Stage
            return Stage(StageLoader.load(info["def"]))
        except Exception as e:
            print(f"VersusMode: failed to load stage: {e}")
            return None

    @staticmethod
    def _make_dummy_stage():
        from unittest.mock import MagicMock
        stage = MagicMock()
        stage.bound_left  = -200
        stage.bound_right = 200
        stage.start_x     = 70
        stage.render      = lambda *a: None
        stage.render_foreground = lambda *a: None
        return stage
