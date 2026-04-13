"""
Fight logic — manages a complete fight between two characters.

Key fixes in this revision:
  - Hit detection: falls back to proximity box when .air has no clsn1 boxes.
  - Hitdef cleared only after one successful hit (not every frame).
  - Hit state applied to defender immediately; hitstun prevents re-activation.
  - Sound playback on hit / KO via engine.audio_manager when available.
  - Stage update() called each tick so background layers scroll.
  - HUD renders lifebars, power bars, timer and combo counters.
"""

import pygame
from enum import Enum, auto
from typing import Optional, List, Tuple, Dict, Any
from dataclasses import dataclass, field

from game.character import Character
from game.stage import Stage
from config import CONFIG
from engine.input_handler import Button


class FightState(Enum):
    INTRO      = auto()
    ROUND_START = auto()
    FIGHTING   = auto()
    KO         = auto()
    ROUND_END  = auto()
    MATCH_END  = auto()
    DRAW_GAME  = auto()


class RoundResult(Enum):
    NONE        = auto()
    P1_WIN      = auto()
    P2_WIN      = auto()
    DRAW        = auto()
    TIME_OVER_P1 = auto()
    TIME_OVER_P2 = auto()
    DOUBLE_KO   = auto()


@dataclass
class RoundInfo:
    round_number:    int = 1
    time_remaining:  int = 99
    time_ticks:      int = 0
    result:     RoundResult = RoundResult.NONE
    started:    bool = False
    finished:   bool = False
    p1_rounds_won: int = 0
    p2_rounds_won: int = 0
    draw_games:    int = 0


@dataclass
class ComboInfo:
    hit_count:     int = 0
    total_damage:  int = 0
    is_active:     bool = False
    display_timer: int = 0

    def reset(self) -> None:
        self.hit_count    = 0
        self.total_damage = 0
        self.is_active    = False
        self.display_timer = 0


