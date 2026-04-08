"""
Audio manager — wraps pygame.mixer for BGM and SFX playback.
"""

import pygame
from typing import Dict, Optional
from config import CONFIG


class AudioManager:
    """Manages sound and music playback using pygame.mixer."""

    def __init__(self):
        self._initialized = False
        self._sounds: Dict[str, pygame.mixer.Sound] = {}
        self._current_music: Optional[str] = None

        try:
            pygame.mixer.init(
                frequency=CONFIG.audio.sample_rate,
                size=-16,
                channels=2,
                buffer=CONFIG.audio.buffer_size,
            )
            pygame.mixer.set_num_channels(CONFIG.audio.channels)
            self._initialized = True
        except pygame.error as e:
            print(f"AudioManager: failed to init mixer — {e}")

    # ------------------------------------------------------------------
    # BGM
    # ------------------------------------------------------------------

    def play_music(self, filepath: str, loops: int = -1) -> None:
        """Load and play background music."""
        if not self._initialized:
            return
        if self._current_music == filepath:
            return
        try:
            pygame.mixer.music.load(filepath)
            pygame.mixer.music.set_volume(
                CONFIG.audio.master_volume * CONFIG.audio.bgm_volume
            )
            pygame.mixer.music.play(loops)
            self._current_music = filepath
        except pygame.error as e:
            print(f"AudioManager: cannot play music '{filepath}' — {e}")

    def stop_music(self) -> None:
        if self._initialized:
            pygame.mixer.music.stop()
        self._current_music = None

    def set_bgm_volume(self, volume: float) -> None:
        if self._initialized:
            pygame.mixer.music.set_volume(
                CONFIG.audio.master_volume * max(0.0, min(1.0, volume))
            )

    # ------------------------------------------------------------------
    # SFX
    # ------------------------------------------------------------------

    def load_sound(self, key: str, filepath: str) -> bool:
        """Pre-load a sound effect and store it under *key*."""
        if not self._initialized:
            return False
        try:
            self._sounds[key] = pygame.mixer.Sound(filepath)
            return True
        except pygame.error as e:
            print(f"AudioManager: cannot load sound '{filepath}' — {e}")
            return False

    def play_sound(self, key: str, volume: Optional[float] = None) -> None:
        """Play a pre-loaded sound effect."""
        if not self._initialized:
            return
        sound = self._sounds.get(key)
        if sound:
            vol = (volume if volume is not None else 1.0)
            sound.set_volume(CONFIG.audio.master_volume * CONFIG.audio.sfx_volume * vol)
            sound.play()

    def play_sound_file(self, filepath: str) -> None:
        """Play a sound directly from a file path (no pre-loading)."""
        if not self._initialized:
            return
        try:
            sound = pygame.mixer.Sound(filepath)
            sound.set_volume(CONFIG.audio.master_volume * CONFIG.audio.sfx_volume)
            sound.play()
        except pygame.error as e:
            print(f"AudioManager: cannot play '{filepath}' — {e}")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        if self._initialized:
            pygame.mixer.quit()
            self._initialized = False
