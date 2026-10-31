import unittest
from bulkrr_updates import parse_release, parse_version, update_available


class UpdateTests(unittest.TestCase):
    def test_versions(self):
        self.assertEqual(parse_version("v2.1.3-beta"), (2, 1, 3))
        self.assertTrue(update_available("2.0.0", "v2.0.1"))
        self.assertFalse(update_available("2.0.0", "v1.9.9"))

    def test_rejects_invalid_versions(self):
        for version in ("v2", "latest", "2.0.0.0"):
            with self.assertRaises(ValueError):
                parse_version(version)

    def test_valid_release(self):
        result = parse_release({"tag_name": "v2.0.1", "html_url": "https://github.com/oriondd/Bulkrr/releases/tag/v2.0.1"})
        self.assertEqual(result["tag"], "v2.0.1")

    def test_rejects_untrusted_release_link(self):
        with self.assertRaises(ValueError):
            parse_release({"tag_name": "v3.0.0", "html_url": "https://github.com.evil.example/oriondd/Bulkrr/releases/tag/v3.0.0"})


if __name__ == "__main__":
    unittest.main()
