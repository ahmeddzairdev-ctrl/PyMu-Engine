"""
Content scanner — validates MUGEN character and stage folders.
Run as a standalone script:  python -m tools.content_scanner
"""

import sys
from pathlib import Path
from typing import List, Dict, Any


def scan_characters(chars_path: Path) -> List[Dict[str, Any]]:
    results = []
    if not chars_path.exists():
        print(f"[WARN] Characters path not found: {chars_path}")
        return results

    for folder in sorted(chars_path.iterdir()):
        if not folder.is_dir():
            continue

        issues = []
        def_files = list(folder.glob("*.def"))
        if not def_files:
            issues.append("missing .def file")

        sff_files = list(folder.glob("*.sff"))
        if not sff_files:
            issues.append("missing .sff sprite file")

        air_files = list(folder.glob("*.air"))
        if not air_files:
            issues.append("missing .air animation file")

        cmd_files = list(folder.glob("*.cmd"))
        if not cmd_files:
            issues.append("missing .cmd command file")

        cns_files = list(folder.glob("*.cns"))
        if not cns_files:
            issues.append("missing .cns state file")

        status = "OK" if not issues else "WARN"
        results.append({
            "name":   folder.name,
            "path":   str(folder),
            "status": status,
            "issues": issues,
        })

    return results


def scan_stages(stages_path: Path) -> List[Dict[str, Any]]:
    results = []
    if not stages_path.exists():
        print(f"[WARN] Stages path not found: {stages_path}")
        return results

    for def_file in sorted(stages_path.glob("*.def")):
        issues = []
        # Check for associated sprite file
        sff = def_file.with_suffix(".sff")
        if not sff.exists():
            issues.append(f"missing {sff.name}")

        status = "OK" if not issues else "WARN"
        results.append({
            "name":   def_file.stem,
            "path":   str(def_file),
            "status": status,
            "issues": issues,
        })

    return results


def main(base_path: str = ".") -> None:
    root = Path(base_path)
    chars_path  = root / "data" / "chars"
    stages_path = root / "data" / "stages"

    print("=" * 56)
    print("PyMugen Content Scanner")
    print("=" * 56)

    print(f"\n[Characters]  ({chars_path})")
    chars = scan_characters(chars_path)
    if not chars:
        print("  (none found)")
    for c in chars:
        marker = "✓" if c["status"] == "OK" else "!"
        print(f"  [{marker}] {c['name']}")
        for issue in c["issues"]:
            print(f"       - {issue}")

    print(f"\n[Stages]  ({stages_path})")
    stages = scan_stages(stages_path)
    if not stages:
        print("  (none found)")
    for s in stages:
        marker = "✓" if s["status"] == "OK" else "!"
        print(f"  [{marker}] {s['name']}")
        for issue in s["issues"]:
            print(f"       - {issue}")

    total = len(chars) + len(stages)
    ok    = sum(1 for x in chars + stages if x["status"] == "OK")
    print(f"\nSummary: {ok}/{total} items passed validation\n")


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else "."
    main(base)
