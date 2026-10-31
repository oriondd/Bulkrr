import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bulkrr_settings import write_settings


class SettingsPersistenceTests(unittest.TestCase):
    def test_atomic_write_and_no_temp_files_left(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "config" / "settings.json"
            write_settings(target, {"radarr_url": "http://localhost:7878",
                                    "extra_profiles": [{"id": "secondary", "kind": "radarr"}]})
            self.assertEqual(json.loads(target.read_text())["extra_profiles"][0]["id"], "secondary")
            self.assertEqual(list(target.parent.glob(".bulkrr-settings-*")), [])

    def test_reject_credentials_nested_and_nonfinite(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "settings.json"
            for data in ({"api_key": "sensitive"},
                         {"extra_profiles": [{"password": "sensitive"}]},
                         {"value": float("nan")},
                         {"value": float("inf")}):
                with self.subTest(data=data), self.assertRaises(ValueError):
                    write_settings(target, data)
            self.assertFalse(target.exists())

    def test_existing_settings_survive_replace_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "settings.json"
            write_settings(target, {"search": False})
            with patch("bulkrr_settings.os.replace", side_effect=OSError("disk error")):
                with self.assertRaises(OSError):
                    write_settings(target, {"search": True})
            self.assertEqual(json.loads(target.read_text()), {"search": False})
            self.assertEqual(list(Path(folder).glob(".bulkrr-settings-*")), [])


if __name__ == "__main__":
    unittest.main()
