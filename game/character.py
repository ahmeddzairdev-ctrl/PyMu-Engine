"""
Character class — the in-game representation of a loaded MUGEN character.
Bridges CharacterLoader data with real-time game state.
"""

from typing import Optional, Dict, Tuple, List, Any, TYPE_CHECKING
from dataclasses import dataclass, field

if TYPE_CHECKING:
    from engine.input_handler import PlayerInput
    from engine.renderer import Renderer
    from game.fight import Fight
    from mugen.character_loader import CharacterLoader, CharacterConstants


class Character:
    """
    Runtime character instance.

    All coordinates follow MUGEN convention:
      • x positive = rightward
      • y positive = downward (ground is y = 0)
    """

    def __init__(self, loader: "CharacterLoader"):
        # --- Identity ---
        self.name: str = loader.name
        self.display_name: str = loader.displayname

        # --- Constants from CNS ---
        self.constants: "CharacterConstants" = loader.constants

        # --- Resources ---
        self.animations = loader.animations    # Dict[int, Animation]
        self.commands   = loader.commands      # List[Command]
        self.states     = loader.states        # Dict[int, StateDef]
        self.sprites    = loader.sprites       # SFFv1/v2 reader (may be None)
        self.sounds     = loader.sounds        # SoundLoader (may be None)

        # --- Vital stats ---
        self.max_life: int  = self.constants.life
        self.life: int      = self.constants.life
        self.max_power: int = 3000
        self.power: int     = 0

        # --- Spatial state ---
        self.position: Tuple[float, float] = (0.0, 0.0)
        self.velocity: Tuple[float, float] = (0.0, 0.0)
        self.facing: int = 1            # +1 right, -1 left

        # --- State machine ---
        self.state_no: int      = 0     # Current state number
        self.prev_state_no: int = 0
        self.state_time: int    = 0     # Ticks in current state
        self.ctrl: int          = 1     # Player control flag
        self.state_type: str    = "S"   # S / C / A / L

        # --- Animation ---
        self.anim_no: int      = 0      # Current animation number
        self.anim_frame: int   = 0      # Frame index within animation
        self.anim_time: int    = 0      # Ticks on current anim frame
        self.anim_elem: int    = 0      # Alias for anim_frame
        self.sprite_priority: int = 0

        # --- Hit / hurt ---
        self.active_hitdef: Optional[Dict[str, Any]] = None
        self.is_guarding: bool = False
        self.hitstun: int  = 0
        self.hitpause: int = 0

        # --- Misc ---
        self._state_executor = None   # Lazy-init StateControllerExecutor

    # ------------------------------------------------------------------
    # State machine
    # ------------------------------------------------------------------

    def change_state(self, new_state: int) -> None:
        """Transition to a new CNS state."""
        self.prev_state_no = self.state_no
        self.state_no      = new_state
        self.state_time    = 0

        # Apply statedef defaults
        statedef = self.states.get(new_state)
        if statedef is None:
            return

        if statedef.anim is not None:
            self._start_anim(statedef.anim)

        if statedef.ctrl is not None:
            self.ctrl = statedef.ctrl

        if statedef.velset != (None, None):
            vx, vy = self.velocity
            if statedef.velset[0] is not None:
                vx = statedef.velset[0]
            if statedef.velset[1] is not None:
                vy = statedef.velset[1]
            self.velocity = (vx, vy)

        self.state_type = statedef.type.value if statedef.type else "S"

    def _start_anim(self, anim_no: int) -> None:
        self.anim_no    = anim_no
        self.anim_frame = 0
        self.anim_time  = 0
        self.anim_elem  = 0

    # ------------------------------------------------------------------
    # Per-tick update
    # ------------------------------------------------------------------

    def update(self, player_input: "PlayerInput", fight: "Fight") -> None:
        """Update the character for one game tick."""
        if self.hitpause > 0:
            self.hitpause -= 1
            return

        # Run CNS state controllers
        self._execute_state_controllers()

        # Advance animation
        self._advance_animation()

        # Apply physics
        self._apply_physics()

        # Hitstun countdown
        if self.hitstun > 0:
            self.hitstun -= 1

        self.state_time += 1

    # ------------------------------------------------------------------
    # State controller execution
    # ------------------------------------------------------------------

    def _execute_state_controllers(self) -> None:
        if self._state_executor is None:
            from mugen.state_controller import StateControllerExecutor
            self._state_executor = StateControllerExecutor(self)

        statedef = self.states.get(self.state_no)
        if statedef is None:
            return

        for ctrl in statedef.controllers:
            self._state_executor.execute(ctrl)

    # ------------------------------------------------------------------
    # Animation
    # ------------------------------------------------------------------

    def _advance_animation(self) -> None:
        anim = self.animations.get(self.anim_no)
        if not anim or not anim.frames:
            return

        frame = anim.frames[self.anim_frame]
        self.anim_time += 1
        self.anim_elem  = self.anim_frame

        if frame.duration >= 0 and self.anim_time >= frame.duration:
            self.anim_frame += 1
            self.anim_time   = 0
            if self.anim_frame >= len(anim.frames):
                # Loop back
                self.anim_frame = anim.loop_start

    # ------------------------------------------------------------------
    # Physics
    # ------------------------------------------------------------------

    def _apply_physics(self) -> None:
        statedef = self.states.get(self.state_no)
        physics = statedef.physics.value if statedef else "S"

        px, py = self.position
        vx, vy = self.velocity

        # Gravity for airborne states
        if physics == "A":
            vy += self.constants.yaccel

        px += vx
        py += vy

        # Ground check
        if py > 0:
            py = 0.0
            vy = 0.0
            if self.state_type == "A":
                self.change_state(52)  # Landing state

        # Friction
        if py == 0.0 and physics == "S":
            vx *= self.constants.stand_friction
        elif py == 0.0 and physics == "C":
            vx *= self.constants.crouch_friction

        self.position = (px, py)
        self.velocity = (vx, vy)

    # ------------------------------------------------------------------
    # Collision box queries
    # ------------------------------------------------------------------

    def get_attack_boxes(self) -> List[Tuple[int, int, int, int]]:
        """Return the current frame's attack (Clsn1) boxes."""
        anim = self.animations.get(self.anim_no)
        if not anim or not anim.frames:
            return []
        frame = anim.frames[min(self.anim_frame, len(anim.frames) - 1)]
        return frame.clsn1

    def get_hurt_boxes(self) -> List[Tuple[int, int, int, int]]:
        """Return the current frame's hit/hurt (Clsn2) boxes."""
        anim = self.animations.get(self.anim_no)
        if not anim or not anim.frames:
            return []
        frame = anim.frames[min(self.anim_frame, len(anim.frames) - 1)]
        return frame.clsn2

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def render(self, renderer: "Renderer", camera_x: float, camera_y: float) -> None:
        """Draw the character sprite onto the renderer's game surface."""
        if self.sprites is None:
            return

        anim = self.animations.get(self.anim_no)
        if not anim or not anim.frames:
            return

        frame = anim.frames[min(self.anim_frame, len(anim.frames) - 1)]
        sprite = self.sprites.get_sprite(frame.group, frame.index)
        if sprite is None:
            return

        ox, oy = self.sprites.get_sprite_offset(frame.group, frame.index)
        sx, sy = renderer.world_to_screen(*self.position, camera_x, camera_y)

        draw_x = sx - ox * self.facing
        draw_y = sy + oy

        flip_h = (self.facing < 0) != frame.flip_h
        renderer.draw_sprite(sprite, draw_x, draw_y, flip_h=flip_h, flip_v=frame.flip_v)
