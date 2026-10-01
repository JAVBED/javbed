import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.installer_payload import choose_asset, extract_engine, stage_payload


DIGEST = "sha256:" + "a" * 64


class InstallerPayloadTests(unittest.TestCase):
    def test_selects_windows_x64_archive_or_standalone_executable(self):
        release = {"assets": [
            {"name": "javli-windows-x86.zip", "digest": DIGEST},
            {"name": "javli-windows-x64.zip", "digest": DIGEST},
        ]}
        self.assertEqual(choose_asset("javli", release)["name"], "javli-windows-x64.zip")
        self.assertEqual(choose_asset("legli", {"assets": [{"name": "legli.exe", "digest": DIGEST}]})["name"], "legli.exe")
        with self.assertRaises(RuntimeError):
            choose_asset("javli", {"assets": [{"name": "javli-windows-x64.zip"}]})

    def test_extracts_executable_with_neighboring_runtime_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "javli.zip"
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr("bundle/javli.exe", b"binary")
                output.writestr("bundle/_internal/runtime.dll", b"dependency")
            extract_engine(archive, "javli", root / "engine")
            self.assertEqual((root / "engine/javli.exe").read_bytes(), b"binary")
            self.assertEqual((root / "engine/_internal/runtime.dll").read_bytes(), b"dependency")

    def test_rejects_archive_path_escape_and_missing_store_helper(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "javli.zip"
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr("../outside.txt", b"bad")
            with self.assertRaises(RuntimeError):
                extract_engine(archive, "javli", root / "engine")
            app = root / "JAVBED"
            app.mkdir()
            (app / "JAVBED.exe").write_bytes(b"binary")
            with self.assertRaisesRegex(RuntimeError, "Store helper"):
                stage_payload(app, root / "stage")


if __name__ == "__main__":
    unittest.main()
