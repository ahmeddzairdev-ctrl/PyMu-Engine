"""
MUGEN content format converter.
Converts older WinMUGEN 1.0 content (SFF v1, CNS quirks) to be
compatible with the engine's expectations.

Run as:  python -m tools.converter <source_dir> [--out <dest_dir>]
"""

import sys
import shutil
import struct
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# SFF v1 → normalised (no-op stub — file is just copied for now)
# ---------------------------------------------------------------------------

def convert_sff(src: Path, dst: Path) -> bool:
    """
    Attempt to upgrade or validate an SFF file.
    Currently copies the file as-is after a header sanity check.
    """
    try:
        with open(src, "rb") as f:
            sig = f.read(11)
        if sig != b"ElecbyteSpr":
            print(f"  [SKIP] {src.name}: not a valid SFF file")
            return False

        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return True
    except Exception as e:
        print(f"  [ERROR] {src.name}: {e}")
        return False


# ---------------------------------------------------------------------------
# CNS / CMD line-ending normalisation
# ---------------------------------------------------------------------------

def normalise_text_file(src: Path, dst: Path) -> bool:
    """
    Normalise a MUGEN text file:
    - Windows CRLF → LF
    - Strip null bytes (common in old encoders)
    - Re-encode as latin-1
    """
    try:
        raw = src.read_bytes()
        text = raw.replace(b"\x00", b"").decode("latin-1", errors="replace")
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(text, encoding="latin-1")
        return True
    except Exception as e:
        print(f"  [ERROR] {src.name}: {e}")
        return False


# ---------------------------------------------------------------------------
# Character folder converter
# ---------------------------------------------------------------------------

_TEXT_EXTS = {".def", ".cmd", ".cns", ".air", ".st", ".fnt"}
_BIN_EXTS  = {".sff", ".snd", ".pcx"}


def convert_character(src_dir: Path, dst_dir: Path) -> None:
    """Convert all files in a character folder."""
    dst_dir.mkdir(parents=True, exist_ok=True)
    converted = 0
    skipped   = 0

    for src_file in sorted(src_dir.rglob("*")):
        if src_file.is_dir():
            continue

        rel      = src_file.relative_to(src_dir)
        dst_file = dst_dir / rel
        ext      = src_file.suffix.lower()

        if ext in _TEXT_EXTS:
            ok = normalise_text_file(src_file, dst_file)
        elif ext in _BIN_EXTS:
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)
            ok = True
        else:
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)
            ok = True

        if ok:
            converted += 1
        else:
            skipped += 1

    print(f"  Converted {converted} files, skipped {skipped}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(
        description="Convert older MUGEN content for PyMugen"
    )
    parser.add_argument("source", help="Source directory (character or stage folder)")
    parser.add_argument("--out", default=None,
                        help="Output directory (default: <source>_converted)")
    args = parser.parse_args()

    src = Path(args.source)
    if not src.exists():
        print(f"Source not found: {src}")
        sys.exit(1)

    dst = Path(args.out) if args.out else src.parent / (src.name + "_converted")

    print(f"Converting: {src}")
    print(f"       To : {dst}")
    convert_character(src, dst)
    print("Done.")


if __name__ == "__main__":
    main()
