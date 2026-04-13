"""
MUGEN SND sound file loader.
Ported from sndextract.c by Popov Evgeniy Alekseyevich.

SND format (format.h):
  head:    signature(12) + version(4) + amount(4) + first_offset(4) + comment(488)
  subhead: next_offset(4) + legth(4) + group(4) + sample(4)  [total 16 bytes]

CRITICAL: The C code NEVER uses the `legth` field for WAV extraction.
  C formula:  wav_length = next_offset - ftell_after_reading_subheader
            = next_offset - (subheader_start + 16)
  Our old bug: wav_end = wav_start + legth   ← legth can be 0 or wrong
  Correct:     wav_end = next_offset

For the last sound (no valid next_offset), extract_last() uses:
  length = file_size - ftell_after_skipping_subheader

The `to_signed` conversion from snd_parser.rs:
  8-bit WAV in SND is unsigned PCM → must convert to signed before pygame:
  (byte - 128) & 0xFF   applied ONLY to the data chunk bytes.
"""

import struct
import io
from pathlib import Path
from typing import Dict, Optional, Tuple

import pygame


class SoundLoader:
    """Loads a MUGEN .snd file. Keys are (group, sample) tuples."""

    SIGNATURE = b"ElecbyteSnd\x00"

    def __init__(self, filepath: str):
        self.filepath = Path(filepath)
        self.sounds: Dict[Tuple[int, int], pygame.mixer.Sound] = {}
        self._load()

    # ------------------------------------------------------------------

    def _load(self) -> None:
        try:
            data = self.filepath.read_bytes()
        except Exception as e:
            print(f"  [SND] {self.filepath.name}: cannot read: {e}")
            return

        fsize = len(data)
        if fsize < 24 or data[:12] != self.SIGNATURE:
            print(f"  [SND] {self.filepath.name}: bad signature")
            return

        # head: sig(12) + ver(4) + amount(4) + first_offset(4)
        amount       = struct.unpack_from('<I', data, 16)[0]
        first_offset = struct.unpack_from('<I', data, 20)[0]

        if first_offset >= fsize:
            print(f"  [SND] {self.filepath.name}: bad first_offset={first_offset}")
            return

        print(f"  [SND] {self.filepath.name}: {amount} sounds, subheader@0x{first_offset:x}")

        loaded = 0
        pos    = first_offset

        for idx in range(amount):
            if pos + 16 > fsize:
                break

            # subhead: next_offset(4) + legth(4) + group(4) + sample(4)
            next_offset = struct.unpack_from('<I', data, pos)[0]
            # legth (note typo in original) is intentionally ignored:
            # C code always uses: length = next_offset - ftell_after_subheader
            groupno     = struct.unpack_from('<I', data, pos + 8)[0]
            sampleno    = struct.unpack_from('<I', data, pos + 12)[0]

            wav_start = pos + 16  # immediately after subhead

            # C extract(): length = next_offset - ftell(input) [after reading subhead]
            # C extract_last(): length = file_size - ftell(after skipping subhead)
            if idx < amount - 1:
                # Non-last sound: WAV data ends at next subheader
                wav_end = next_offset if (next_offset > wav_start and
                                          next_offset <= fsize) else fsize
            else:
                # Last sound: extract_last() skips subhead then reads to EOF
                wav_end = fsize

            wav_bytes = data[wav_start:wav_end]

            if len(wav_bytes) >= 12:
                sound = self._make_sound(wav_bytes)
                if sound is not None:
                    self.sounds[(groupno, sampleno)] = sound
                    loaded += 1

            # Advance: jump to next subheader
            if next_offset > pos and next_offset < fsize:
                pos = next_offset
            else:
                break

        print(f"  [SND] {self.filepath.name}: loaded {loaded}/{amount} sounds")

    # ------------------------------------------------------------------

    def _make_sound(self, wav_bytes: bytes) -> Optional[pygame.mixer.Sound]:
        """
        Build a pygame.mixer.Sound from raw WAV bytes.
        Applies to_signed conversion for 8-bit unsigned PCM (sndextract.c / snd_parser.rs).
        """
        if wav_bytes[:4] != b'RIFF':
            return None
        try:
            wav_fixed = self._fix_8bit_unsigned(wav_bytes)
            return pygame.mixer.Sound(file=io.BytesIO(wav_fixed))
        except Exception:
            try:
                # Fallback: try raw PCM extraction
                pcm = self._extract_pcm(wav_bytes)
                if pcm:
                    return pygame.mixer.Sound(buffer=pcm)
            except Exception:
                pass
        return None

    def _fix_8bit_unsigned(self, wav: bytes) -> bytes:
        """
        snd_parser.rs to_signed(): (byte - 128) & 0xFF
        Applied only to the PCM data chunk — NOT the headers.
        """
        fmt_pos = wav.find(b'fmt ')
        if fmt_pos < 0:
            return wav
        try:
            audio_format    = struct.unpack_from('<H', wav, fmt_pos + 8)[0]
            bits_per_sample = struct.unpack_from('<H', wav, fmt_pos + 22)[0]
        except struct.error:
            return wav

        if audio_format != 1 or bits_per_sample != 8:
            return wav   # not 8-bit PCM, no conversion needed

        data_pos = wav.find(b'data')
        if data_pos < 0:
            return wav
        try:
            data_size = struct.unpack_from('<I', wav, data_pos + 4)[0]
        except struct.error:
            return wav

        pcm_start = data_pos + 8
        pcm_end   = min(pcm_start + data_size, len(wav))

        # to_signed: unsigned [0..255] → signed representation
        converted = bytes((b - 128) & 0xFF for b in wav[pcm_start:pcm_end])

        result = bytearray(wav[:pcm_start])
        result.extend(converted)
        result.extend(wav[pcm_end:])
        return bytes(result)

    @staticmethod
    def _extract_pcm(wav: bytes) -> Optional[bytes]:
        dp = wav.find(b'data')
        if dp < 0:
            return None
        try:
            size = struct.unpack_from('<I', wav, dp + 4)[0]
            return wav[dp + 8: dp + 8 + size]
        except Exception:
            return wav[44:] if len(wav) > 44 else None

    # ------------------------------------------------------------------

    def get(self, group: int, index: int) -> Optional[pygame.mixer.Sound]:
        return self.sounds.get((group, index))

    def play(self, group: int, index: int) -> None:
        s = self.get(group, index)
        if s:
            try:
                s.play()
            except Exception:
                pass

    @staticmethod
    def load(filepath: str) -> "SoundLoader":
        return SoundLoader(filepath)
