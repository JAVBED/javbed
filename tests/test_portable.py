import tempfile
import unittest
import json
from pathlib import Path
from unittest.mock import patch

from javbed import settings
from javbed.settings import data_root


class PortableTests(unittest.TestCase):
    def test_marker_selects_local_data_without_migration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = root / "app"
            app.mkdir()
            normal = root / "appdata"
            self.assertEqual(data_root(app, normal), normal / "JAVBED")
            (app / "portable.txt").write_text("", encoding="utf-8")
            self.assertEqual(data_root(app, normal), app / "JAVBED-data")
            self.assertFalse((app / "JAVBED-data").exists())

    def test_existing_settings_do_not_trigger_first_run(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text('{"java_memory_mb":8192}', encoding="utf-8")
            with patch.object(settings, "FILE", path):
                self.assertTrue(settings.load()["onboarding_complete"])

    def test_failed_settings_replace_keeps_previous_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text('{"java_memory_mb":8192}', encoding="utf-8")
            with patch.object(settings, "FILE", path), patch.object(settings.os, "replace", side_effect=OSError("replace failed")):
                with self.assertRaisesRegex(OSError, "replace failed"):
                    settings.save({"java_memory_mb":4096})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["java_memory_mb"], 8192)
            self.assertEqual(list(path.parent.glob(".settings-*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
