def render(self):
    # Check if sprite exists, if not fallback to placeholder
    if self.sprite is None:
        self.render_placeholder()
        return

    # Calculate offsets based on facing direction
    offset_x = 0
    offset_y = 0
    if self.facing_direction == 'left':
        offset_x = -self.sprite.width // 2
    elif self.facing_direction == 'right':
        offset_x = self.sprite.width // 2
    elif self.facing_direction == 'up':
        offset_y = -self.sprite.height // 2
    elif self.facing_direction == 'down':
        offset_y = self.sprite.height // 2

    # Render the sprite with calculated offsets
    draw_image(self.sprite, self.position.x + offset_x, self.position.y + offset_y)

# Placeholder rendering method
def render_placeholder(self):
    # Implement placeholder rendering logic here
    draw_image(self.placeholder_sprite, self.position.x, self.position.y)