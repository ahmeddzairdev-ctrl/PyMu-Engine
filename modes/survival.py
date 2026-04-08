"""
Survival mode — fight an endless stream of CPU opponents.
Life does NOT reset between rounds; only power and timer refresh.
"""

import random
from typing import Dict, Any, Optional
from engine.core import StateHandler, GameTime, GameState
from engine.renderer import Renderer


class SurvivalMode(StateHandler):

    def __init__(self, content_manager):
        super().__init__()
        self.content_manager = content_manager
        self._fight = None
        self._p1_char = None
        self._wins: int = 0

    def on_enter(self, data: Dict[str, Any]) -> None:
        p1_info = data.get("p1_character")
        if p1_info is None:
            self.engine.change_state(GameState.MAIN_MENU)
            return

        loader = self.content_manager.load_character(p1_info["path"])
        if loader is None:
            self.engine.change_state(GameState.MAIN_MENU)
            return

        from game.character import Character
        self._p1_char = Character(loader)
        self._wins    = 0
        self._start_next_round()

    def on_exit(self) -> None:
        self._fight = None

    def update(self, time: GameTime) -> None:
        if self._fight is None:
            return

        p1_input = self.engine.input_handler.get_player(0)
        cpu_input = self._get_cpu_input()
        self._fight.update(p1_input, cpu_input)

        from game.fight import FightState, RoundResult
        if self._fight.state == FightState.MATCH_END:
            if self._fight.round.result in (
                RoundResult.P1_WIN, RoundResult.TIME_OVER_P1
            ):
                self._wins += 1
                print(f"SurvivalMode: win #{self._wins}")
                # Partially restore P1 life
                self._p1_char.life = min(
                    self._p1_char.max_life,
                    self._p1_char.life + self._p1_char.max_life // 5,
                )
                self._start_next_round()
            else:
                print(f"SurvivalMode: defeated after {self._wins} wins")
                self.engine.change_state(GameState.MAIN_MENU)

    def render(self, renderer: Renderer) -> None:
        if self._fight:
            self._fight.render(renderer)

    # ------------------------------------------------------------------

    def _start_next_round(self) -> None:
        roster = self.content_manager.get_character_list()
        if not roster:
            self.engine.change_state(GameState.MAIN_MENU)
            return

        cpu_info = random.choice(roster)
        loader   = self.content_manager.load_character(cpu_info["path"])
        if loader is None:
            return

        from game.character import Character
        from game.ai import AI
        from config import CONFIG
        cpu_char     = Character(loader)
        cpu_char._ai = AI(level=min(8, CONFIG.gameplay.default_ai_level + self._wins // 3))

        from game.fight import Fight
        self._fight = Fight(self._p1_char, cpu_char, self._make_dummy_stage())

    def _get_cpu_input(self):
        if self._fight and hasattr(self._fight.p2, "_ai"):
            return self._fight.p2._ai.update(self._fight.p2, self._fight.p1)
        return self.engine.input_handler.get_player(1)

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
