from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from javbed import servers


class ServerTests(unittest.TestCase):
    def test_properties_validation(self):
        self.assertEqual(servers.parse_properties("# note\nmotd=Hello=World\nmax-players=20\n"), {"motd": "Hello=World", "max-players": "20"})
        self.assertEqual(servers.validate_property("online-mode", "true"), "true")
        for key, value in (("server-port", "70000"), ("max-players", "many"), ("online-mode", "sometimes"), ("motd", "bad\nvalue")):
            with self.assertRaises(ValueError):
                servers.validate_property(key, value)

    def test_console_tail_resumes_at_previous_offset(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / "servers" / "survival" / "logs"
            folder.mkdir(parents=True)
            log = folder / "console-20260101.log"
            log.write_bytes(b"first\n")
            with patch.object(servers, "servli_home", return_value=root):
                cursor, text = servers.read_console("survival", ("", 0))
                self.assertEqual(text, "first\n")
                with log.open("ab") as stream:
                    stream.write(b"second\n")
                cursor, text = servers.read_console("survival", cursor)
                self.assertEqual(text, "second\n")

    def test_snapshot_uses_structured_servli_output(self):
        completed = type("Completed", (), {"returncode": 0, "stdout": json.dumps([{"name": "survival", "running": False}]), "stderr": ""})()
        with patch.object(type(servers.ENGINES["Servers"]), "command", return_value=(["servli", "list", "--json"], None)), patch.object(servers.subprocess, "run", return_value=completed):
            self.assertEqual(servers.server_snapshot()[0]["name"], "survival")


if __name__ == "__main__":
    unittest.main()
