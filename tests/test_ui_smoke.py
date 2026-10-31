"""Headless GUI construction smoke tests for the unified 2.0 screens."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
import bulkrr


class MainWindowSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_new_phase_tabs_and_actions_construct_without_network(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(bulkrr, "SETTINGS", Path(folder) / "settings.json"):
                with patch("keyring.get_password", return_value=None):
                    window = bulkrr.Main()
                    try:
                        tabs = window.tabs
                        names = [tabs.tabText(i) for i in range(tabs.count())]
                        self.assertTrue(any("Library" in name for name in names))
                        self.assertTrue(any("Discover" in name for name in names))
                        self.assertIsNotNone(window.library_upgrade_btn)
                        self.assertIsNotNone(window.trending_anime_button)
                        self.assertIsNotNone(window.recommend_interests)
                        self.assertEqual(window.library_layout_table.columnCount(), 6)
                    finally:
                        window.close()


if __name__ == "__main__":
    unittest.main()
