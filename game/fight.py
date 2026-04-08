"""
Fight logic - manages the actual fighting gameplay.
Handles rounds, win conditions, and fight flow.
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
    """States within a fight."""
    INTRO = auto()
    ROUND_START = auto()
    FIGHTING = auto()
    KO = auto()
    ROUND_END = auto()
    MATCH_END = auto()
    DRAW_GAME = auto()


class RoundResult(Enum):
    """Result of a round."""
    NONE = auto()
    P1_WIN = auto()
    P2_WIN = auto()
    DRAW = auto()
    TIME_OVER_P1 = auto()
    TIME_OVER_P2 = auto()
    DOUBLE_KO = auto()


@dataclass
class RoundInfo:
    """Information about the current round."""
    round_number: int = 1
    time_remaining: int = 99  # In seconds (display)
    time_ticks: int = 0       # Internal tick counter
    result: RoundResult = RoundResult.NONE
    
    # Round state
    started: bool = False
    finished: bool = False
    
    # Win tracking
    p1_rounds_won: int = 0
    p2_rounds_won: int = 0
    draw_games: int = 0


@dataclass
class ComboInfo:
    """Tracks combo information for a player."""
    hit_count: int = 0
    total_damage: int = 0
    is_active: bool = False
    display_timer: int = 0  # Ticks to show combo counter
    
    def reset(self) -> None:
        """Reset combo tracking."""
        self.hit_count = 0
        self.total_damage = 0
        self.is_active = False


class Fight:
    """
    Manages a complete fight between two players.
    Handles rounds, timing, win conditions, and coordinates character updates.
    """
    
    ROUND_START_TICKS = 60    # 1 second at 60fps
    KO_FREEZE_TICKS = 60      # Freeze on KO
    ROUND_END_TICKS = 180     # Time before next round
    
    def __init__(self, p1_char: Character, p2_char: Character, stage: Stage):
        self.p1 = p1_char
        self.p2 = p2_char
        self.stage = stage
        
        self.state = FightState.INTRO
        self.round = RoundInfo()
        self.round.time_remaining = CONFIG.gameplay.round_time
        self.round.time_ticks = self.round.time_remaining * 60  # Convert to ticks
        
        self.state_timer = 0  # Ticks in current state
        
        # Combo tracking
        self.p1_combo = ComboInfo()
        self.p2_combo = ComboInfo()
        
        # Camera
        self.camera_x = 0.0
        self.camera_y = 0.0
        
        # HUD (lazy-loaded to avoid circular import at module level)
        self._hud = None

        # Pause state
        self.paused = False
        self.pause_player = 0  # Which player paused
        
        # Super pause/freeze
        self.super_pause_ticks = 0
        self.hit_pause_ticks = 0
        
        # Initialize positions
        self._setup_round()
    
    def _setup_round(self) -> None:
        """Set up character positions for a new round."""
        # Starting positions (symmetric around center)
        start_x = self.stage.start_x if hasattr(self.stage, 'start_x') else 70
        
        self.p1.position = (-start_x, 0.0)
        self.p2.position = (start_x, 0.0)
        
        # Face each other
        self.p1.facing = 1   # Facing right
        self.p2.facing = -1  # Facing left
        
        # Reset to idle state
        self.p1.change_state(0)  # Stand state
        self.p2.change_state(0)
        
        # Reset life
        self.p1.life = self.p1.max_life
        self.p2.life = self.p2.max_life
        
        # Reset power (optionally)
        # self.p1.power = 0
        # self.p2.power = 0
        
        # Reset velocities
        self.p1.velocity = (0.0, 0.0)
        self.p2.velocity = (0.0, 0.0)
        
        # Clear combo info
        self.p1_combo.reset()
        self.p2_combo.reset()
        
        self.state = FightState.ROUND_START
        self.state_timer = 0
        self.round.started = False
        self.round.finished = False
    
    def update(self, p1_input: 'PlayerInput', p2_input: 'PlayerInput') -> None:
        """Update the fight for one tick."""
        # Handle pause
        if self.paused:
            self._handle_pause(p1_input, p2_input)
            return
        
        # Check for pause request
        if p1_input.button_pressed(Button.START):  # START button
            self.paused = True
            self.pause_player = 0
            return
        elif p2_input.button_pressed(Button.START):
            self.paused = True
            self.pause_player = 1
            return
        
        # Handle super pause
        if self.super_pause_ticks > 0:
            self.super_pause_ticks -= 1
            # During super pause, only update the character that initiated it
            return
        
        # Update based on fight state
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
    
    def _update_intro(self) -> None:
        """Update intro sequence (character intros)."""
        # Skip for now - go straight to round start
        self.state = FightState.ROUND_START
        self.state_timer = 0
    
    def _update_round_start(self) -> None:
        """Update round start countdown."""
        if self.state_timer >= self.ROUND_START_TICKS:
            self.state = FightState.FIGHTING
            self.state_timer = 0
            self.round.started = True
            
            # Enable player control
            self.p1.ctrl = 1
            self.p2.ctrl = 1
    
    def _update_fighting(self, p1_input: 'PlayerInput', p2_input: 'PlayerInput') -> None:
        """Update active fighting gameplay."""
        # Update timer
        if CONFIG.gameplay.round_time > 0:
            self.round.time_ticks -= 1
            self.round.time_remaining = max(0, self.round.time_ticks // 60)
            
            # Time over
            if self.round.time_ticks <= 0:
                self._handle_time_over()
                return
        
        # Update characters
        self.p1.update(p1_input, self)
        self.p2.update(p2_input, self)
        
        # Check for hits
        self._check_collisions()
        
        # Check for KO
        if self.p1.life <= 0 or self.p2.life <= 0:
            self._handle_ko()
            return
        
        # Update camera
        self._update_camera()
        
        # Update combos display
        self._update_combo_display()
        
        # Enforce boundaries
        self._enforce_boundaries()
    
    def _check_collisions(self) -> None:
        """Check for attack collisions between characters."""
        # P1 attacking P2
        p1_hit = self._check_hit(self.p1, self.p2)
        if p1_hit:
            self._apply_hit(self.p1, self.p2, p1_hit, self.p2_combo)
        
        # P2 attacking P1
        p2_hit = self._check_hit(self.p2, self.p1)
        if p2_hit:
            self._apply_hit(self.p2, self.p1, p2_hit, self.p1_combo)
        
        # Push collision (no overlap)
        self._check_push_collision()
    
    def _check_hit(self, attacker: Character, defender: Character) -> Optional[Dict]:
        """Check if attacker's hitboxes connect with defender's hurtboxes."""
        if not attacker.active_hitdef:
            return None
        
        # Get collision boxes
        attack_boxes = attacker.get_attack_boxes()
        hurt_boxes = defender.get_hurt_boxes()
        
        if not attack_boxes or not hurt_boxes:
            return None
        
        # Transform boxes to world coordinates
        attack_world = self._transform_boxes(attack_boxes, attacker)
        hurt_world = self._transform_boxes(hurt_boxes, defender)
        
        # Check intersection
        for a_box in attack_world:
            for h_box in hurt_world:
                if self._boxes_intersect(a_box, h_box):
                    return attacker.active_hitdef
        
        return None
    
    def _transform_boxes(self, boxes: List[Tuple[int, int, int, int]], 
                        char: Character) -> List[Tuple[float, float, float, float]]:
        """Transform local collision boxes to world coordinates."""
        result = []
        px, py = char.position
        facing = char.facing
        
        for x1, y1, x2, y2 in boxes:
            # Flip x coordinates based on facing
            if facing < 0:
                x1, x2 = -x2, -x1
            
            # Translate to world position
            wx1 = px + x1
            wy1 = py + y1
            wx2 = px + x2
            wy2 = py + y2
            
            # Normalize (ensure x1 < x2, y1 < y2)
            result.append((
                min(wx1, wx2), min(wy1, wy2),
                max(wx1, wx2), max(wy1, wy2)
            ))
        
        return result
    
    def _boxes_intersect(self, box1: Tuple[float, float, float, float],
                        box2: Tuple[float, float, float, float]) -> bool:
        """Check if two AABB boxes intersect."""
        x1, y1, x2, y2 = box1
        x3, y3, x4, y4 = box2
        
        return not (x2 < x3 or x4 < x1 or y2 < y3 or y4 < y1)
    
    def _apply_hit(self, attacker: Character, defender: Character,
                   hitdef: Dict, combo: ComboInfo) -> None:
        """Apply a hit from attacker to defender."""
        # Get hit properties
        damage = hitdef.get('damage', (20, 0))
        if isinstance(damage, tuple):
            hit_damage, guard_damage = damage
        else:
            hit_damage, guard_damage = damage, damage // 2
        
        # Check if blocked
        is_blocked = self._check_block(defender, hitdef)
        
        if is_blocked:
            # Apply guard damage (chip damage)
            actual_damage = guard_damage
            defender.change_state(150)  # Guard hit state
        else:
            # Apply full damage
            actual_damage = hit_damage
            
            # Determine hit state
            hit_state = self._get_hit_state(defender, hitdef)
            defender.change_state(hit_state)
            
            # Apply hitstun
            defender.hitstun = hitdef.get('pausetime', (0, 12))[1]
            
            # Apply velocity
            ground_vel = hitdef.get('ground.velocity', (-5.0, 0.0))
            defender.velocity = (
                ground_vel[0] * attacker.facing,
                ground_vel[1]
            )
            
            # Update combo
            combo.is_active = True
            combo.hit_count += 1
            combo.total_damage += actual_damage
            combo.display_timer = 90  # Show for 1.5 seconds
        
        # Apply damage
        defender.life = max(0, defender.life - actual_damage)
        
        # Give power to attacker
        attacker.power = min(attacker.max_power, 
                            attacker.power + hitdef.get('getpower', 0))
        
        # Give power to defender
        defender.power = min(defender.max_power,
                            defender.power + hitdef.get('givepower', 0))
        
        # Hit pause
        pause_time = hitdef.get('pausetime', (0, 0))
        attacker.hitpause = pause_time[0]
        defender.hitpause = pause_time[1]
        
        # Create hit spark
        # (Would spawn a helper/explod here)
        
        # Clear the hitdef so it doesn't hit again
        attacker.active_hitdef = None
    
    def _check_block(self, defender: Character, hitdef: Dict) -> bool:
        """Check if defender is blocking."""
        # Check if in guard state
        if not defender.is_guarding:
            return False
        
        # Check guard type (high/low/mid)
        guard_flag = hitdef.get('guardflag', 'MA')
        
        if defender.state_type == 'S':  # Standing
            return 'H' in guard_flag or 'M' in guard_flag
        elif defender.state_type == 'C':  # Crouching
            return 'L' in guard_flag or 'M' in guard_flag
        elif defender.state_type == 'A':  # Airborne
            return 'A' in guard_flag
        
        return False
    
    def _get_hit_state(self, defender: Character, hitdef: Dict) -> int:
        """Determine which hit state the defender should enter."""
        # Based on defender's state type and hit type
        anim_type = hitdef.get('animtype', 'light')
        
        if defender.state_type == 'S':
            if anim_type == 'light':
                return 5000
            elif anim_type == 'medium':
                return 5010
            elif anim_type == 'hard':
                return 5020
            elif anim_type == 'back':
                return 5030
        elif defender.state_type == 'C':
            if anim_type == 'light':
                return 5000
            else:
                return 5010
        elif defender.state_type == 'A':
            return 5050  # Air hit
        
        return 5000
    
    def _check_push_collision(self) -> None:
        """Handle push collision between characters (no overlap)."""
        p1_x, p1_y = self.p1.position
        p2_x, p2_y = self.p2.position
        
        # Get widths
        p1_front = self.p1.constants.ground_front
        p1_back = self.p1.constants.ground_back
        p2_front = self.p2.constants.ground_front
        p2_back = self.p2.constants.ground_back
        
        # Calculate push boxes
        if self.p1.facing > 0:
            p1_left = p1_x - p1_back
            p1_right = p1_x + p1_front
        else:
            p1_left = p1_x - p1_front
            p1_right = p1_x + p1_back
        
        if self.p2.facing > 0:
            p2_left = p2_x - p2_back
            p2_right = p2_x + p2_front
        else:
            p2_left = p2_x - p2_front
            p2_right = p2_x + p2_back
        
        # Check overlap
        if p1_right > p2_left and p1_left < p2_right:
            # Calculate push amount
            overlap = min(p1_right - p2_left, p2_right - p1_left)
            push = overlap / 2
            
            # Push apart
            if p1_x < p2_x:
                self.p1.position = (p1_x - push, p1_y)
                self.p2.position = (p2_x + push, p2_y)
            else:
                self.p1.position = (p1_x + push, p1_y)
                self.p2.position = (p2_x - push, p2_y)
    
    def _update_camera(self) -> None:
        """Update camera position to follow the fight."""
        p1_x, _ = self.p1.position
        p2_x, _ = self.p2.position
        
        # Camera follows midpoint between players
        target_x = (p1_x + p2_x) / 2
        
        # Smooth camera movement
        self.camera_x += (target_x - self.camera_x) * 0.1
        
        # Clamp to stage bounds
        stage_bound = self.stage.bound_left if hasattr(self.stage, 'bound_left') else -200
        stage_right = self.stage.bound_right if hasattr(self.stage, 'bound_right') else 200
        
        half_screen = CONFIG.video.game_width / 2
        self.camera_x = max(stage_bound + half_screen, 
                           min(stage_right - half_screen, self.camera_x))
    
    def _update_combo_display(self) -> None:
        """Update combo display timers."""
        if self.p1_combo.display_timer > 0:
            self.p1_combo.display_timer -= 1
            if self.p1_combo.display_timer == 0:
                self.p1_combo.reset()
        
        if self.p2_combo.display_timer > 0:
            self.p2_combo.display_timer -= 1
            if self.p2_combo.display_timer == 0:
                self.p2_combo.reset()
    
    def _enforce_boundaries(self) -> None:
        """Keep characters within stage boundaries."""
        left_bound = self.stage.bound_left if hasattr(self.stage, 'bound_left') else -200
        right_bound = self.stage.bound_right if hasattr(self.stage, 'bound_right') else 200
        
        # P1
        p1_x, p1_y = self.p1.position
        p1_x = max(left_bound, min(right_bound, p1_x))
        p1_y = min(0, p1_y)  # Can't go below ground
        self.p1.position = (p1_x, p1_y)
        
        # P2
        p2_x, p2_y = self.p2.position
        p2_x = max(left_bound, min(right_bound, p2_x))
        p2_y = min(0, p2_y)
        self.p2.position = (p2_x, p2_y)
    
    def _handle_ko(self) -> None:
        """Handle knockout."""
        self.state = FightState.KO
        self.state_timer = 0
        
        # Determine winner
        if self.p1.life <= 0 and self.p2.life <= 0:
            self.round.result = RoundResult.DOUBLE_KO
        elif self.p1.life <= 0:
            self.round.result = RoundResult.P2_WIN
            self.round.p2_rounds_won += 1
        else:
            self.round.result = RoundResult.P1_WIN
            self.round.p1_rounds_won += 1
    
    def _handle_time_over(self) -> None:
        """Handle time running out."""
        # Winner is whoever has more life (percentage)
        p1_percent = self.p1.life / self.p1.max_life
        p2_percent = self.p2.life / self.p2.max_life
        
        if p1_percent > p2_percent:
            self.round.result = RoundResult.TIME_OVER_P1
            self.round.p1_rounds_won += 1
        elif p2_percent > p1_percent:
            self.round.result = RoundResult.TIME_OVER_P2
            self.round.p2_rounds_won += 1
        else:
            self.round.result = RoundResult.DRAW
            self.round.draw_games += 1
        
        self.state = FightState.KO
        self.state_timer = 0
    
    def _update_ko(self) -> None:
        """Update KO state (freeze/slowmo)."""
        if self.state_timer >= self.KO_FREEZE_TICKS:
            self.state = FightState.ROUND_END
            self.state_timer = 0
    
    def _update_round_end(self) -> None:
        """Update round end sequence."""
        if self.state_timer >= self.ROUND_END_TICKS:
            # Check for match end
            rounds_to_win = CONFIG.gameplay.rounds_to_win
            
            if self.round.p1_rounds_won >= rounds_to_win:
                self.state = FightState.MATCH_END
            elif self.round.p2_rounds_won >= rounds_to_win:
                self.state = FightState.MATCH_END
            elif self.round.draw_games >= CONFIG.gameplay.max_draw_games:
                self.state = FightState.DRAW_GAME
            else:
                # Next round
                self.round.round_number += 1
                self.round.time_remaining = CONFIG.gameplay.round_time
                self.round.time_ticks = self.round.time_remaining * 60
                self._setup_round()
    
    def _update_draw_game(self) -> None:
        """Update draw game state."""
        # Could go to sudden death or end match
        pass
    
    def _handle_pause(self, p1_input: 'PlayerInput', p2_input: 'PlayerInput') -> None:
        """Handle pause menu."""
        # Check for unpause
        if self.pause_player == 0:
            if p1_input.button_pressed(Button.START):  # START
                self.paused = False
        else:
            if p2_input.button_pressed(Button.START):
                self.paused = False
    
    def render(self, renderer: 'Renderer') -> None:
        """Render the fight."""
        # Render stage background
        self.stage.render(renderer, self.camera_x, self.camera_y)
        
        # Render characters (sorted by z-order)
        chars = sorted([self.p1, self.p2], 
                      key=lambda c: c.sprite_priority)
        
        for char in chars:
            char.render(renderer, self.camera_x, self.camera_y)
        
        # Render stage foreground
        self.stage.render_foreground(renderer, self.camera_x, self.camera_y)
        
        # Render HUD
        self._render_hud(renderer)
        
        # Render pause overlay
        if self.paused:
            self._render_pause(renderer)
    
    def _render_hud(self, renderer: 'Renderer') -> None:
        """Render the fight HUD (life bars, timer, etc.)."""
        if self._hud is None:
            from ui.hud import HUD
            self._hud = HUD()
        self._hud.render(renderer, self)
    
    def _render_pause(self, renderer: 'Renderer') -> None:
        """Render pause overlay."""
        # Semi-transparent overlay
        pass
