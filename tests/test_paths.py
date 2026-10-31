import unittest
from pathlib import Path
from bulkrr_paths import config_dir


class ConfigPathTests(unittest.TestCase):
    def test_windows(self):
        self.assertEqual(config_dir("C:/Users/test", {"APPDATA": "C:/Users/test/AppData/Roaming"}, "win32"), Path("C:/Users/test/AppData/Roaming/Bulkrr"))

    def test_macos(self):
        self.assertEqual(config_dir("/Users/test", {}, "darwin"), Path("/Users/test/Library/Application Support/Bulkrr"))

    def test_linux_xdg(self):
        self.assertEqual(config_dir("/home/test", {"XDG_CONFIG_HOME": "/tmp/config"}, "linux"), Path("/tmp/config/Bulkrr"))

    def test_linux_relative_xdg_ignored(self):
        self.assertEqual(config_dir("/home/test", {"XDG_CONFIG_HOME": "relative"}, "linux"), Path("/home/test/.config/Bulkrr"))


if __name__ == "__main__":
    unittest.main()
