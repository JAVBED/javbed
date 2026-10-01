from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from javbed import safemode, settings
from javbed.crashdoctor import diagnose


class CrashSafeTests(unittest.TestCase):
    def test_safe_mode_restores_exact_original_mods(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(settings, "ROOT", Path(temporary) / "data"):
            root = Path(temporary)
            mods = root / "instance" / "minecraft" / "mods"
            mods.mkdir(parents=True)
            (mods / "a.jar").write_bytes(b"mod")
            (mods / "already.disabled").write_bytes(b"disabled")
            with patch.object(safemode, "get_instance", return_value={"path": str(root / "instance")}):
                self.assertEqual(safemode.prepare("test"), 1)
                self.assertFalse((mods / "a.jar").exists())
                self.assertEqual(safemode.pending(), [("test", 0)])
                safemode.set_pid("test", 123)
                self.assertEqual(safemode.pending(), [("test", 123)])
                self.assertEqual(safemode.restore("test"), 1)
                self.assertEqual((mods / "a.jar").read_bytes(), b"mod")
                self.assertTrue((mods / "already.disabled").exists())

    def test_crash_doctor_uses_fresh_evidence_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            game = Path(temporary)
            logs = game / "logs"
            logs.mkdir()
            log = logs / "latest.log"
            log.write_text("java.lang.OutOfMemoryError: Java heap space", encoding="utf-8")
            found = diagnose(game, time.time() - 1, 1)
            self.assertIn("memory", found.cause.lower())
            self.assertIsNone(diagnose(game, time.time() + 100, 0))


if __name__ == "__main__":
    unittest.main()
