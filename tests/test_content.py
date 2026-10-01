import sys
import tempfile
import unittest
import json
import zipfile
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from javbed import content, content_registry, settings
from javbed.content_browser import _finish_update, _make_backup
from javbed.modpack_browser import inspect_mrpack, pack_requirements


class ContentTests(unittest.TestCase):
    def test_modrinth_search_filters_minecraft_and_loader(self):
        urls = []

        def fake_get(url, key=""):
            urls.append(url)
            return {"hits": [{"project_id": "abc", "title": "Example", "versions": ["1.21.1"], "categories": ["fabric"]}]}

        with patch.object(content, "_get", side_effect=fake_get):
            result = content.search("modrinth", "mod", "example", "1.21.1", "fabric")
        self.assertEqual(result[0]["id"], "abc")
        facets = parse_qs(urlparse(urls[0]).query)["facets"][0]
        self.assertIn("versions:1.21.1", facets)
        self.assertIn("categories:fabric", facets)

    def test_version_check_rejects_incompatible_rows(self):
        rows = [
            {"id": "wrong", "game_versions": ["1.20.1"], "loaders": ["fabric"]},
            {"id": "right", "game_versions": ["1.21.1"], "loaders": ["fabric"], "files": [{"filename": "example.jar"}]},
        ]
        with patch.object(content, "_get", return_value=rows):
            version = content.newest_compatible("modrinth", "mod", "example", "1.21.1", "fabric")
        self.assertEqual(version["id"], "right")
        with patch.object(content, "_get", return_value=rows):
            self.assertIsNone(content.newest_compatible("modrinth", "mod", "example", "1.21.1", "forge"))

    def test_failed_update_restores_only_copy(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(settings, "ROOT", Path(directory)):
            old = Path(directory) / "mod.jar"
            old.write_bytes(b"working")
            backup = _make_backup(old)
            old.write_bytes(b"broken")
            updated = _finish_update(old, backup, old, False, "survival", "mod", {}, {"file_name": "mod.jar"})
            self.assertFalse(updated)
            self.assertEqual(old.read_bytes(), b"working")
            self.assertFalse(backup.exists())

    def test_content_registry_is_instance_scoped(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(settings, "ROOT", Path(directory)):
            content_registry.upsert({"instance": "one", "kind": "mod", "file_name": "a.jar", "project": "a"})
            content_registry.upsert({"instance": "two", "kind": "mod", "file_name": "a.jar", "project": "b"})
            content_registry.remove("one", "mod", "a.jar")
            self.assertIsNone(content_registry.lookup("one", "mod", "a.jar"))
            self.assertEqual(content_registry.lookup("two", "mod", "a.jar")["project"], "b")

    def test_local_modpack_requirements(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pack.mrpack"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("modrinth.index.json", json.dumps({"formatVersion": 1, "name": "Example Pack", "dependencies": {"minecraft": "1.21.1", "fabric-loader": "0.16.0"}}))
            self.assertEqual(inspect_mrpack(path), {"name": "Example Pack", "minecraft": "1.21.1", "loader": "fabric", "loader_version": "0.16.0"})
            self.assertEqual(pack_requirements({"dependencies": {"minecraft": "1.20.1"}}), ("1.20.1", "vanilla", ""))


if __name__ == "__main__":
    unittest.main()
