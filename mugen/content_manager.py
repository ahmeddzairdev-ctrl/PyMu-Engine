"""
Content manager — scans the data/ directory for available MUGEN characters
and stages, and provides a registry for the engine to query.
"""

from pathlib import Path
from typing import List, Dict, Optional, Any
from config import CONFIG


class ContentManager:
    """
    Discovers and caches all available MUGEN content (characters, stages).

    Characters are found by scanning CONFIG.paths.chars_path for sub-folders
    that contain a .def file.

    Stages are found by scanning CONFIG.paths.stages_path for .def files.
    """

    def __init__(self):
        self._characters: List[Dict[str, Any]] = []
        self._stages: List[Dict[str, Any]] = []
        self._scan()

    # ------------------------------------------------------------------
    # Scanning
    # ------------------------------------------------------------------

    def _scan(self) -> None:
        self._scan_characters()
        self._scan_stages()

    def _scan_characters(self) -> None:
        chars_path = Path(CONFIG.paths.chars_path)
        if not chars_path.exists():
            return

        for item in sorted(chars_path.iterdir()):
            if not item.is_dir():
                continue
            def_files = list(item.glob("*.def"))
            if not def_files:
                continue

            def_file = def_files[0]
            name = self._read_name(def_file) or item.name

            self._characters.append(
                {
                    "name": name,
                    "path": str(item),
                    "def": str(def_file),
                }
            )

    def _scan_stages(self) -> None:
        stages_path = Path(CONFIG.paths.stages_path)
        if not stages_path.exists():
            return

        for def_file in sorted(stages_path.glob("*.def")):
            name = self._read_name(def_file) or def_file.stem
            self._stages.append(
                {
                    "name": name,
                    "path": str(def_file.parent),
                    "def": str(def_file),
                }
            )

    @staticmethod
    def _read_name(def_file: Path) -> Optional[str]:
        """Quick scan of a .def file to extract the [Info] name field."""
        try:
            with open(def_file, "r", encoding="latin-1") as f:
                in_info = False
                for line in f:
                    line = line.strip()
                    if line.lower().startswith("[info]"):
                        in_info = True
                        continue
                    if in_info:
                        if line.startswith("["):
                            break
                        if line.lower().startswith("name"):
                            _, _, val = line.partition("=")
                            return val.strip().strip('"')
        except OSError:
            pass
        return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_character_list(self) -> List[Dict[str, Any]]:
        """Return a list of character descriptor dicts."""
        return list(self._characters)

    def get_stage_list(self) -> List[Dict[str, Any]]:
        """Return a list of stage descriptor dicts."""
        return list(self._stages)

    def get_character(self, name: str) -> Optional[Dict[str, Any]]:
        """Look up a character by name (case-insensitive)."""
        name_lower = name.lower()
        for c in self._characters:
            if c["name"].lower() == name_lower:
                return c
        return None

    def get_stage(self, name: str) -> Optional[Dict[str, Any]]:
        """Look up a stage by name (case-insensitive)."""
        name_lower = name.lower()
        for s in self._stages:
            if s["name"].lower() == name_lower:
                return s
        return None

    def load_character(self, path: str):
        """
        Fully load and return a CharacterLoader for the given path.
        Returns None if loading fails.
        """
        try:
            from mugen.character_loader import CharacterLoader
            return CharacterLoader(path)
        except Exception as e:
            print(f"ContentManager: failed to load character '{path}': {e}")
            return None

    def refresh(self) -> None:
        """Re-scan content directories."""
        self._characters.clear()
        self._stages.clear()
        self._scan()
