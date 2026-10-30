"""Offscreen Qt smoke tests for the Phase 2 interface."""

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from bulkrr import Main


class Phase2GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = Main()

    def tearDown(self):
        self.window.close()

    def test_import_txt_populates_real_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "titles.txt"
            path.write_text("movie: Alien\ntv: Lost\n", encoding="utf-8")
            self.window.import_files([str(path)])
            self.assertEqual(self.window.input.toPlainText().splitlines(), ["movie: Alien", "tv: Lost"])

    def test_review_actions_follow_selected_row(self):
        self.window.items = [
            {
                "input": "movie: Alien",
                "status": "review",
                "selected": 0,
                "matches": [{"label": "Alien", "app": "radarr", "type": "movie", "score": 1.0, "data": {"title": "Alien", "year": 1979}, "id": 1}],
                "message": "Review",
                "duplicate": None,
            }
        ]
        self.window.refresh()
        self.assertFalse(self.window.review_btn.isEnabled())
        self.window.table.selectRow(0)
        self.assertTrue(self.window.review_btn.isEnabled())
        self.assertFalse(self.window.duplicate_btn.isEnabled())
        self.assertFalse(self.window.add_btn.isEnabled())

    def test_review_summary_starts_empty(self):
        self.assertIn("No titles analyzed", self.window.review_summary_label.text())

    def test_refresh_counts_ready_titles(self):
        self.window.items = [{"input": "movie: Alien", "status": "ready", "selected": -1, "matches": [], "message": "Ready"}]
        self.window.refresh()
        self.assertIn("1 ready", self.window.review_summary_label.text())


if __name__ == "__main__":
    unittest.main()
