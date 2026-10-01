import io
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from javbed.storymode import DownloadCancelled, download_iso
from javbed.app import DownloadSignals


class Response(io.BytesIO):
    def __init__(self, data, status=200):
        super().__init__(data)
        self.status = status
        self.headers = {"Content-Length": str(len(data))}


class StoryModeTests(unittest.TestCase):
    def test_large_progress_value_crosses_qt_signal(self):
        reports = []
        signals = DownloadSignals()
        signals.progress.connect(lambda received, total: reports.append((received, total)))
        signals.progress.emit(1_500_000_000, 3_000_000_000)
        self.assertEqual(reports, [(1_500_000_000, 3_000_000_000)])

    def test_download_resumes_partial_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "story.iso"
            target.with_name(target.name + ".part").write_bytes(b"abc")
            requests = []
            def open_response(request, timeout):
                requests.append(request)
                return Response(b"def", status=206)
            reports = []
            with patch("javbed.storymode.urlopen", side_effect=open_response):
                download_iso("https://example.invalid/story.iso", target, lambda received, total: reports.append((received, total)))
            self.assertEqual(requests[0].get_header("Range"), "bytes=3-")
            self.assertEqual(target.read_bytes(), b"abcdef")
            self.assertEqual(reports[-1], (6, 6))

    def test_pause_keeps_partial_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "story.iso"
            cancelled = threading.Event()
            cancelled.set()
            with patch("javbed.storymode.urlopen", return_value=Response(b"abc")):
                with self.assertRaises(DownloadCancelled):
                    download_iso("https://example.invalid/story.iso", target, lambda *_: None, cancelled)
            self.assertTrue(target.with_name(target.name + ".part").exists())
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
