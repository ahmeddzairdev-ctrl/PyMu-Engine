"""
2D physics and collision detection for the MUGEN engine.
Handles gravity, velocity integration, and AABB collision queries.
"""

from typing import List, Tuple, Optional
from config import CONFIG


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

Box = Tuple[float, float, float, float]   # (x1, y1, x2, y2)
Vec2 = Tuple[float, float]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GRAVITY: float = 0.44          # Pixels / tick² (matches MUGEN default)
GROUND_Y: float = 0.0          # World Y of the ground plane
TERMINAL_VEL: float = 20.0     # Max fall speed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def aabb_intersect(a: Box, b: Box) -> bool:
    """Return True if two axis-aligned bounding boxes overlap."""
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def aabb_overlap(a: Box, b: Box) -> Vec2:
    """
    Return the (dx, dy) minimum translation vector to separate *a* from *b*.
    Returns (0, 0) if the boxes do not overlap.
    """
    if not aabb_intersect(a, b):
        return (0.0, 0.0)
    dx = min(a[2], b[2]) - max(a[0], b[0])
    dy = min(a[3], b[3]) - max(a[1], b[1])
    return (dx, dy)


def translate_box(box: Box, dx: float, dy: float) -> Box:
    """Translate a box by (dx, dy)."""
    return (box[0] + dx, box[1] + dy, box[2] + dx, box[3] + dy)


def flip_box_h(box: Box) -> Box:
    """Flip a box horizontally (negate X coordinates)."""
    return (-box[2], box[1], -box[0], box[3])


# ---------------------------------------------------------------------------
# Physics body
# ---------------------------------------------------------------------------

class PhysicsBody:
    """
    Minimal physics body attached to a game entity.

    Coordinates follow MUGEN convention:
        • x increases rightward
        • y increases *upward* (ground is y=0, air is y<0)
    """

    def __init__(self, x: float = 0.0, y: float = 0.0):
        self.x: float = x
        self.y: float = y
        self.vx: float = 0.0
        self.vy: float = 0.0

        self.on_ground: bool = True
        self.apply_gravity: bool = True
        self.gravity: float = GRAVITY
        self.friction: float = 0.85       # Ground friction factor per tick

    # ------------------------------------------------------------------

    def integrate(self) -> None:
        """Step the simulation by one tick."""
        if self.apply_gravity and not self.on_ground:
            self.vy = min(self.vy + self.gravity, TERMINAL_VEL)

        self.x += self.vx
        self.y += self.vy

        # Ground collision
        if self.y >= GROUND_Y:
            self.y = GROUND_Y
            self.vy = 0.0
            self.on_ground = True
        else:
            self.on_ground = False

        # Apply friction when grounded
        if self.on_ground:
            self.vx *= self.friction

    def set_velocity(self, vx: float, vy: float) -> None:
        self.vx = vx
        self.vy = vy

    def add_velocity(self, dvx: float, dvy: float) -> None:
        self.vx += dvx
        self.vy += dvy

    @property
    def position(self) -> Vec2:
        return (self.x, self.y)

    @position.setter
    def position(self, pos: Vec2) -> None:
        self.x, self.y = pos
