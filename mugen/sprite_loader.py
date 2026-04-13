"""
MUGEN SFF sprite loader — v1 and v2.
Ported directly from the Rust reference (sffv1.rs, sffv2.rs, rle5.rs, lz5.rs, pcx.rs).

SFF v1 key facts (from sffv1.rs):
  - Header: sig(12) + ver(4) + num_groups(4) + num_images(4) + first_offset(4) +
            subheader_size(4) + is_shared(1) + reserved(3) + comments(476) = 512 bytes
  - Sprite subheader (32 bytes): next_offset(4) + subfile_len(4) + x(i16) + y(i16) +
    groupno(i16) + imageno(i16) + linked(i16) + is_shared(1) + blank(13)
  - PCX data size = next_offset - current_offset - 32  (NOT subfile_len!)
  - Palette: sprites with is_shared=False carry their own PCX palette (last 769 bytes)
             sprites with is_shared=True reuse the last seen own-palette
  - Shared palette: prefer group=0 img=0, then group=9000 img=0, then first own-palette sprite

SFF v2 key facts (from sffv2.rs):
  - Sprite header reads groupno/imageno as i16 (signed)
  - Palette stored as RGBA in ldata region
  - Format 0/1 = raw; 2 = RLE8; 3 = RLE5; 4 = LZ5

Decoders (from rle5.rs, lz5.rs):
  - All decoders skip first 4 bytes (uncompressed size header)
  - RLE8: (ch & 0xC0)==0x40 → run of (ch & 0x3F) × next_byte; else → literal ch
  - RLE5: packet-based with run_len, color_bit, data_len fields
  - LZ5: control-byte driven with RLE and back-reference packets

PCX (from pcx.rs):
  - 8-bit paletted PCX: palette embedded at end (flag 0x0C + 256 × RGB)
  - Index 0 is always alpha=0 (transparent)
"""

from __future__ import annotations
import struct
import os
import logging
from pathlib import Path
from io import BytesIO
from typing import Dict, List, Tuple, Optional, BinaryIO

import pygame

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

class SpriteInfo:
    __slots__ = ('group', 'index', 'x_offset', 'y_offset', 'linked', 'linked_index')

    def __init__(self, group, index, x_offset, y_offset, linked=False, linked_index=0):
        self.group = group
        self.index = index
        self.x_offset = x_offset
        self.y_offset = y_offset
        self.linked = linked
        self.linked_index = linked_index   # sequential insertion order


class Palette:
    """256-colour RGBA palette. Index 0 is always transparent."""
    __slots__ = ('colors',)

    def __init__(self, colors: List[Tuple[int, int, int, int]]):
        self.colors = colors   # list of (r,g,b,a), length 256


def _default_palette() -> Palette:
    c = [(i, i, i, 255 if i else 0) for i in range(256)]
    return Palette(c)


def _flat_rgb_to_palette(flat: List[int]) -> Palette:
    """768-byte flat RGB list → Palette (index 0 transparent)."""
    colors = []
    for i in range(256):
        r = flat[i*3]     if i*3     < len(flat) else 0
        g = flat[i*3 + 1] if i*3 + 1 < len(flat) else 0
        b = flat[i*3 + 2] if i*3 + 2 < len(flat) else 0
        colors.append((r, g, b, 0 if i == 0 else 255))
    return Palette(colors)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _render_indexed(pixels: bytes, width: int, height: int, palette: Palette) -> Optional[pygame.Surface]:
    """
    Map palette indices to RGBA → pygame.Surface.
    Uses pygame.image.fromstring which correctly preserves alpha.
    Both numpy and pure-Python paths go through fromstring.
    """
    needed = width * height
    if not pixels or width <= 0 or height <= 0:
        return None
    if len(pixels) < needed:
        pixels = pixels + bytes(needed - len(pixels))

    col = palette.colors

    if HAS_NUMPY:
        try:
            idx = np.frombuffer(pixels[:needed], dtype=np.uint8)
            pa  = np.array(col, dtype=np.uint8)   # (256, 4)
            rgba = pa[idx]                          # (w*h, 4) in row-major
            return pygame.image.fromstring(rgba.tobytes(), (width, height), 'RGBA')
        except Exception as e:
            log.debug(f"numpy render failed: {e}")

    # Pure-Python
    rgba = bytearray(needed * 4)
    for i in range(needed):
        r, g, b, a = col[pixels[i] if i < len(pixels) else 0]
        rgba[i*4]   = r
        rgba[i*4+1] = g
        rgba[i*4+2] = b
        rgba[i*4+3] = a
    return pygame.image.fromstring(bytes(rgba), (width, height), 'RGBA')


