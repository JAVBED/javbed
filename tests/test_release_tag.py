import unittest

from tools.release_tag import choose_tag


class ReleaseTagTests(unittest.TestCase):
    def test_blank_input_advances_latest_patch_from_legacy_tags(self):
        tags = {"v0.3.5", "v1", "v1.0", "v1.0.0", "v1.1", "build-12"}
        self.assertEqual(choose_tag("", tags), "v1.1.1")
        self.assertEqual(choose_tag("   ", tags), "v1.1.1")
        self.assertEqual(choose_tag("", set()), "v0.1.0")

    def test_normalizes_manual_versions_and_rejects_duplicates(self):
        tags = {"v1.1", "v1.2.3"}
        self.assertEqual(choose_tag(" 1.2 ", tags), "v1.2.0")
        self.assertEqual(choose_tag("v2", tags), "v2.0.0")
        self.assertEqual(choose_tag("v2.0.1", tags), "v2.0.1")
        with self.assertRaisesRegex(ValueError, "already exists"):
            choose_tag("v1.1", tags)
        with self.assertRaisesRegex(ValueError, "already exists"):
            choose_tag("1.2.3", tags)
        with self.assertRaisesRegex(ValueError, "legacy tag"):
            choose_tag("v1.1.0", tags)
        with self.assertRaisesRegex(ValueError, "Invalid version"):
            choose_tag("latest", tags)


if __name__ == "__main__":
    unittest.main()