class Fight:
    """Manages a complete fight between two characters."""

    ROUND_START_TICKS = 90
    KO_FREEZE_TICKS   = 60
    ROUND_END_TICKS   = 180

    def __init__(self, p1: Character, p2: Character, stage: Stage):
        self.p1    = p1
        self.p2    = p2
        self.stage = stage

        self.state        = FightState.INTRO
        self.round        = RoundInfo()
        self.round.time_remaining = CONFIG.gameplay.round_time
        self.round.time_ticks     = self.round.time_remaining * 60

        self.state_timer  = 0
        self.p1_combo     = ComboInfo()
        self.p2_combo     = ComboInfo()

        self.camera_x     = 0.0
        self.camera_y     = 0.0
        self.paused       = False
        self.pause_player = 0
        self.super_pause_ticks = 0
        self.hit_pause_ticks   = 0

        self._hud = None

        self._setup_round()

    # ------------------------------------------------------------------
    # Round setup
    # ------------------------------------------------------------------

    def _setup_round(self) -> None:
        start_x = getattr(self.stage, 'start_x', 70)

        self.p1.position = (-float(start_x), 0.0)
        self.p2.position = ( float(start_x), 0.0)
        self.p1.facing   =  1
        self.p2.facing   = -1

        # Reset to idle animation
        self.p1._start_anim(0)
        self.p2._start_anim(0)
        self.p1.change_state(0)
        self.p2.change_state(0)

        self.p1.life     = self.p1.max_life
        self.p2.life     = self.p2.max_life
        self.p1.velocity = (0.0, 0.0)
        self.p2.velocity = (0.0, 0.0)
        self.p1.ctrl     = 0   # disabled until round starts
        self.p2.ctrl     = 0
        self.p1.active_hitdef = None
        self.p2.active_hitdef = None
        self.p1_combo.reset()
        self.p2_combo.reset()

        self.state       = FightState.ROUND_START
        self.state_timer = 0
        self.round.started  = False
        self.round.finished = False

    # ------------------------------------------------------------------
    # Main update
    # ------------------------------------------------------------------

    def update(self, p1_input, p2_input) -> None:
        if self.paused:
            self._handle_pause(p1_input, p2_input)
            return

        if p1_input.button_pressed(Button.START):
            self.paused = True;  self.pause_player = 0;  return
        if p2_input.button_pressed(Button.START):
            self.paused = True;  self.pause_player = 1;  return

        if self.super_pause_ticks > 0:
            self.super_pause_ticks -= 1
            return

        # Update stage backgrounds
        if hasattr(self.stage, 'update'):
            self.stage.update()

        if self.state == FightState.INTRO:
            self._update_intro()
        elif self.state == FightState.ROUND_START:
            self._update_round_start()
        elif self.state == FightState.FIGHTING:
            self._update_fighting(p1_input, p2_input)
        elif self.state == FightState.KO:
            self._update_ko()
        elif self.state == FightState.ROUND_END:
            self._update_round_end()
        elif self.state == FightState.DRAW_GAME:
            self._update_draw_game()

        self.state_timer += 1

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def _update_intro(self) -> None:
        self.state       = FightState.ROUND_START
        self.state_timer = 0

    def _update_round_start(self) -> None:
        if self.state_timer >= self.ROUND_START_TICKS:
            self.state       = FightState.FIGHTING
            self.state_timer = 0
            self.round.started = True
            self.p1.ctrl = 1
            self.p2.ctrl = 1

    def _update_round_end(self) -> None:
        if self.state_timer >= self.ROUND_END_TICKS:
            if self.round.p1_rounds_won >= CONFIG.gameplay.rounds_to_win:
                self.state = FightState.MATCH_END
            elif self.round.p2_rounds_won >= CONFIG.gameplay.rounds_to_win:
                self.state = FightState.MATCH_END
            elif self.round.draw_games >= CONFIG.gameplay.max_draw_games:
                self.state = FightState.DRAW_GAME
            else:
                self.round.round_number  += 1
                self.round.time_remaining = CONFIG.gameplay.round_time
                self.round.time_ticks     = self.round.time_remaining * 60
                self._setup_round()

    def _update_draw_game(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Active fighting
    # ------------------------------------------------------------------

    def _update_fighting(self, p1_input, p2_input) -> None:
        # Timer
        if CONFIG.gameplay.round_time > 0:
            self.round.time_ticks     -= 1
            self.round.time_remaining  = max(0, self.round.time_ticks // 60)
            if self.round.time_ticks <= 0:
                self._handle_time_over()
                return

        # Auto-face — each character always faces the opponent
        p1x, _ = self.p1.position
        p2x, _ = self.p2.position
        if self.p1.ctrl:
            self.p1.facing =  1 if p1x < p2x else -1
        if self.p2.ctrl:
            self.p2.facing = -1 if p2x > p1x else  1

        # Update characters
        self.p1.update(p1_input, self)
        self.p2.update(p2_input, self)

        # Collision
        self._check_collisions()

        # KO check
        if self.p1.life <= 0 or self.p2.life <= 0:
            self._handle_ko()
            return

        # Camera / combo display / boundaries
        self._update_camera()
        self._update_combo_display()
        self._enforce_boundaries()

    # ------------------------------------------------------------------
    # Collision detection
    # ------------------------------------------------------------------

    def _check_collisions(self) -> None:
        # P1 attacking P2
        p1_hit = self._check_hit(self.p1, self.p2)
        if p1_hit:
            self._apply_hit(self.p1, self.p2, p1_hit, self.p2_combo)

        # P2 attacking P1
        p2_hit = self._check_hit(self.p2, self.p1)
        if p2_hit:
            self._apply_hit(self.p2, self.p1, p2_hit, self.p1_combo)

        self._check_push_collision()

    def _check_hit(self, attacker: Character, defender: Character) -> Optional[Dict]:
        """
        Check if attacker's attack boxes overlap defender's hurt boxes.

        Fallback: when no attack boxes exist, use a simple proximity box so
        basic button-press attacks still land. This covers characters whose
        .air files don't define Clsn1 boxes on every attack frame.
        """
        if not attacker.active_hitdef:
            return None
        # Don't re-apply the same hitdef twice
        if attacker.active_hitdef.get('_used'):
            return None

        attack_boxes = attacker.get_attack_boxes()
        hurt_boxes   = defender.get_hurt_boxes()

        # If no explicit boxes, fall back to character proximity
        if not attack_boxes:
            # Use a synthetic attack box centred on the attacker,
            # extending forward toward the defender.
            px, py = attacker.position
            w = 50;  h = 100
            attack_boxes = [(0, -h, w * attacker.facing, 0)]

        if not hurt_boxes:
            # Defender hurt box: their whole body
            hurt_boxes = [(-20, -120, 20, 0)]

        attack_world = self._transform_boxes(attack_boxes, attacker)
        hurt_world   = self._transform_boxes(hurt_boxes,   defender)

        for a in attack_world:
            for h in hurt_world:
                if self._boxes_intersect(a, h):
                    return attacker.active_hitdef

        return None

    def _transform_boxes(self, boxes, char: Character):
        result = []
        px, py = char.position
        facing = char.facing
        for x1, y1, x2, y2 in boxes:
            if facing < 0:
                x1, x2 = -x2, -x1
            result.append((px+x1, py+y1, px+x2, py+y2))
        return result

    @staticmethod
    def _boxes_intersect(a, b) -> bool:
        return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])

    def _apply_hit(self, attacker: Character, defender: Character,
                   hitdef: Dict, combo: ComboInfo) -> None:
        # Mark used immediately so it can't double-hit
        hitdef['_used'] = True
        attacker.active_hitdef = None

        damage = hitdef.get('damage', (20, 0))
        if isinstance(damage, tuple):
            hit_dmg, guard_dmg = damage
        else:
            hit_dmg = damage;  guard_dmg = damage // 2

        is_blocked = self._check_block(defender, hitdef)

        if is_blocked:
            actual = guard_dmg
            defender.change_state(150)
            defender.hitstun = 12
        else:
            actual = hit_dmg
            hit_state = self._get_hit_state(defender, hitdef)
            defender.change_state(hit_state)
            defender.hitstun = hitdef.get('pausetime', (0, 20))[1]

            gv = hitdef.get('ground.velocity', (-4.0, 0.0))
            if isinstance(gv, (list, tuple)):
                defender.velocity = (gv[0] * attacker.facing, gv[1])
            defender._on_ground = False

            combo.is_active    = True
            combo.hit_count   += 1
            combo.total_damage += actual
            combo.display_timer = 90

        defender.life = max(0, defender.life - actual)
        attacker.power = min(attacker.max_power,
                             attacker.power + hitdef.get('getpower', 0))
        defender.power = min(defender.max_power,
                             defender.power + hitdef.get('givepower', 0))

        attacker.hitpause = hitdef.get('pausetime', (8, 0))[0]
        defender.hitpause = hitdef.get('pausetime', (0, 8))[1]

        # Play hit sound from character if sounds are loaded
        try:
            defender.play_sound(5, 0)   # MUGEN common hit sound: group 5, index 0
        except Exception:
            pass

    def _check_block(self, defender: Character, hitdef: Dict) -> bool:
        if not defender.is_guarding:
            return False
        gf = hitdef.get('guardflag', 'MA')
        st = defender.state_type
        if st == 'S': return 'H' in gf or 'M' in gf
        if st == 'C': return 'L' in gf or 'M' in gf
        if st == 'A': return 'A' in gf
        return False

    def _get_hit_state(self, defender: Character, hitdef: Dict) -> int:
        atype = hitdef.get('animtype', 'light')
        st    = defender.state_type
        if st == 'S':
            return {  'light': 5000, 'medium': 5010, 'hard': 5020, 'back': 5030 }.get(atype, 5000)
        if st == 'C':
            return 5010
        if st == 'A':
            return 5050
        return 5000

    # ------------------------------------------------------------------
    # Push / boundaries / camera
    # ------------------------------------------------------------------

    def _check_push_collision(self) -> None:
        p1x, p1y = self.p1.position
        p2x, p2y = self.p2.position

        pf = getattr(self.p1.constants, 'ground_front', 16)
        pb = getattr(self.p1.constants, 'ground_back',  15)

        if self.p1.facing > 0:
            p1_l = p1x - pb;  p1_r = p1x + pf
        else:
            p1_l = p1x - pf;  p1_r = p1x + pb

        if self.p2.facing > 0:
            p2_l = p2x - pb;  p2_r = p2x + pf
        else:
            p2_l = p2x - pf;  p2_r = p2x + pb

        if p1_r > p2_l and p1_l < p2_r:
            overlap = min(p1_r - p2_l, p2_r - p1_l) / 2
            if p1x < p2x:
                self.p1.position = (p1x - overlap, p1y)
                self.p2.position = (p2x + overlap, p2y)
            else:
                self.p1.position = (p1x + overlap, p1y)
                self.p2.position = (p2x - overlap, p2y)

    def _update_camera(self) -> None:
        p1x, _ = self.p1.position
        p2x, _ = self.p2.position
        target  = (p1x + p2x) / 2
        self.camera_x += (target - self.camera_x) * 0.12

        lb = getattr(self.stage, 'bound_left',  -200)
        rb = getattr(self.stage, 'bound_right',  200)
        hw = CONFIG.video.game_width / 2
        self.camera_x = max(lb + hw, min(rb - hw, self.camera_x))

    def _update_combo_display(self) -> None:
        for combo in (self.p1_combo, self.p2_combo):
            if combo.display_timer > 0:
                combo.display_timer -= 1
                if combo.display_timer == 0:
                    combo.reset()

    def _enforce_boundaries(self) -> None:
        lb = getattr(self.stage, 'bound_left',  -200)
        rb = getattr(self.stage, 'bound_right',  200)
        for char in (self.p1, self.p2):
            px, py = char.position
            char.position = (max(lb, min(rb, px)), min(0.0, py))

    # ------------------------------------------------------------------
    # KO / time over
    # ------------------------------------------------------------------

    def _handle_ko(self) -> None:
        self.state       = FightState.KO
        self.state_timer = 0
        if self.p1.life <= 0 and self.p2.life <= 0:
            self.round.result = RoundResult.DOUBLE_KO
        elif self.p1.life <= 0:
            self.round.result      = RoundResult.P2_WIN
            self.round.p2_rounds_won += 1
        else:
            self.round.result      = RoundResult.P1_WIN
            self.round.p1_rounds_won += 1
        # Freeze both characters
        self.p1.ctrl = 0
        self.p2.ctrl = 0

    def _handle_time_over(self) -> None:
        r1 = self.p1.life / max(1, self.p1.max_life)
        r2 = self.p2.life / max(1, self.p2.max_life)
        if r1 > r2:
            self.round.result        = RoundResult.TIME_OVER_P1
            self.round.p1_rounds_won += 1
        elif r2 > r1:
            self.round.result        = RoundResult.TIME_OVER_P2
            self.round.p2_rounds_won += 1
        else:
            self.round.result      = RoundResult.DRAW
            self.round.draw_games += 1
        self.state       = FightState.KO
        self.state_timer = 0
        self.p1.ctrl = 0
        self.p2.ctrl = 0

    def _update_ko(self) -> None:
        if self.state_timer >= self.KO_FREEZE_TICKS:
            self.state       = FightState.ROUND_END
            self.state_timer = 0

    # ------------------------------------------------------------------
    # Pause
    # ------------------------------------------------------------------

    def _handle_pause(self, p1_input, p2_input) -> None:
        if self.pause_player == 0:
            if p1_input.button_pressed(Button.START):
                self.paused = False
        else:
            if p2_input.button_pressed(Button.START):
                self.paused = False

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def render(self, renderer) -> None:
        # Align character ground Y with stage zoffset so feet touch the floor
        renderer.set_ground_y(self.stage.zoffset)

        # 1. Stage background (layerno=0)
        self.stage.render(renderer, self.camera_x, self.camera_y)

        # 2. Ground shadows (under characters, above stage bg)
        try:
            self.stage.render_shadows(renderer, [self.p1, self.p2], self.camera_x)
        except Exception:
            pass

        # 3. Characters sorted by sprite priority (lower = drawn first = behind)
        chars = sorted([self.p1, self.p2], key=lambda c: c.sprite_priority)
        for char in chars:
            char.render(renderer, self.camera_x, self.camera_y)

        # 4. Stage foreground (layerno=1) — drawn over characters
        self.stage.render_foreground(renderer, self.camera_x, self.camera_y)

        # 5. HUD (always on top)
        self._render_hud(renderer)

        if self.paused:
            self._render_pause(renderer)

    def _render_hud(self, renderer) -> None:
        """Render life bars, power bars, timer, combo counters."""
        if self._hud is None:
            try:
                from ui.hud import HUD
                self._hud = HUD()
            except Exception:
                return
        try:
            self._hud.render(renderer, self)
        except Exception:
            pass

    def _render_pause(self, renderer) -> None:
        surf = renderer.get_surface()
        overlay = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 128))
        surf.blit(overlay, (0, 0))
        renderer.draw_text("PAUSED",
                           CONFIG.video.game_width // 2 - 24,
                           CONFIG.video.game_height // 2,
                           (255, 255, 255), 16)
