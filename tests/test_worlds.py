from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from javbed.worlds import World, backup_world, duplicate_world, import_world, restore_world, trash_world
from javbed import settings


class WorldTests(unittest.TestCase):
    def test_backup_restore_and_recoverable_delete(self):
        with tempfile.TemporaryDirectory() as temporary:
            original = settings.ROOT
            settings.ROOT = Path(temporary) / "data"
            try:
                root = Path(temporary) / "saves"
                folder = root / "Survival"
                folder.mkdir(parents=True)
                (folder / "level.dat").write_bytes(b"before")
                world = World("Survival", "Java", "", folder, root, "1.21", 0, 6, None)
                backup = backup_world(world)
                (folder / "level.dat").write_bytes(b"after")
                restore_world(world, backup)
                self.assertEqual((folder / "level.dat").read_bytes(), b"before")
                self.assertGreaterEqual(len(list((settings.ROOT / "backups" / "worlds").rglob("*.zip"))), 2)
                copy = duplicate_world(world)
                self.assertTrue((copy / "level.dat").is_file())
                trash = trash_world(world)
                self.assertFalse(folder.exists())
                self.assertEqual((trash / "level.dat").read_bytes(), b"before")
            finally:
                settings.ROOT = original

    def test_world_import_rejects_archive_traversal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "bad.zip"
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr("../escape.txt", "bad")
                output.writestr("level.dat", "world")
            with self.assertRaises(ValueError):
                import_world(archive, root / "saves")
            self.assertFalse((root / "escape.txt").exists())


if __name__ == "__main__":
    unittest.main()
