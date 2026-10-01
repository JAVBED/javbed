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
from PySide6.QtWidgets import QApplication, QPushButton
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
        def slow_install(_engine, **_kwargs):
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
            self.assertEqual(window.stack.count(), 15)
            window.select_name("Java")
            page = window.java_page
            page.switch_view("play")
            window.resize(1272, 720)
            self.app.processEvents()
            self.assertEqual(window.centralWidget().layout().itemAt(0).widget().width(), 178)
            self.assertEqual(page.top.height(), 79)
            self.assertLessEqual(abs(page.hero.height() - 446), 2)
            self.assertEqual(page.playbar.height(), 58)
            self.assertEqual(page.play_button.width(), 235)
            self.assertEqual(page.news.height(), 137)
            for name in ("Bedrock", "EDU", "LCE", "Dungeons", "Dungeons 2", "Legends", "Story Mode"):
                window.select_name(name)
                self.app.processEvents()
                game = window.pages[window.stack.currentIndex()]
                self.assertEqual(game.findChild(type(page.top), "topbar").height(), 79, name)
                self.assertLessEqual(abs(game.hero.height() - 446), 2, name)
                self.assertEqual(game.playbar.height(), 58, name)
                button = game.play_button if hasattr(game, "play_button") else game.play
                self.assertEqual(button.size().width(), 235, name)
                self.assertLessEqual(abs(button.y() - 501), 2, name)
            window.select_name("Bedrock")
            bedrock = window.pages[window.stack.currentIndex()]
            bedrock.channel_menu.actions()[1].trigger()
            self.assertEqual(bedrock.channel.currentText(), "beta")
            window.select_name("Story Mode")
            window.story_page.season.setCurrentIndex(1)
            self.assertEqual(window.story_page.title(), "Story Mode 2")
            window.select_name("Java")
            page.version.addItem("Instance: survival", ("instance", "survival"))
            with patch.object(page, "run") as launch:
                page.choose_installation(page.version.count() - 1)
                page.play_selected_java()
                launch.assert_called_once_with(["instance", "launch", "survival"])
            page.clear_selected_instance()
            page.version.setEditText("1.21.1")
            with patch.object(page, "run") as launch:
                page.play_selected_java()
                launch.assert_called_once_with(["release", "1.21.1"])
            page.tab_buttons["more"].menu().actions()[0].trigger()
            self.assertTrue(page.resources_panel.isVisible())
            page.channel_menu.actions()[1].trigger()
            self.assertEqual(page.channel.currentText(), "snapshot")
            window.java_page.switch_view("instances")
            self.assertTrue(window.java_page.instances_panel.isVisible())
            instance_buttons = [button.text() for button in window.java_page.instances_panel.findChildren(QPushButton)]
            self.assertFalse(any("IMPORT" in label for label in instance_buttons))
            window.java_page.switch_view("mods")
            self.assertTrue(window.java_page.mods_panel.isVisible())
            window.java_page.switch_view("resources")
            self.assertTrue(window.java_page.resources_panel.isVisible())
            window.java_page.switch_view("shaders")
            self.assertTrue(window.java_page.shaders_panel.isVisible())
            window.java_page.switch_view("modpacks")
            self.assertTrue(window.java_page.modpacks_panel.isVisible())
            window.select_name("Servers")
            server_page = window.pages[window.stack.currentIndex()]
            server_page.switch_view("dashboard")
            self.assertTrue(server_page.server_dashboard.isVisible())
            self.assertEqual(server_page.server_dashboard.tabs.count(), 8)
            world_buttons = [button.text() for button in window.pages[9].findChildren(QPushButton)]
            self.assertFalse(any("IMPORT" in label for label in world_buttons))
            window.open_deep_link("javbed://java/1.21.1")
            self.assertEqual(window.java_page.version.currentText(), "1.21.1")
            window.open_deep_link("javbed://settings")
            self.assertEqual(window.stack.currentIndex(), 14)
            wizard = InstanceWizard(window)
            self.assertEqual(len(wizard.pageIds()), 4)
            window.close()


if __name__ == "__main__":
    unittest.main()
