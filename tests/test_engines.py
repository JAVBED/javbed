import io
import hashlib
import json
import os
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from javbed import engines


class EngineTests(unittest.TestCase):
    def test_explicit_path_then_path_then_managed_engine(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = "javli.exe" if os.name == "nt" else "javli"
            managed = root / "engines" / "javli" / executable
            managed.parent.mkdir(parents=True)
            managed.touch()
            unrelated = root / "path" / executable
            unrelated.parent.mkdir()
            unrelated.touch()
            managed.chmod(0o755)
            unrelated.chmod(0o755)
            engine = engines.Engine("Java", "javli", "javli")
            with patch.object(engines, "ENGINE_ROOT", root / "engines"), patch.dict(os.environ, {"PATH": str(unrelated.parent), "JAVBED_JAVA": ""}):
                self.assertEqual(engine.locate(), unrelated)
                os.environ["JAVBED_JAVA"] = str(managed)
                self.assertEqual(engine.locate(), managed)
                os.environ["JAVBED_JAVA"] = ""
                os.environ["PATH"] = ""
                self.assertEqual(engine.locate(), managed)

    def test_rejects_archive_traversal_and_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bad_tar = root / "bad.tar.gz"
            with tarfile.open(bad_tar, "w:gz") as archive:
                data = b"bad"
                member = tarfile.TarInfo("../outside.exe")
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
            with self.assertRaises(ValueError):
                engines._extract_archive(bad_tar, root / "out")
            self.assertFalse((root / "outside.exe").exists())

            link_tar = root / "link.tar.gz"
            with tarfile.open(link_tar, "w:gz") as archive:
                member = tarfile.TarInfo("release/current")
                member.type = tarfile.SYMTYPE
                member.linkname = "../outside.exe"
                archive.addfile(member)
            with self.assertRaises(ValueError):
                engines._extract_archive(link_tar, root / "out")

            bad_zip = root / "bad.zip"
            with zipfile.ZipFile(bad_zip, "w") as archive:
                archive.writestr("../outside.exe", b"bad")
            with self.assertRaises(ValueError):
                engines._extract_archive(bad_zip, root / "out")

    def test_extracts_valid_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "engine.zip"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("release/javli.exe", b"engine")
            output = root / "out"
            engines._extract_archive(package, output)
            self.assertEqual((output / "release" / "javli.exe").read_bytes(), b"engine")

    def test_install_verifies_checksum_before_replacing_engine(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            engine = engines.Engine("Java", "javli", "javli")
            managed = root / "javli" / "javli.exe"
            managed.parent.mkdir()
            managed.write_bytes(b"old engine")
            archive_data = io.BytesIO()
            with zipfile.ZipFile(archive_data, "w") as archive:
                archive.writestr("release/javli.exe", b"new engine")
            payload = archive_data.getvalue()
            asset = {"name": "javli-windows-x64.zip", "browser_download_url": "https://example.invalid/engine.zip", "digest": "sha256:" + hashlib.sha256(payload).hexdigest()}
            release = json.dumps({"tag_name": "v1.2.3", "assets": [asset]}).encode()
            def open_response(request, timeout):
                return io.BytesIO(release if isinstance(request, engines.urllib.request.Request) else payload)
            with patch.object(engines, "ENGINE_ROOT", root), patch.object(engines.platform, "system", return_value="Windows"), patch.object(engines.platform, "machine", return_value="AMD64"), patch.object(engines.urllib.request, "urlopen", side_effect=open_response):
                self.assertEqual(engine.install_latest(), "v1.2.3")
                self.assertEqual(managed.read_bytes(), b"new engine")
                managed.write_bytes(b"old engine")
                asset["digest"] = "sha256:" + "0" * 64
                release = json.dumps({"tag_name": "v1.2.4", "assets": [asset]}).encode()
                with self.assertRaisesRegex(RuntimeError, "Checksum mismatch"):
                    engine.install_latest()
                self.assertEqual(managed.read_bytes(), b"old engine")


if __name__ == "__main__":
    unittest.main()
