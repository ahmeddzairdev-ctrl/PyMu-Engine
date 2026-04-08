"""
Arcade / story mode.
The player fights a series of CPU opponents drawn from the content roster.
"""

import random
from typing import List, Optional, Dict, Any

from engine.core import StateHandler, GameTime, GameState
from engine.renderer import Renderer


class ArcadeMode(StateHandler):
    """Arcade mode: fight through a random roster until all opponents are beaten."""

    def __init__(self, content_manager):
        super().__init__()
        self.content_manager = content_manager

        self._opponent_list: List[Dict[str, Any]] = []
        self._current_index: int = 0
        self._fight = None
        self._p1_char = None

    # ------------------------------------------------------------------

    def on_enter(self, data: Dict[str, Any]) -> None:
        p1_info = data.get("p1_character")
        stage_info = data.get("stage")

        if p1_info is None:
            print("ArcadeMode: no P1 character selected — returning to menu")
            self.engine.change_state(GameState.MAIN_MENU)
            return

        # Build opponent list
        roster = self.content_manager.get_character_list()
        self._opponent_list = [c for c in roster
                               if c["name"] != p1_info.get("name")]
        random.shuffle(self._opponent_list)

        self._current_index = 0

        # Load P1
        self._p1_char = self._load_char(p1_info)
        if self._p1_char is None:
            self.engine.change_state(GameState.MAIN_MENU)
            return

        self._start_next_fight(stage_info)

    def on_exit(self) -> None:
        self._fight = None

    # ------------------------------------------------------------------

    def update(self, time: GameTime) -> None:
        if self._fight is None:
            return

        p1_input = self.engine.input_handler.get_player(0)

        # Generate CPU input
        cpu_input = self._fight.p2._ai.update(
            self._fight.p2, self._fight.p1
        ) if hasattr(self._fight.p2, "_ai") else p1_input  # fallback

        self._fight.update(p1_input, cpu_input)

        from game.fight import FightState
        if self._fight.state == FightState.MATCH_END:
            self._on_match_end()

    def render(self, renderer: Renderer) -> None:
        if self._fight:
            self._fight.render(renderer)

    # ------------------------------------------------------------------

    def _start_next_fight(self, stage_info: Optional[Dict] = None) -> None:
        if self._current_index >= len(self._opponent_list):
            print("ArcadeMode: congratulations — all opponents defeated!")
            self.engine.change_state(GameState.MAIN_MENU)
            return

        opp_info = self._opponent_list[self._current_index]
        cpu_char = self._load_char(opp_info)
        if cpu_char is None:
            self._current_index += 1
            self._start_next_fight(stage_info)
            return

        # Attach a simple AI to the CPU character
        from game.ai import AI
        from config import CONFIG
        cpu_char._ai = AI(level=CONFIG.gameplay.default_ai_level)

        stage = self._load_stage(stage_info)
        if stage is None:
            stage = self._make_dummy_stage()

        from game.fight import Fight
        self._fight = Fight(self._p1_char, cpu_char, stage)

    def _on_match_end(self) -> None:
        from game.fight import RoundResult
        if self._fight.round.result in (
            __import__("game.fight", fromlist=["RoundResult"]).RoundResult.P1_WIN,
            __import__("game.fight", fromlist=["RoundResult"]).RoundResult.TIME_OVER_P1,
        ):
            self._current_index += 1
            self._start_next_fight()
        else:
            # P1 lost — game over
            print("ArcadeMode: P1 lost — returning to menu")
            self.engine.change_state(GameState.MAIN_MENU)

    # ------------------------------------------------------------------

    def _load_char(self, info: Dict[str, Any]):
        loader = self.content_manager.load_character(info["path"])
        if loader is None:
            return None
        from game.character import Character
        return Character(loader)

    def _load_stage(self, info: Optional[Dict[str, Any]]):
        if info is None:
            stages = self.content_manager.get_stage_list()
            if stages:
                info = random.choice(stages)
            else:
                return None
        try:
            from mugen.stage_loader import StageLoader
            from game.stage import Stage
            return Stage(StageLoader.load(info["def"]))
        except Exception as e:
            print(f"ArcadeMode: failed to load stage: {e}")
            return None

    @staticmethod
    def _make_dummy_stage():
        """Return a minimal Stage with no graphics (for testing)."""
        from unittest.mock import MagicMock
        stage = MagicMock()
        stage.bound_left  = -200
        stage.bound_right = 200
        stage.start_x     = 70
        stage.render      = lambda *a: None
        stage.render_foreground = lambda *a: None
        return stage