# ---------------------------------------------------------------------------
# PCX decoding (from pcx.rs)
# ---------------------------------------------------------------------------

def _pcx_palette_from_data(data: bytes) -> Optional[List[int]]:
    """Extract embedded 768-byte palette (flag 0x0C at -769)."""
    if len(data) >= 769 and data[-769] == 0x0C:
        return list(data[-768:])
    return None


def _pcx_to_surface(pcx_data: bytes, palette_override: Optional[List[int]] = None) -> Optional[pygame.Surface]:
    """
    Decode PCX → pygame.Surface.
    palette_override: flat 768-byte RGB list. If None, use embedded palette.
    Index 0 is transparent per pcx.rs: 'if i == 0 { 0 } else { 255 }'
    """
    if HAS_PIL:
        try:
            img = Image.open(BytesIO(pcx_data))
            img.load()
            width, height = img.size
            if img.mode != 'P':
                img = img.convert('P')
            flat_pal = palette_override or _pcx_palette_from_data(pcx_data) or img.getpalette() or ([0]*768)
            pal = _flat_rgb_to_palette(flat_pal)
            pixels = img.tobytes()
            return _render_indexed(pixels, width, height, pal)
        except Exception as e:
            log.debug(f"PIL PCX failed: {e}")

    # Pure-Python decoder
    return _pcx_pure_python(pcx_data, palette_override)


