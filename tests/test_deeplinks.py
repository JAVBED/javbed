import unittest

from javbed.deeplinks import Link, parse


class DeepLinkTests(unittest.TestCase):
    def test_supported_links(self):
        self.assertEqual(parse("javbed://java/1.21.1"), Link("java", "1.21.1"))
        self.assertEqual(parse("javbed://instance/Survival"), Link("instance", "Survival"))
        self.assertEqual(parse("javbed://server/home"), Link("server", "home"))
        self.assertEqual(parse("javbed://modrinth/sodium"), Link("modrinth", "sodium"))
        self.assertEqual(parse("javbed://settings"), Link("settings"))

    def test_rejects_traversal_and_unexpected_parameters(self):
        for uri in ("javbed://instance/..", "javbed://instance/%2e%2e", "javbed://server/hello%2Fworld", "javbed://settings?cmd=launch", "javbed://java/1.21#extra", "https://example.com", "javbed://unknown/value"):
            with self.assertRaises(ValueError, msg=uri):
                parse(uri)


if __name__ == "__main__":
    unittest.main()
