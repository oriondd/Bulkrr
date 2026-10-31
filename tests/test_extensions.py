import json
import tempfile
import unittest
from pathlib import Path
from bulkrr_extensions import validate_manifest, discover_manifests


class ExtensionTests(unittest.TestCase):
    def test_safe_manifest(self):
        data = validate_manifest({"schema": 1, "name": "Sample", "titles": ["movie: Example", "movie: Example"]})
        self.assertEqual(data["titles"], ["movie: Example"])

    def test_rejects_executable_fields(self):
        with self.assertRaises(ValueError):
            validate_manifest({"schema": 1, "name": "Bad", "titles": [], "script": "evil.py"})

    def test_directory_scan_skips_bad_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ok.json").write_text(json.dumps({"schema": 1, "name": "OK", "titles": ["tv: Example"]}))
            (root / "bad.json").write_text("{bad")
            self.assertEqual(len(discover_manifests(root)), 1)


if __name__ == "__main__":
    unittest.main()
