"""
Character and stage selection screen.
"""

import pygame
from typing import Dict, Any, List, Optional
from engine.core import StateHandler, GameTime, GameState
from engine.renderer import Renderer
from engine.input_handler import Button


class CharacterSelectHandler(StateHandler):
    """
    Grid-based character select screen.

    Flow:
      1. P1 picks a character (and P2 if versus/training)
      2. A random or first available stage is chosen
      3. Engine transitions to FIGHT with the selections in state data
    """

    COLS = 5   # Characters per row

    def __init__(self, content_manager):
        super().__init__()
        self.content_manager = content_manager

        self._mode: str      = "arcade"
        self._roster: List[Dict[str, Any]] = []
        self._stages: List[Dict[str, Any]] = []

        # Selection state for P1 and P2
        self._p1_idx:     int  = 0
        self._p2_idx:     int  = 0
        self._p1_done:    bool = False
        self._p2_done:    bool = False
        self._stage_idx:  int  = 0
        self._debounce:   Dict[int, int] = {0: 0, 1: 0}

    # ------------------------------------------------------------------

    def on_enter(self, data: Dict[str, Any]) -> None:
        self._mode     = data.get("mode", "arcade")
        self._p1_done  = False
        self._p2_done  = False
        self._p1_idx   = 0
        self._p2_idx   = 0

        self._roster = self.content_manager.get_character_list()
        self._stages = self.content_manager.get_stage_list()

    # ------------------------------------------------------------------

    def update(self, time: GameTime) -> None:
        if not self._roster:
            # No characters found — go back
            self.engine.change_state(GameState.MAIN_MENU)
            return

        self._handle_player_input(0)

        needs_p2 = self._mode in ("versus", "training")
        if needs_p2:
            self._handle_player_input(1)

        # Confirm when all required selections are made
        if self._p1_done and (not needs_p2 or self._p2_done):
            self._confirm()

    def _handle_player_input(self, player_id: int) -> None:
        if self._debounce[player_id] > 0:
            self._debounce[player_id] -= 1
            return

        p = self.engine.input_handler.get_player(player_id)
        done_attr = "_p1_done" if player_id == 0 else "_p2_done"

        if getattr(self, done_attr):
            return

        idx_attr = "_p1_idx" if player_id == 0 else "_p2_idx"
        idx = getattr(self, idx_attr)

        moved = False
        if p.button_pressed(Button.LEFT):
            idx = max(0, idx - 1);           moved = True
        elif p.button_pressed(Button.RIGHT):
            idx = min(len(self._roster) - 1, idx + 1); moved = True
        elif p.button_pressed(Button.UP):
            idx = max(0, idx - self.COLS);   moved = True
        elif p.button_pressed(Button.DOWN):
            idx = min(len(self._roster) - 1, idx + self.COLS); moved = True

        if moved:
            setattr(self, idx_attr, idx)
            self._debounce[player_id] = 10

        if p.button_pressed(Button.A) or p.button_pressed(Button.START):
            setattr(self, done_attr, True)

        if p.button_pressed(Button.BACK) and not getattr(self, done_attr):
            self.engine.change_state(GameState.MAIN_MENU)

    def _confirm(self) -> None:
        import random
        p1_char  = self._roster[self._p1_idx]
        p2_char  = self._roster[self._p2_idx]
        stage    = (random.choice(self._stages) if self._stages else None)

        target_state = {
            "arcade":   GameState.FIGHT,
            "versus":   GameState.FIGHT,
            "survival": GameState.FIGHT,
            "training": GameState.FIGHT,
        }.get(self._mode, GameState.FIGHT)

        self.engine.change_state(target_state, {
            "mode":         self._mode,
            "p1_character": p1_char,
            "p2_character": p2_char,
            "stage":        stage,
        })

    # ------------------------------------------------------------------

    def render(self, renderer: Renderer) -> None:
        from config import CONFIG
        renderer.draw_text("Select Character", 4, 4, (255, 215, 0), 14)

        for i, char in enumerate(self._roster):
            col = i % self.COLS
            row = i // self.COLS
            x = 10 + col * 58
            y = 30 + row * 30

            color = (180, 180, 180)
            if i == self._p1_idx:
                color = (0, 200, 255)
            if i == self._p2_idx:
                color = (255, 80, 80) if self._p2_idx != self._p1_idx else (200, 0, 200)

            renderer.draw_text(char["name"][:7], x, y, color, 10)

        # Show current selections
        if self._roster:
            p1_name = self._roster[self._p1_idx]["name"]
            renderer.draw_text(f"P1: {p1_name}", 4,
                                CONFIG.video.game_height - 30, (0, 200, 255), 12)

            if self._mode in ("versus", "training"):
                p2_name = self._roster[self._p2_idx]["name"]
                renderer.draw_text(f"P2: {p2_name}",
                                   CONFIG.video.game_width // 2,
                                   CONFIG.video.game_height - 30,
                                   (255, 80, 80), 12)
