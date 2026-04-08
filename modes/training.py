"""
Training mode — P1 fights a CPU dummy with configurable behaviour.
"""

from typing import Dict, Any, Optional
from engine.core import StateHandler, GameTime, GameState
from engine.renderer import Renderer


class TrainingMode(StateHandler):

    # Dummy behaviours
    DUMMY_STAND  = "stand"
    DUMMY_CROUCH = "crouch"
    DUMMY_JUMP   = "jump"
    DUMMY_BLOCK  = "block"
    DUMMY_CPU    = "cpu"

    def __init__(self, content_manager):
        super().__init__()
        self.content_manager = content_manager
        self._fight = None
        self.dummy_behaviour: str = self.DUMMY_STAND

    def on_enter(self, data: Dict[str, Any]) -> None:
        p1_info  = data.get("p1_character")
        p2_info  = data.get("p2_character")
        stage_info = data.get("stage")

        if not p1_info or not p2_info:
            self.engine.change_state(GameState.MAIN_MENU)
            return

        p1 = self._load_char(p1_info)
        p2 = self._load_char(p2_info)
        if p1 is None or p2 is None:
            self.engine.change_state(GameState.MAIN_MENU)
            return

        self.dummy_behaviour = data.get("dummy_behaviour", self.DUMMY_STAND)

        stage = self._load_stage(stage_info) or self._make_dummy_stage()

        from game.fight import Fight
        self._fight = Fight(p1, p2, stage)
        # Training mode: infinite time, no rounds
        self._fight.round.time_remaining = 0
        self._fight.round.time_ticks = 0

    def on_exit(self) -> None:
        self._fight = None

    def update(self, time: GameTime) -> None:
        if self._fight is None:
            return

        p1_input  = self.engine.input_handler.get_player(0)
        cpu_input = self._dummy_input()
        self._fight.update(p1_input, cpu_input)

        # Auto-regenerate dummy life
        if self._fight.p2.life <= 0:
            self._fight.p2.life = self._fight.p2.max_life
            self._fight.p2.change_state(0)

        # ESC → return to menu
        from engine.input_handler import Button
        if p1_input.button_pressed(Button.BACK):
            self.engine.change_state(GameState.MAIN_MENU)

    def render(self, renderer: Renderer) -> None:
        if self._fight:
            self._fight.render(renderer)

    # ------------------------------------------------------------------

    def _dummy_input(self):
        """Produce synthetic input for the training dummy."""
        from engine.input_handler import Button, InputFrame

        class _DummyInput:
            def __init__(self, buttons: Button):
                self.current = InputFrame(buttons=buttons)
            def button_held(self, b):    return bool(self.current.buttons & b)
            def button_pressed(self, b): return False
            def button_released(self, b): return False
            def command_active(self, n): return False

        if self._fight is None:
            return _DummyInput(Button.NONE)

        b = Button.NONE
        if self.dummy_behaviour == self.DUMMY_CROUCH:
            b = Button.DOWN
        elif self.dummy_behaviour == self.DUMMY_JUMP:
            b = Button.UP
        elif self.dummy_behaviour == self.DUMMY_BLOCK:
            # Block = hold back relative to facing
            b = Button.LEFT if self._fight.p2.facing > 0 else Button.RIGHT
        elif self.dummy_behaviour == self.DUMMY_CPU:
            if hasattr(self._fight.p2, "_ai"):
                return self._fight.p2._ai.update(self._fight.p2, self._fight.p1)

        return _DummyInput(b)

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
        except Exception:
            return None

    @staticmethod
    def _make_dummy_stage():
        from unittest.mock import MagicMock
        s = MagicMock()
        s.bound_left  = -200
        s.bound_right = 200
        s.start_x     = 70
        s.render      = lambda *a: None
        s.render_foreground = lambda *a: None
        return s
