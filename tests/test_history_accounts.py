import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from javbed import accounts, history, instances, settings


class HistoryAccountTests(unittest.TestCase):
    def test_default_java_path_and_fullscreen_reach_javli(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(settings, "FILE", Path(directory) / "settings.json"):
            data = settings.load()
            data.update({"minecraft_directory": str(Path(directory).resolve()), "fullscreen": True})
            settings.save(data)
            environment = instances.launch_environment()
            self.assertEqual(environment["MCLI_GAME_DIR"], str(Path(directory).resolve()))
            self.assertEqual(environment["MCLI_FULLSCREEN"], "1")

    def test_history_ignores_failed_starts_and_summarizes_sessions(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(settings, "ROOT", Path(directory)):
            started = datetime(2026, 1, 1, tzinfo=timezone.utc)
            self.assertFalse(history.record("Java", started, started + timedelta(seconds=2), instance="survival"))
            self.assertTrue(history.record("Java", started, started + timedelta(minutes=4), instance="survival", version="1.21.1", loader="fabric"))
            self.assertTrue(history.record("Java", started + timedelta(days=1), started + timedelta(days=1, minutes=6), instance="survival", version="1.21.1", loader="fabric"))
            item = history.summary()[0]
            self.assertEqual((item["play_count"], item["total_seconds"], item["version"], item["loader"]), (2, 600, "1.21.1", "fabric"))
            self.assertEqual(len(history.sessions()), 2)

    def test_account_reader_does_not_return_tokens(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(accounts, "JAVLI_ROOT", Path(directory)):
            (Path(directory) / "accounts.json").write_text(json.dumps({"active": "main", "accounts": {"main": {"profile": {"name": "Builder", "id": "0" * 32}, "refresh_token": "secret"}}}), encoding="utf-8")
            self.assertEqual(accounts.active_account(), {"alias": "main", "username": "Builder", "uuid": "0" * 32})
            self.assertNotIn("secret", repr(accounts.accounts()))

    def test_instance_index_uses_structured_metadata(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(instances, "JAVLI_ROOT", Path(directory)):
            (Path(directory) / "instances.json").write_text(json.dumps({"survival": {"name": "survival", "version": "1.21.1", "loader": "fabric"}}), encoding="utf-8")
            self.assertEqual(instances.get_instance("survival")["loader"], "fabric")
            self.assertIsNone(instances.get_instance("missing"))

    def test_instance_preferences_and_mod_count(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            javli = root / "javli"
            game = javli / "instances" / "survival"
            mods = game / "minecraft" / "mods"
            mods.mkdir(parents=True)
            (mods / "example.jar").touch()
            javli.mkdir(exist_ok=True)
            (javli / "instances.json").write_text(json.dumps({"survival": {"name": "survival", "era": "release", "version": "1.21.1", "path": str(game)}}), encoding="utf-8")
            with patch.object(settings, "ROOT", root / "JAVBED"), patch.object(settings, "FILE", root / "JAVBED" / "settings.json"), patch.object(instances, "JAVLI_ROOT", javli):
                instances.save_preferences("survival", {"memory_mb": 8192, "width": 1600, "height": 900, "java_major": 21})
                self.assertEqual(instances.snapshot()[0]["mod_count"], 1)
                self.assertEqual(instances.launch_environment("survival")["MCLI_MEMORY_MB"], "8192")
                self.assertEqual(instances.preferences("survival")["java_major"], 21)
                self.assertFalse(instances.valid_name("../unsafe"))


if __name__ == "__main__":
    unittest.main()
