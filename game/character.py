"""
Character class — in-game runtime wrapper around a loaded MUGEN character.

Key fixes in this revision:
  - Direct input→velocity so characters actually walk/jump without requiring
    a full CNS state-machine implementation.
  - change_state() now auto-selects the best available animation.
  - Render uses correct MUGEN axis math (draw_y = sy - oy).
  - Coloured placeholder rect drawn when sprite unavailable (debug).
"""

from typing import Optional, Dict, Tuple, List, Any, TYPE_CHECKING
import pygame

if TYPE_CHECKING:
    from engine.input_handler import PlayerInput
    from engine.renderer import Renderer
    from game.fight import Fight
    from mugen.character_loader import CharacterLoader, CharacterConstants

from engine.input_handler import Button


class Character:
    """Runtime character instance."""

    def __init__(self, loader: "CharacterLoader"):
        self.name:         str = loader.name
        self.display_name: str = loader.displayname
        self.constants           = loader.constants

        self.animations = loader.animations
        self.commands   = loader.commands
        self.states     = loader.states
        self.sprites    = loader.sprites
        self.sounds     = loader.sounds

        # Vital stats
        self.max_life:  int = max(1, self.constants.life or 1000)
        self.life:      int = self.max_life
        self.max_power: int = 3000
        self.power:     int = 0

        # Spatial
        self.position: Tuple[float, float] = (0.0, 0.0)
        self.velocity: Tuple[float, float] = (0.0, 0.0)
        self.facing:   int = 1   # +1 right, -1 left
        self._on_ground: bool = True

        # State machine
        self.state_no:      int  = 0
        self.prev_state_no: int  = 0
        self.state_time:    int  = 0
        self.ctrl:          int  = 1
        self.state_type:    str  = "S"

        # Animation
        self.anim_no:    int = 0
        self.anim_frame: int = 0
        self.anim_time:  int = 0
        self.anim_elem:  int = 0
        self.sprite_priority: int = 0

        # Hit / hurt
        self.active_hitdef: Optional[Dict[str, Any]] = None
        self.is_guarding:   bool = False
        self.hitstun:       int  = 0
        self.hitpause:      int  = 0

        self._state_executor = None

        # Start on standing animation
        self._init_anim()

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _init_anim(self) -> None:
        """Select the best starting animation (idle = anim 0 if it exists)."""
        for candidate in (0, next(iter(self.animations), None)):
            if candidate is not None and candidate in self.animations:
                self.anim_no = candidate
                self.anim_frame = 0
                self.anim_time = 0
                return

    def play_sound(self, group: int, index: int) -> None:
        """Play a sound from this character's SND file if available."""
        if self.sounds is None:
            return
        sound = self.sounds.sounds.get((group, index))
        if sound:
            try:
                sound.play()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # State machine
    # ------------------------------------------------------------------

    def change_state(self, new_state: int) -> None:
        self.prev_state_no = self.state_no
        self.state_no      = new_state
        self.state_time    = 0

        statedef = self.states.get(new_state)
        if statedef is None:
            # No CNS state → pick best animation and return
            self._best_anim_for(new_state)
            return

        if statedef.anim is not None:
            self._start_anim(statedef.anim)
        if statedef.ctrl is not None:
            self.ctrl = statedef.ctrl
        if statedef.velset not in (None, (None, None)):
            vx, vy = self.velocity
            if statedef.velset[0] is not None:
                vx = statedef.velset[0]
            if statedef.velset[1] is not None:
                vy = statedef.velset[1]
            self.velocity = (vx, vy)
        self.state_type = statedef.type.value if statedef.type else "S"

    def _best_anim_for(self, state_no: int) -> None:
        """Pick the most appropriate animation for an unknown state."""
        if state_no in self.animations:
            self._start_anim(state_no)
        # else keep the current animation running (don't reset)

    def _start_anim(self, anim_no: int) -> None:
        if anim_no in self.animations:
            self.anim_no    = anim_no
            self.anim_frame = 0
            self.anim_time  = 0
            self.anim_elem  = 0

    # ------------------------------------------------------------------
    # Per-tick update
    # ------------------------------------------------------------------

    def update(self, player_input: "PlayerInput", fight: "Fight") -> None:
        if self.hitpause > 0:
            self.hitpause -= 1
            return

        # Run CNS state controllers first (may change velocity/state)
        self._execute_state_controllers()

        # Direct input → velocity (stand-in for CNS walk/jump states)
        if self.ctrl:
            self._apply_input(player_input)

        self._advance_animation()
        self._apply_physics()

        if self.hitstun > 0:
            self.hitstun -= 1

        self.state_time += 1

    # ------------------------------------------------------------------
    # Direct input handling (replaces missing CNS walk/jump states)
    # ------------------------------------------------------------------

    def _apply_input(self, inp: "PlayerInput") -> None:
        """Translate player buttons into velocity and state changes."""
        vx, vy = self.velocity

        walk_fwd  = getattr(self.constants, 'walk_fwd',  2.4) or 2.4
        walk_back = getattr(self.constants, 'walk_back', -2.2) or -2.2
        jump_neu  = getattr(self.constants, 'jump_neu',  (0.0, -8.4))

        # Normalise tuple/scalar velocities
        if isinstance(walk_fwd,  (list, tuple)): walk_fwd  = walk_fwd[0]
        if isinstance(walk_back, (list, tuple)): walk_back = walk_back[0]
        jump_y = jump_neu[1] if isinstance(jump_neu, (list, tuple)) else -8.4

        forward  = Button.RIGHT if self.facing > 0 else Button.LEFT
        backward = Button.LEFT  if self.facing > 0 else Button.RIGHT

        on_ground = self._on_ground

        # Horizontal movement
        if inp.button_held(forward):
            vx = walk_fwd  * self.facing
            if on_ground and self.anim_no != 20:   # anim 20 = walk
                self._start_anim(20 if 20 in self.animations else self.anim_no)
        elif inp.button_held(backward):
            vx = walk_back * self.facing
            if on_ground and self.anim_no != 20:
                self._start_anim(20 if 20 in self.animations else self.anim_no)
        else:
            vx = 0.0
            if on_ground and self.anim_no == 20:
                self._start_anim(0)   # return to stand

        # Jump
        if on_ground and inp.button_pressed(Button.UP):
            vy = jump_y
            self._on_ground = False
            self._start_anim(40 if 40 in self.animations else self.anim_no)

        # Crouch
        if on_ground and inp.button_held(Button.DOWN) and vx == 0.0:
            self._start_anim(10 if 10 in self.animations else self.anim_no)

        # Attacks: set hitdef when pressing an attack button
        attack_map = {
            Button.A: (200, 20, 'light'),
            Button.B: (210, 35, 'medium'),
            Button.C: (220, 55, 'hard'),
            Button.X: (230, 25, 'light'),
            Button.Y: (240, 40, 'medium'),
            Button.Z: (250, 60, 'hard'),
        }
        for btn, (anim_id, damage, anim_type) in attack_map.items():
            if inp.button_pressed(btn) and self.hitstun == 0:
                target_anim = anim_id if anim_id in self.animations else self.anim_no
                self._start_anim(target_anim)
                # Set a basic hitdef so fight.py can detect the hit
                self.active_hitdef = {
                    'damage':        (damage, damage // 2),
                    'animtype':      anim_type,
                    'guardflag':     'MA',
                    'pausetime':     (12, 12),
                    'ground.velocity': (-3.5, 0.0),
                    'getpower':      damage * 7,
                    'givepower':     damage * 4,
                    '_used':         False,
                }
                break

        self.velocity = (vx, vy)

    # ------------------------------------------------------------------
    # State controllers
    # ------------------------------------------------------------------

    def _execute_state_controllers(self) -> None:
        if self._state_executor is None:
            from mugen.state_controller import StateControllerExecutor
            self._state_executor = StateControllerExecutor(self)
        statedef = self.states.get(self.state_no)
        if statedef is None:
            return
        for ctrl in statedef.controllers:
            try:
                self._state_executor.execute(ctrl)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Animation advance
    # ------------------------------------------------------------------

    def _advance_animation(self) -> None:
        anim = self.animations.get(self.anim_no)
        if not anim or not anim.frames:
            return
        frame = anim.frames[self.anim_frame]
        self.anim_time += 1
        self.anim_elem  = self.anim_frame
        if frame.duration >= 0 and self.anim_time >= max(1, frame.duration):
            self.anim_frame += 1
            self.anim_time   = 0
            if self.anim_frame >= len(anim.frames):
                self.anim_frame = anim.loop_start

    # ------------------------------------------------------------------
    # Physics  (Y=0 is ground, positive Y goes downward in screen space,
    # but MUGEN physics uses Y upward, so positive vy = falling)
    # ------------------------------------------------------------------

    def _apply_physics(self) -> None:
        statedef = self.states.get(self.state_no)
        physics  = statedef.physics.value if statedef and statedef.physics else "S"

        px, py = self.position
        vx, vy = self.velocity

        if not self._on_ground:
            vy += (self.constants.yaccel or 0.44)

        px += vx
        py += vy

        if py >= 0.0:
            py = 0.0
            vy = 0.0
            self._on_ground = True
            if self.anim_no in (40, 41, 42):   # jump anims → land
                self._start_anim(0)
        else:
            self._on_ground = False

        if self._on_ground:
            friction = self.constants.stand_friction or 0.85
            if physics == "C":
                friction = self.constants.crouch_friction or 0.82
            vx *= friction

        self.position = (px, py)
        self.velocity = (vx, vy)

    # ------------------------------------------------------------------
    # Collision boxes
    # ------------------------------------------------------------------

    def get_attack_boxes(self) -> List[Tuple[int, int, int, int]]:
        anim = self.animations.get(self.anim_no)
        if not anim or not anim.frames:
            return []
        return anim.frames[min(self.anim_frame, len(anim.frames)-1)].clsn1

    def get_hurt_boxes(self) -> List[Tuple[int, int, int, int]]:
        anim = self.animations.get(self.anim_no)
        if not anim or not anim.frames:
            return []
        return anim.frames[min(self.anim_frame, len(anim.frames)-1)].clsn2

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def render(self, renderer: "Renderer", camera_x: float, camera_y: float) -> None:
        surf = renderer.get_surface()
        sx, sy = renderer.world_to_screen(*self.position, camera_x, camera_y)

        sprite_drawn = False

        if self.sprites is not None:
            anim = self.animations.get(self.anim_no)
            if anim and anim.frames:
                frame  = anim.frames[min(self.anim_frame, len(anim.frames)-1)]
                sprite = self.sprites.get_sprite(frame.group, frame.index)
                ox, oy = self.sprites.get_sprite_offset(frame.group, frame.index)

                if sprite is not None:
                    flip_h = (self.facing < 0) != frame.flip_h
                    flip_v = frame.flip_v

                    if flip_h or flip_v:
                        sprite = pygame.transform.flip(sprite, flip_h, flip_v)

                    w = sprite.get_width()

                    # MUGEN axis math:
                    #   facing right: sprite_left = screen_x - ox
                    #   facing left:  sprite_left = screen_x - (width - ox)
                    #   sprite_top   = screen_y - oy  (oy is pixels below sprite top)
                    draw_x = (sx - ox) if not flip_h else (sx - (w - ox))
                    draw_y = sy - oy

                    surf.blit(sprite, (int(draw_x), int(draw_y)))
                    sprite_drawn = True

        if not sprite_drawn:
            # Coloured placeholder (40×80 px) so character is always visible
            w, h = 40, 80
            col   = (200, 50, 50) if self.facing > 0 else (50, 50, 200)
            rect  = pygame.Rect(sx - w // 2, sy - h, w, h)
            pygame.draw.rect(surf, col, rect)
            pygame.draw.rect(surf, (255, 255, 255), rect, 1)
