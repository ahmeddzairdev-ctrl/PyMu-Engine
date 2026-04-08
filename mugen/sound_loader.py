"""
MUGEN SND (Sound File) loader.
Parses the binary .snd format used by WinMUGEN and MUGEN 1.x.
"""

import struct
from pathlib import Path
from typing import Dict, Optional, Tuple
import pygame
from io import BytesIO


class SoundLoader:
    """
    Loads a MUGEN .snd file and provides access to individual sound samples
    keyed by (group, index).
    """

    SIGNATURE = b"ElecbyteSnd\x00"

    def __init__(self, filepath: str):
        self.filepath = Path(filepath)
        # Maps (group, index) -> pygame.mixer.Sound
        self.sounds: Dict[Tuple[int, int], pygame.mixer.Sound] = {}
        self._load()

    # ------------------------------------------------------------------

    def _load(self) -> None:
        with open(self.filepath, "rb") as f:
            sig = f.read(12)
            if sig != self.SIGNATURE:
                raise ValueError(f"Not a valid SND file: {self.filepath}")

            # Version (4 bytes, unused)
            f.read(4)

            # Number of sounds and offset of first subfile
            num_sounds, subfile_offset = struct.unpack("<II", f.read(8))

            f.seek(subfile_offset)
            for _ in range(num_sounds):
                self._read_sound(f)

    def _read_sound(self, f) -> None:
        next_offset = struct.unpack("<I", f.read(4))[0]
        data_length = struct.unpack("<I", f.read(4))[0]
        group, index = struct.unpack("<II", f.read(8))

        key = (group, index)

        if data_length > 0:
            raw = f.read(data_length)
            try:
                sound = pygame.mixer.Sound(buffer=raw)
                self.sounds[key] = sound
            except Exception:
                pass  # Unsupported format in this sample

        if next_offset > 0:
            f.seek(next_offset)

    # ------------------------------------------------------------------

    def get(self, group: int, index: int) -> Optional[pygame.mixer.Sound]:
        """Return the sound at (group, index), or None if not found."""
        return self.sounds.get((group, index))

    def play(self, group: int, index: int) -> None:
        """Play the sound at (group, index) if it exists."""
        sound = self.get(group, index)
        if sound:
            sound.play()

    # ------------------------------------------------------------------

    @staticmethod
    def load(filepath: str) -> "SoundLoader":
        """Convenience factory — mirrors SpriteLoader.load()."""
        return SoundLoader(filepath)
