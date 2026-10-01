import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from javbed.app import EXTRA_GAMES, find_game
from javbed.storymode import detect_game


class DiscoveryTests(unittest.TestCase):
    def test_located_game_is_found_outside_default_folders(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "Custom Legends.exe"
            executable.touch()
            with patch("javbed.app.load_settings", return_value={"game_legends_path": str(executable)}):
                self.assertEqual(find_game("Legends", EXTRA_GAMES["Legends"][0]), ("exe", str(executable)))

    def test_story_mode_seasons_have_independent_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            second = Path(directory) / "Season Two.exe"
            second.touch()
            settings = {"story_mode_s1_path": "", "story_mode_s2_path": str(second)}
            with patch("javbed.storymode.sys.platform", "linux"):
                self.assertIsNone(detect_game(settings, 0))
                self.assertEqual(detect_game(settings, 1), second)


if __name__ == "__main__":
    unittest.main()
