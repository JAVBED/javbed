import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from javbed import content_registry, packages, settings


class PackageTests(unittest.TestCase):
    def test_roundtrip_contains_references_without_game_binaries(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(settings, "ROOT", Path(directory) / "data"):
            root = Path(directory)
            game = root / "instance" / "minecraft"
            mods = game / "mods"
            mods.mkdir(parents=True)
            (mods / "tracked.jar").write_bytes(b"mod binary")
            (mods / "local.jar").write_bytes(b"local binary")
            content_registry.upsert({"instance": "survival", "kind": "mod", "file_name": "tracked.jar", "provider": "modrinth", "project": "abc123", "version_id": "v1", "project_name": "Example"})
            instance = {"name": "survival", "version": "1.21.1", "era": "release", "loader": "fabric", "path": str(root / "instance"), "preferences": {"memory_mb": 4096}}
            output = root / "survival.javbed"
            packages.export_package(instance, output)
            manifest, icon = packages.load_package(output)
            self.assertEqual(manifest["content"][0]["project"], "abc123")
            self.assertEqual(manifest["untracked"], [{"kind": "mod", "file_name": "local.jar"}])
            self.assertIsNone(icon)
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(archive.namelist(), ["manifest.json"])
                self.assertNotIn(b"mod binary", archive.read("manifest.json"))

    def test_rejects_unknown_format_and_malicious_identifiers(self):
        base = {"format": packages.FORMAT, "format_version": 1, "name": "good", "minecraft": {"version": "1.21.1", "type": "release", "loader": "fabric"}, "settings": {}, "modpack": None, "content": []}
        with self.assertRaises(ValueError):
            packages.validate_manifest({**base, "format_version": 2})
        with self.assertRaises(ValueError):
            packages.validate_manifest({**base, "name": "../bad"})
        with self.assertRaises(ValueError):
            packages.validate_manifest({**base, "content": [{"kind": "mod", "provider": "modrinth", "project": "../../bad"}]})


if __name__ == "__main__":
    unittest.main()
