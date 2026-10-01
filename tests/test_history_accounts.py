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


if __name__ == "__main__":
    unittest.main()