def _pcx_pure_python(data: bytes, palette_override: Optional[List[int]]) -> Optional[pygame.Surface]:
    if len(data) < 128 or data[0] != 0x0A or data[2] != 1 or data[3] != 8:
        return None
    x_min, y_min, x_max, y_max = struct.unpack_from('<HHHH', data, 4)
    bpl     = struct.unpack_from('<H', data, 66)[0]
    nplanes = data[65]
    width   = x_max - x_min + 1
    height  = y_max - y_min + 1
    if width <= 0 or height <= 0:
        return None

    # Decode RLE scanlines
    out = bytearray()
    i = 128
    needed = bpl * height * nplanes
    while i < len(data) and len(out) < needed:
        b = data[i]; i += 1
        if b > 0xC0:
            count = b & 0x3F
            if i < len(data):
                v = data[i]; i += 1
                out.extend([v] * count)
        else:
            out.append(b)

    pixels = bytearray()
    for y in range(height):
        pixels.extend(out[y * bpl * nplanes: y * bpl * nplanes + width])

    flat_pal = palette_override or _pcx_palette_from_data(data) or [i // 3 for i in range(768)]
    pal = _flat_rgb_to_palette(flat_pal)
    return _render_indexed(bytes(pixels), width, height, pal)


# ---------------------------------------------------------------------------
# SFF v2 decoders (from rle5.rs, lz5.rs)
# ---------------------------------------------------------------------------

def _rle8_decode(data: bytes, width: int, height: int) -> bytes:
    """
    Exact port of rle5.rs decode_rle8:
      Skip 4 bytes.
      if (ch & 0xC0) == 0x40: push next_byte (ch & 0x3F) times
      else: push ch
    """
    out = bytearray()
    i = 4   # skip 4-byte header
    while i < len(data):
        ch = data[i]; i += 1
        if (ch & 0xC0) == 0x40:
            count = ch & 0x3F
            if i < len(data):
                color = data[i]; i += 1
                out.extend([color] * count)
        else:
            out.append(ch)
    size = width * height
    if len(out) < size:
        out.extend(bytes(size - len(out)))
    return bytes(out[:size])


def _rle5_decode(data: bytes, width: int, height: int) -> bytes:
    """
    Exact port of rle5.rs decode_rle5.
    Packet: run_len(1) + byte2(1) where color_bit=byte2>>7, data_len=byte2&0x7F
    """
    out = bytearray()
    i = 4   # skip 4-byte header
    color = 0

    while i < len(data):
        if i >= len(data): break
        run_len = data[i]; i += 1
        if i >= len(data): break
        b2 = data[i]; i += 1
        color_bit = b2 >> 7
        data_len  = b2 & 0x7F

        if color_bit == 1:
            if i >= len(data): break
            color = data[i]; i += 1
        else:
            color = 0

        out.extend([color] * run_len)

        for _ in range(data_len):
            if i >= len(data): break
            one_byte = data[i]; i += 1
            color    = one_byte & 0x1F
            run_len2 = one_byte >> 5
            out.extend([color] * run_len2)

    size = width * height
    if len(out) < size:
        out.extend(bytes(size - len(out)))
    return bytes(out[:size])


def _lz5_decode(data: bytes, width: int, height: int) -> bytes:
    """
    Exact port of lz5.rs decode_lz5.
    Control byte flags[0..7] = bits 0..7 (lsb first).
    flag=0: RLE packet. flag=1: LZ (back-reference) packet.
    """
    if len(data) < 4:
        return bytes(width * height)

    dest = bytearray()
    i = 4   # skip 4-byte uncompressed-size header

    # State for Lz5LzPacket recycled bits
    recycled            = 0
    recycled_bits_filled = 0

    while i < len(data):
        if i >= len(data): break
        ctrl_byte = data[i]; i += 1

        for bit in range(8):
            if i >= len(data): break
            flag = (ctrl_byte >> bit) & 1

            if flag == 0:
                # RLE packet (Lz5RlePacket)
                if i >= len(data): break
                byte1 = data[i]; i += 1
                num_times = (byte1 & 0xE0) >> 5
                color     = byte1 & 0x1F
                if num_times == 0:
                    if i >= len(data): break
                    byte2 = data[i]; i += 1
                    num_times = byte2 + 8
                dest.extend([color] * num_times)

            else:
                # LZ packet (Lz5LzPacket)
                if i >= len(data): break
                byte1  = data[i]; i += 1
                length = byte1 & 0x3F

                if length == 0:
                    # Long form: 3 bytes total
                    if i + 1 >= len(data): break
                    byte2 = data[i]; i += 1
                    byte3 = data[i]; i += 1
                    offset = (byte1 & 0xC0) * 4 + byte2 + 1
                    length = byte3 + 3
                else:
                    # Short form with recycled bits
                    length += 1
                    tmp_recyc = byte1 & 0xC0
                    # shift right by recycled_bits_filled
                    tmp_recyc >>= recycled_bits_filled
                    recycled += tmp_recyc
                    recycled_bits_filled += 2

                    if recycled_bits_filled < 8:
                        if i >= len(data): break
                        byte2  = data[i]; i += 1
                        offset = byte2 + 1
                    else:
                        offset = recycled + 1
                        recycled = 0
                        recycled_bits_filled = 0

                # Copy last `offset` bytes of dest, `length` times
                dlen = len(dest)
                if offset > dlen:
                    src = bytes(dest)   # copy all
                else:
                    src = bytes(dest[dlen - offset:])
                # Tile src to fill length
                needed_src = src if len(src) >= length else src * (length // len(src) + 1)
                dest.extend(needed_src[:length])

    size = width * height
    if len(dest) < size:
        dest.extend(bytes(size - len(dest)))
    return bytes(dest[:size])


def _decode_sffv2_pixels(fmt: int, data: bytes, w: int, h: int) -> Tuple[bytes, str]:
    """Decode SFF v2 pixel data. Returns (pixels, 'indexed'|'rgba')."""
    size = w * h
    try:
        if fmt in (0, 1):
            pixels = data[:size]
        elif fmt == 2:
            pixels = _rle8_decode(data, w, h)
        elif fmt == 3:
            pixels = _rle5_decode(data, w, h)
        elif fmt in (4, 25):
            pixels = _lz5_decode(data, w, h)
        elif fmt == 10:
            # PNG embedded
            if HAS_PIL:
                img = Image.open(BytesIO(data)).convert('RGBA')
                return bytes(img.tobytes()), 'rgba'
            return bytes(size), 'indexed'
        else:
            pixels = data[:size] if len(data) >= size else data + bytes(size - len(data))
    except Exception as e:
        log.debug(f"v2 decode fmt={fmt}: {e}")
        return bytes(size), 'indexed'

    if len(pixels) < size:
        pixels = pixels + bytes(size - len(pixels))
    return bytes(pixels[:size]), 'indexed'


# ---------------------------------------------------------------------------
# SFF v1 reader — ported from sffv1.rs
# ---------------------------------------------------------------------------

class SFFv1Reader:
    """
    Exact port of sffv1.rs read_images logic.

    Key difference from all previous versions:
    - PCX data size = next_offset - current_offset - 32  (NOT subfile_len)
    - is_shared flag drives palette inheritance
    - Palette chosen: prefer group=0, then group=9000/img=0, then first own-palette
    """

    def __init__(self, filepath: str):
        self.filepath    = Path(filepath)
        self.sprites:    Dict[Tuple[int, int], pygame.Surface] = {}
        self.sprite_info: Dict[Tuple[int, int], SpriteInfo]   = {}
        self._key_order: List[Tuple[int, int]] = []
        # Maps sequential counter → (group, index) for linked sprite resolution
        self._counter_to_key: Dict[int, Tuple[int, int]] = {}
        self._load()

    def _load(self) -> None:
        fsize = os.path.getsize(self.filepath)

        with open(self.filepath, 'rb') as f:
            raw = f.read(512)   # full header

        if len(raw) < 36 or raw[:11] != b'ElecbyteSpr':
            raise ValueError(f"Bad SFF v1 signature in {self.filepath.name}")

        # Header fields (sffv1.rs read_file_header)
        # sig(12) + ver(4) + num_groups(4) + num_images(4) + first_offset(4) + ...
        num_groups  = struct.unpack_from('<I', raw, 16)[0]
        num_images  = struct.unpack_from('<I', raw, 20)[0]
        first_offset= struct.unpack_from('<I', raw, 24)[0]
        is_shared_file = raw[32] != 0   # is_shared flag in file header

        if first_offset == 0 or first_offset >= fsize:
            first_offset = 512

        print(f"  [SFF v1] {self.filepath.name}: {num_images} images, first@0x{first_offset:x}, is_shared={is_shared_file}")

        # ── Pre-seed palette from sprite 0 (C: extract_first) ──────────────
        # sffdecompiler.c extract_first():
        #   palette = last 768 bytes of sprite 0's PCX data
        #   i.e. file bytes [sprite0_next_offset - 768 : sprite0_next_offset]
        # This guarantees pallete_ref is never all-zeros before the main loop.
        pallete_ref: bytes = bytes(768)   # fallback if pre-seed fails
        with open(self.filepath, 'rb') as _pf:
            _pf.seek(first_offset)
            _sub0 = _pf.read(32)
            if len(_sub0) == 32:
                _next0 = struct.unpack_from('<I', _sub0, 0)[0]
                if _next0 > 768 and _next0 <= fsize:
                    _pf.seek(_next0 - 768)
                    _seed = _pf.read(768)
                    if len(_seed) == 768:
                        pallete_ref = _seed

        # Track data structures matching sffv1.rs
        sffdata: Dict[int, dict] = {}
        ind_image: List[int] = []
        shared_image: List[int] = []

        actual_offset = first_offset
        counter = 0

        with open(self.filepath, 'rb') as f:
            while counter < num_images:
                if actual_offset == 0 or actual_offset >= fsize:
                    break

                f.seek(actual_offset)
                subhdr_raw = f.read(32)
                if len(subhdr_raw) < 32:
                    break

                # sff_subhead (format.h):
                # next_offset(u32) + length(u32) + x(i16) + y(i16) +
                # group(u16) + image(u16) + preversion(u16) + same_palette(u8) + comments(13)
                next_offset   = struct.unpack_from('<I', subhdr_raw, 0)[0]
                subfile_len   = struct.unpack_from('<I', subhdr_raw, 4)[0]
                x             = struct.unpack_from('<h', subhdr_raw, 8)[0]   # signed
                y             = struct.unpack_from('<h', subhdr_raw, 10)[0]  # signed
                groupno       = struct.unpack_from('<H', subhdr_raw, 12)[0]  # unsigned per format.h
                imageno       = struct.unpack_from('<H', subhdr_raw, 14)[0]  # unsigned per format.h
                linked        = struct.unpack_from('<H', subhdr_raw, 16)[0]  # preversion = unsigned
                spr_is_shared = subhdr_raw[18] != 0  # same_palette byte

                # PCX data size = next_offset - current_offset - 32  (sffdecompiler.c)
                # For the last sprite next_offset=0, use file size instead.
                if next_offset > actual_offset:
                    array_size = next_offset - actual_offset - 32
                elif next_offset == 0 and subfile_len > 0:
                    # Last sprite: use fsize to compute, or fall back to subfile_len
                    array_size = fsize - (actual_offset + 32)
                    if array_size <= 0:
                        array_size = subfile_len
                else:
                    array_size = subfile_len

                key = (groupno, imageno)

                info = SpriteInfo(groupno, imageno, x, y,
                                  linked=(array_size == 0),
                                  linked_index=linked)
                self.sprite_info[key] = info
                self._key_order.append(key)
                self._counter_to_key[counter] = key

                surface = None

                if array_size > 0:
                    # Read PCX data (sffv1.rs: tmp_arr = reader.get_buffer(array_size))
                    f.seek(actual_offset + 32)
                    tmp_arr = f.read(array_size)

                    if is_shared_file and spr_is_shared:
                        # Shared sprite: force the last seen own-palette.
                        # The PCX may have a blank/wrong embedded palette.
                        pal_to_use = list(pallete_ref) if len(pallete_ref) == 768 else None
                        shared_image.append(counter)
                        surface = _pcx_to_surface(tmp_arr, pal_to_use)

                    elif not is_shared_file and spr_is_shared:
                        # Non-shared file, but this sprite reuses the last palette
                        pal_to_use = list(pallete_ref) if len(pallete_ref) == 768 else None
                        surface = _pcx_to_surface(tmp_arr, pal_to_use)

                    else:
                        # spr_is_shared == False: sprite carries its own PCX palette
                        ind_image.append(counter)
                        extracted = _pcx_palette_from_data(tmp_arr)
                        if extracted:
                            pallete_ref = bytes(extracted)
                        surface = _pcx_to_surface(tmp_arr)

                    if surface is None:
                        print(f"  [SFF v1] WARNING: ({groupno},{imageno}) PCX decode failed")

                else:
                    # Linked sprite: reuse surface from linked index
                    linked_item = sffdata.get(linked)
                    if linked_item:
                        surface = linked_item['surface']
                        if is_shared_file and spr_is_shared:
                            shared_image.append(counter)
                    # else: leave surface=None (linked target not yet loaded)

                sffdata[counter] = {
                    'surface': surface,
                    'groupno': groupno,
                    'imageno': imageno,
                    'x': x, 'y': y,
                    'is_shared': spr_is_shared,
                    'key': key,
                }

                if surface:
                    self.sprites[key] = surface

                actual_offset = next_offset if next_offset > 0 else 0
                counter += 1

        print(f"  [SFF v1] {self.filepath.name}: loaded {len(self.sprites)}/{num_images} sprites")

    def get_sprite(self, group: int, index: int) -> Optional[pygame.Surface]:
        key  = (group, index)
        info = self.sprite_info.get(key)
        if info is None:
            return None
        if info.linked:
            # Use _counter_to_key for exact counter→key mapping (sffv1.rs: spr.linked as i32)
            src_key = self._counter_to_key.get(info.linked_index)
            if src_key:
                return self.sprites.get(src_key)
            # Fallback: sequential _key_order index
            si = info.linked_index
            if 0 <= si < len(self._key_order):
                return self.sprites.get(self._key_order[si])
            return None
        return self.sprites.get(key)

    def get_sprite_offset(self, group: int, index: int) -> Tuple[int, int]:
        info = self.sprite_info.get((group, index))
        return (info.x_offset, info.y_offset) if info else (0, 0)

# ---------------------------------------------------------------------------

class SFFv2Reader:
    """Exact port of sffv2.rs."""

    def __init__(self, filepath: str):
        self.filepath     = Path(filepath)
        self._data        = self.filepath.read_bytes()
        self.sprites:     Dict[Tuple[int, int], pygame.Surface] = {}
        self.sprite_info: Dict[Tuple[int, int], SpriteInfo]     = {}
        self._key_order:  List[Tuple[int, int]] = []
        self._palettes:   List[Optional[Palette]] = []
        self._load()

    def _load(self) -> None:
        d = self._data
        if len(d) < 0x60:
            raise ValueError("SFF v2 file too short")
        if d[:11] != b'ElecbyteSpr':
            raise ValueError(f"Bad SFF v2 signature in {self.filepath.name}")

        # FileHeader from sffv2.rs FileHeader::read
        # sig(12)+ver(4)+res(4)+res(4)+compat(4)+res(4)+res(4)+
        # first_sprnode(4)+total_frames(4)+first_palnode(4)+total_palettes(4)+
        # ldata_off(4)+ldata_len(4)+tdata_off(4)+tdata_len(4)+res(4)+res(4)+unused(436)
        spr_off  = struct.unpack_from('<I', d, 0x24)[0]
        spr_cnt  = struct.unpack_from('<I', d, 0x28)[0]
        pal_off  = struct.unpack_from('<I', d, 0x2C)[0]
        pal_cnt  = struct.unpack_from('<I', d, 0x30)[0]
        ldata    = struct.unpack_from('<I', d, 0x34)[0]
        tdata    = struct.unpack_from('<I', d, 0x3C)[0]

        print(f"  [SFF v2] {self.filepath.name}: {spr_cnt} sprites, {pal_cnt} palettes")

        # Load palettes (sffv2.rs PaletteHeader)
        # groupno(i16)+itemno(i16)+numcols(i16)+linked(i16)+offset(u32)+len(u32) = 16 bytes
        self._palettes = [None] * pal_cnt
        links: Dict[int, int] = {}

        for i in range(pal_cnt):
            base = pal_off + i * 16
            if base + 16 > len(d):
                break
            groupno, itemno, numcols, linked_idx = struct.unpack_from('<hhhh', d, base)
            file_off, file_len = struct.unpack_from('<II', d, base + 8)

            if file_len == 0:
                links[i] = linked_idx
                continue

            # matrix_to_pal from sffv2.rs: reads RGBA (4 bytes per color), index 0 transparent
            raw = d[ldata + file_off: ldata + file_off + file_len]
            colors = []
            for ci in range(min(numcols, 256)):
                if ci * 4 + 3 < len(raw):
                    r, g, b, _ = raw[ci*4], raw[ci*4+1], raw[ci*4+2], raw[ci*4+3]
                else:
                    r = g = b = 0
                colors.append((r, g, b, 0 if ci == 0 else 255))
            while len(colors) < 256:
                colors.append((0, 0, 0, 255))
            self._palettes[i] = Palette(colors)

        # Resolve palette links
        for idx, link_id in links.items():
            if 0 <= link_id < len(self._palettes) and self._palettes[link_id] is not None:
                self._palettes[idx] = self._palettes[link_id]
            else:
                self._palettes[idx] = _default_palette()

        # Load sprites (sffv2.rs SpriteHeader)
        # groupno(i16)+imageno(i16)+w(i16)+h(i16)+x(i16)+y(i16)+linked(i16)+
        # fmt(u8)+colordepth(u8)+offset(u32)+len(u32)+palindex(i16)+flags(i16) = 28 bytes
        loaded = 0
        for i in range(spr_cnt):
            base = spr_off + i * 28
            if base + 28 > len(d):
                break

            groupno, imageno = struct.unpack_from('<hh', d, base)
            w, h             = struct.unpack_from('<hh', d, base + 4)
            x, y             = struct.unpack_from('<hh', d, base + 8)
            linked_idx       = struct.unpack_from('<H',  d, base + 12)[0]
            fmt              = d[base + 14]
            colordepth       = d[base + 15]
            file_off         = struct.unpack_from('<I', d, base + 16)[0]
            file_len         = struct.unpack_from('<I', d, base + 20)[0]
            pal_idx          = struct.unpack_from('<h', d, base + 24)[0]
            flags            = struct.unpack_from('<h', d, base + 26)[0]

            key    = (groupno, imageno)
            serial = len(self._key_order)

            info = SpriteInfo(groupno, imageno, x, y,
                              linked=(file_len == 0),
                              linked_index=linked_idx)
            self.sprite_info[key] = info
            self._key_order.append(key)

            if file_len > 0 and w > 0 and h > 0:
                # sffv2.rs: flags==0 → ldata, flags!=0 → tdata
                base_region = tdata if flags != 0 else ldata
                actual_off  = base_region + file_off
                raw = d[actual_off: actual_off + file_len]

                pixels, mode = _decode_sffv2_pixels(fmt, raw, w, h)

                if mode == 'rgba':
                    try:
                        surf = pygame.image.fromstring(pixels, (w, h), 'RGBA')
                        self.sprites[key] = surf
                        loaded += 1
                        continue
                    except Exception:
                        pass

                # Indexed → apply palette
                palette = None
                if 0 <= pal_idx < len(self._palettes):
                    palette = self._palettes[pal_idx]
                if palette is None and self._palettes:
                    palette = next((p for p in self._palettes if p is not None), None)
                if palette is None:
                    palette = _default_palette()

                surf = _render_indexed(pixels, w, h, palette)
                if surf:
                    self.sprites[key] = surf
                    loaded += 1

        print(f"  [SFF v2] {self.filepath.name}: loaded {loaded}/{spr_cnt} sprites")

    def get_sprite(self, group: int, index: int) -> Optional[pygame.Surface]:
        key  = (group, index)
        info = self.sprite_info.get(key)
        if info is None:
            return None
        if info.linked:
            si = info.linked_index
            if 0 <= si < len(self._key_order):
                return self.sprites.get(self._key_order[si])
            return None
        return self.sprites.get(key)

    def get_sprite_offset(self, group: int, index: int) -> Tuple[int, int]:
        info = self.sprite_info.get((group, index))
        return (info.x_offset, info.y_offset) if info else (0, 0)


# ---------------------------------------------------------------------------
# Unified loader
# ---------------------------------------------------------------------------

class SpriteLoader:
    @staticmethod
    def load(filepath: str) -> 'SFFv1Reader | SFFv2Reader':
        with open(filepath, 'rb') as f:
            header = f.read(20)
        if len(header) < 16 or header[:11] != b'ElecbyteSpr':
            raise ValueError(f"Not a valid SFF file: {filepath}")
        ver = header[15]   # verhi is at byte 15 (after sig=12, verhi=12)
        if ver == 2:
            return SFFv2Reader(filepath)
        return SFFv1Reader(filepath)
