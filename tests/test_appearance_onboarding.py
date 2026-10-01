import unittest
from unittest.mock import patch

from javbed.theme import stylesheet
from javbed.notifications import NotificationCenter
from javbed.onboarding import first_run_snapshot


class AppearanceOnboardingTests(unittest.TestCase):
    def test_accent_and_compact_theme(self):
        compact = stylesheet({"accent_color": "#336699", "compact_navigation": True})
        self.assertIn("background:#336699", compact)
        self.assertIn("padding:8px 11px", compact)
        self.assertIn("background:#3c8527", stylesheet({"accent_color": "invalid"}))

    def test_notifications_deduplicate(self):
        center = NotificationCenter()
        messages = []
        center.posted.connect(messages.append)
        self.assertTrue(center.post("download:one", "Complete"))
        self.assertFalse(center.post("download:one", "Complete again"))
        self.assertEqual(messages, ["Complete"])

    def test_first_run_snapshot_collects_games_and_instances(self):
        home = lambda: (["Java"], [("Java", "javli", "v1")], 1, 0, "", None, "", [])
        with patch("javbed.onboarding.list_instances", return_value=[{"name": "survival"}]):
            result = first_run_snapshot(home)
        self.assertEqual(result[0], ["Java"])
        self.assertEqual(result[4][0]["name"], "survival")
        self.assertEqual(len(result), 6)


if __name__ == "__main__":
    unittest.main()
