"""
AI opponent logic.
Implements a simple rule-based AI that maps to MUGEN AI level 1-8.
"""

import random
from typing import TYPE_CHECKING, Optional

from engine.input_handler import Button, InputFrame, PlayerInput

if TYPE_CHECKING:
    from game.character import Character
    from game.fight import Fight


class AIInput:
    """
    Synthetic PlayerInput produced by the AI each tick.
    Mimics the PlayerInput interface so Fight.update() can use it transparently.
    """

    def __init__(self):
        self._frame = InputFrame()
        self._prev  = InputFrame()

    def feed(self, frame: InputFrame) -> None:
        self._prev  = self._frame
        self._frame = frame

    # Mirror the PlayerInput query interface
    def button_held(self, button: Button) -> bool:
        return bool(self._frame.buttons & button)

    def button_pressed(self, button: Button) -> bool:
        return bool(self._frame.buttons_pressed & button)

    def button_released(self, button: Button) -> bool:
        return bool(self._frame.buttons_released & button)

    def command_active(self, name: str) -> bool:
        return False   # AI does not use the command buffer

    @property
    def current(self) -> InputFrame:
        return self._frame


class AI:
    """
    Rule-based AI controller.

    level 1-3  → random / reactive
    level 4-6  → opportunistic (rushes when safe, blocks high attacks)
    level 7-8  → aggressive (near-frame-perfect, punishes whiffs)
    """

    # Reaction delay in ticks per level (lower = faster)
    _REACTION = {1: 30, 2: 25, 3: 20, 4: 15, 5: 10, 6: 8, 7: 4, 8: 2}

    def __init__(self, level: int = 4):
        self.level = max(1, min(8, level))
        self._reaction_delay = self._REACTION[self.level]

        self.ai_input = AIInput()

        self._cooldown: int   = 0
        self._action:   str   = "idle"
        self._action_timer: int = 0

    # ------------------------------------------------------------------

    def update(self, self_char: "Character", enemy_char: "Character") -> AIInput:
        """
        Decide what to do this tick and return the synthetic input.
        """
        self._cooldown -= 1

        dist_x = enemy_char.position[0] - self_char.position[0]
        dist_x *= self_char.facing   # Positive = enemy is in front

        on_ground = self_char.position[1] >= 0

        # Choose a new action when cooldown expires
        if self._cooldown <= 0:
            self._action = self._choose_action(dist_x, self_char, enemy_char)
            self._cooldown = self._reaction_delay + random.randint(0, 8)
            self._action_timer = 0

        buttons = self._execute_action(self._action, dist_x, on_ground)

        # Compute pressed / released vs previous frame
        prev_btns = self.ai_input.current.buttons
        pressed   = buttons & ~prev_btns
        released  = prev_btns & ~buttons

        frame = InputFrame(buttons=buttons, buttons_pressed=pressed,
                           buttons_released=released)
        self.ai_input.feed(frame)
        self._action_timer += 1
        return self.ai_input

    # ------------------------------------------------------------------

    def _choose_action(
        self,
        dist_x: float,
        self_char: "Character",
        enemy_char: "Character",
    ) -> str:
        level = self.level
        close = abs(dist_x) < 60
        medium = abs(dist_x) < 130

        # Low HP → more aggressive
        hp_ratio = self_char.life / max(1, self_char.max_life)
        if hp_ratio < 0.25:
            level = min(8, level + 2)

        roll = random.random()

        if close:
            if roll < 0.05 * level:
                return "jump_attack"
            if roll < 0.10 * level:
                return "crouch_attack"
            return "attack"
        elif medium:
            if roll < 0.08 * level:
                return "walk_in"
            if roll < 0.04 * level:
                return "jump"
            return "walk_in"
        else:
            if roll < 0.06 * level:
                return "jump"
            return "walk_in"

    def _execute_action(self, action: str, dist_x: float, on_ground: bool) -> Button:
        forward  = Button.RIGHT if dist_x > 0 else Button.LEFT
        backward = Button.LEFT  if dist_x > 0 else Button.RIGHT

        if action == "idle":
            return Button.NONE

        if action == "walk_in":
            return forward

        if action == "attack":
            btns = forward
            if self._action_timer < 3:
                btns |= random.choice([Button.A, Button.B, Button.C])
            return btns

        if action == "crouch_attack":
            btns = Button.DOWN
            if self._action_timer < 3:
                btns |= random.choice([Button.X, Button.Y, Button.Z])
            return btns

        if action == "jump":
            if self._action_timer == 0:
                return Button.UP | forward
            return forward

        if action == "jump_attack":
            if self._action_timer == 0:
                return Button.UP | forward
            if self._action_timer < 20:
                return forward
            return forward | random.choice([Button.A, Button.B])

        if action == "block":
            return backward

        return Button.NONE
