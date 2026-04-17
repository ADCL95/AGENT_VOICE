"""Smoke tests: package layout (no API calls)."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


class TestShowroomLayout(unittest.TestCase):
    def test_repo_paths_helpers(self) -> None:
        from showroom.helpers.paths import RepositoryPaths

        root = RepositoryPaths.root()
        self.assertTrue((root / "front-end").is_dir())
        self.assertTrue((root / "data").is_dir())

    def test_settings_loads_with_secret(self) -> None:
        if not os.environ.get("OPENAI_API_KEY") and not (_ROOT / "local.settings.json").is_file():
            self.skipTest("OPENAI_API_KEY or local.settings.json required")
        from showroom.core import settings as s

        self.assertTrue(bool(s.OPENAI_API_KEY))
        self.assertTrue(bool(s.MODEL_MAIN))


if __name__ == "__main__":
    unittest.main()
