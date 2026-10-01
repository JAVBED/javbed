import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from javbed.app import ExtraPage, MainWindow, SettingsPage, UpdatesPage
from javbed.instance_library import InstanceWizard
from javbed import settings


class UiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def wait_for(self, predicate, timeout=3):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)
        self.app.processEvents()
        self.assertTrue(predicate())

    def test_missing_game_reports_not_detected_and_offers_locate(self):
        with patch("javbed.app.detect_extra_game", return_value=(None, False)):
            page = ExtraPage("Legends")
            self.wait_for(lambda: page.scan_job is None)
            self.assertIn("Not detected", page.state.text())
            self.assertTrue(page.locate_button.isEnabled())

    def test_engine_updates_leave_event_loop_responsive(self):
        page = UpdatesPage()
        ticked = []
        def slow_install(_engine):
            time.sleep(0.06)
            return "v1"
        with patch("javbed.engines.Engine.install_latest", slow_install):
            page.update_engines()
            QTimer.singleShot(10, lambda: ticked.append(True))
            self.wait_for(lambda: bool(ticked))
            self.assertIsNotNone(page.update_job)
            self.wait_for(lambda: page.update_job is None)
            self.assertIn("Update pass complete", page.output.toPlainText())

    def test_settings_save_preserves_game_path_added_after_page_opened(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(settings, "ROOT", root), patch.object(settings, "FILE", root / "settings.json"):
                page = SettingsPage()
                data = settings.load()
                data["game_legends_path"] = str(root / "Legends.exe")
                settings.save(data)
                page.save()
                self.assertEqual(settings.load()["game_legends_path"], data["game_legends_path"])

    def test_main_window_and_instance_wizard_smoke(self):
        with patch("javbed.app.home_snapshot", return_value=([], [], None, None, "", None, "", [])):
            window = MainWindow()
            window.show()
            self.app.processEvents()
            self.assertEqual(window.stack.count(), 13)
            window.select_name("Java")
            window.java_page.switch_view("instances")
            self.assertTrue(window.java_page.instances_panel.isVisible())
            window.java_page.switch_view("mods")
            self.assertTrue(window.java_page.mods_panel.isVisible())
            window.java_page.switch_view("resources")
            self.assertTrue(window.java_page.resources_panel.isVisible())
            window.java_page.switch_view("shaders")
            self.assertTrue(window.java_page.shaders_panel.isVisible())
            window.java_page.switch_view("modpacks")
            self.assertTrue(window.java_page.modpacks_panel.isVisible())
            wizard = InstanceWizard(window)
            self.assertEqual(len(wizard.pageIds()), 4)
            window.close()


if __name__ == "__main__":
    unittest.main()
