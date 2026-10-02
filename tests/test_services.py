import unittest
from unittest.mock import patch

from javbed import services


class ServiceTests(unittest.TestCase):
    def test_update_check_requires_a_newer_version(self):
        for current, latest, expected in (
            ("1.2.3", "v1.2.4", True),
            ("1.2.3", "v1.2.3", False),
            ("1.2.3", "v1.2.2", False),
            ("1.2.3", "v1.2", False),
        ):
            with self.subTest(current=current, latest=latest), patch.object(services, "latest_release", return_value={"tag_name": latest, "html_url": "https://example.invalid"}):
                self.assertEqual(services.javbed_update(current)[1], expected)


if __name__ == "__main__":
    unittest.main()
