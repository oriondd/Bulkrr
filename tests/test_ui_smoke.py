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

    def test_library_rows_separate_missing_and_upgrade_actions(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(bulkrr, "SETTINGS", Path(folder) / "settings.json"):
                with patch("keyring.get_password", return_value=None):
                    window = bulkrr.Main()
                    try:
                        data = {
                            "movies": [{"id": 1, "title": "Missing movie", "year": 2020,
                                        "monitored": True, "status": "missing"}],
                            "series": [],
                            "upgrades": [{"id": 2, "title": "Upgrade movie", "year": 2021,
                                          "monitored": True, "status": "upgrade"}],
                            "errors": [],
                        }
                        window.library_scanned(data)
                        self.assertEqual(window.library_layout_table.rowCount(), 2)
                        self.assertEqual(window.library_layout_table.item(0, 3).text(), "Missing")
                        self.assertEqual(window.library_layout_table.item(1, 3).text(), "Upgrade")
                        window.library_layout_table.selectRow(1)
                        with patch.object(bulkrr.QMessageBox, "information") as notice:
                            window.search_missing()
                            notice.assert_called_once()
                        window.library_layout_table.selectRow(0)
                        with patch.object(bulkrr.QMessageBox, "information") as notice:
                            window.search_upgrades()
                            notice.assert_called_once()
                    finally:
                        window.close()

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
