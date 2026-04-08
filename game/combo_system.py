"""
Combo system — tracks hit counts and applies damage scaling.
"""

from dataclasses import dataclass


# Damage scaling table (MUGEN default): hit_count → multiplier
_SCALING = [
    1.0,   # 1st hit
    1.0,   # 2nd
    0.8,   # 3rd
    0.7,   # 4th
    0.6,   # 5th
    0.5,   # 6th+
]


def get_damage_scale(hit_count: int) -> float:
    """Return the damage multiplier for a hit at *hit_count* (1-based)."""
    idx = max(0, min(hit_count - 1, len(_SCALING) - 1))
    return _SCALING[idx]


@dataclass
class ComboTracker:
    """
    Tracks an active combo for one side of the fight.
    Used by Fight to apply damage scaling and display the combo counter.
    """
    hit_count: int   = 0
    total_damage: int = 0
    is_active: bool  = False
    display_timer: int = 0   # Ticks remaining to show the counter

    # ------------------------------------------------------------------

    def register_hit(self, raw_damage: int) -> int:
        """
        Record a hit, apply scaling, and return the actual damage dealt.
        """
        self.hit_count   += 1
        scale             = get_damage_scale(self.hit_count)
        actual            = max(1, int(raw_damage * scale))
        self.total_damage += actual
        self.is_active    = True
        self.display_timer = 90   # Show counter for 1.5 s @ 60 fps
        return actual

    def tick(self) -> None:
        """Call once per frame to count down the display timer."""
        if self.display_timer > 0:
            self.display_timer -= 1
            if self.display_timer == 0:
                self.reset()

    def reset(self) -> None:
        self.hit_count    = 0
        self.total_damage = 0
        self.is_active    = False
        self.display_timer = 0
