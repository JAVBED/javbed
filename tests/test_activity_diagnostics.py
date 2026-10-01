from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from javbed.activity import ActivityManager
from javbed import diagnostics


class ActivityDiagnosticsTests(unittest.TestCase):
    def test_activity_never_invents_a_total(self):
        manager = ActivityManager()
        key = manager.begin("Story ISO", "configured source", "Downloading")
        manager.progress(key, received=1024, total=0)
        self.assertIsNone(manager.items[key].total)
        manager.progress(key, received=2048, total=4096)
        self.assertEqual(manager.items[key].total, 4096)
        manager.finish(key, True)
        self.assertEqual(manager.items[key].state, "completed")

    def test_doctor_reports_missing_engine_and_bad_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.object(diagnostics, "ROOT", root), patch.object(diagnostics, "JAVLI_ROOT", root / "mcli"), patch.object(diagnostics, "_reachable", return_value=True), patch.object(diagnostics, "active_account", return_value=None), patch.object(diagnostics, "artwork_dir", return_value=root), patch.object(diagnostics, "load", return_value={"minecraft_directory": str(root / "missing")}), patch.object(type(diagnostics.ENGINES["Java"]), "locate", return_value=None), patch.object(diagnostics.sys, "platform", "linux"):
                checks = diagnostics.scan()
            self.assertTrue(any(check.name == "Java engine" and check.repair_engine == "Java" for check in checks))
            self.assertTrue(any(check.name == "Minecraft folder" and check.state == "warning" for check in checks))
            self.assertTrue(any(check.name == "JAVBED data" and check.state == "healthy" for check in checks))


if __name__ == "__main__":
    unittest.main()
