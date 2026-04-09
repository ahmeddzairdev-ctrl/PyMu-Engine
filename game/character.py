def render(self, surface):
    # Check if the sprite exists before trying to render
    if self.sprite:
        # Calculate sprite position considering offsets
        offset_x = self.sprite_offset_x
        offset_y = self.sprite_offset_y
        sprite_position = (self.x + offset_x, self.y + offset_y)

        # Adjust for facing direction
        if self.facing_direction == 'right':
            sprite = self.sprite
        elif self.facing_direction == 'left':
            sprite = self.sprite_flipped
        else:
            sprite = self.sprite  # Default to original if facing direction is unknown

        # Render the sprite at the calculated position
        surface.blit(sprite, sprite_position)
    else:
        # Fallback placeholder rendering
        placeholder_image = self.get_placeholder_image()
        surface.blit(placeholder_image, (self.x, self.y))

    # Additional rendering logic can be added here if needed