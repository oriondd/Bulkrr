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

    def test_library_genre_recommendations_require_explicit_queue(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(bulkrr, "SETTINGS", Path(folder) / "settings.json"):
                with patch("keyring.get_password", return_value=None):
                    window = bulkrr.Main()
                    try:
                        window.library_scanned({
                            "movies": [], "series": [], "upgrades": [],
                            "genres": ["mystery"], "errors": [],
                        })
                        window.discovered([
                            {"title": "Mysterious Story", "type": "tv", "year": 2026,
                             "overview": "A mystery adventure", "genres": ["Mystery"]},
                            {"title": "Cooking Hour", "type": "tv", "year": 2026,
                             "overview": "Cooking", "genres": ["Food"]},
                        ])
                        window.rank_from_library()
                        self.assertEqual(len(window.discover_records), 1)
                        self.assertEqual(len(window.discover_source_records), 2)
                        self.assertEqual(window.input.toPlainText(), "")
                    finally:
                        window.close()

    def test_failed_connection_discards_stale_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(bulkrr, "SETTINGS", Path(folder) / "settings.json"):
                with patch("keyring.get_password", return_value=None):
                    window = bulkrr.Main()
                    try:
                        window.connections = {"radarr": {"url": "http://localhost:7878", "key": "secret"}}
                        window.library_genres = ["mystery"]
                        window.connection_error()
                        self.assertEqual(window.connections, {})
                        self.assertEqual(window.library_genres, [])
                    finally:
                        window.close()

    def test_genre_filter_is_reversible_and_does_not_queue_imports(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(bulkrr, "SETTINGS", Path(folder) / "settings.json"):
                with patch("keyring.get_password", return_value=None):
                    window = bulkrr.Main()
                    try:
                        window.discovered([
                            {"title": "Horror Story", "type": "anime", "year": 2026, "genres": ["Horror"]},
                            {"title": "Sports Story", "type": "anime", "year": 2025, "genres": ["Sports"]},
                        ])
                        window.genre_filter.setText("HORROR")
                        window.filter_discovery_genre()
                        self.assertEqual([x["title"] for x in window.discover_records], ["Horror Story"])
                        self.assertEqual(len(window.discover_source_records), 2)
                        window.reset_discovery_filter()
                        self.assertEqual(len(window.discover_records), 2)
                        self.assertEqual(window.input.toPlainText(), "")
                    finally:
                        window.close()

    def test_tmdb_worker_emits_metadata_without_importing(self):
        worker = bulkrr.Worker("trending_tmdb", {}, config={
            "kind": "movie", "access_token": "test-value",
        })
        found, failures = [], []
        worker.finished_data.connect(found.append)
        worker.failed.connect(failures.append)
        sample = [{"title": "Example", "type": "movie", "year": 2026,
                   "genres": ["Mystery"]}]
        with patch.object(bulkrr, "fetch_trending", return_value=sample) as provider:
            worker.run()
        provider.assert_called_once_with("movie", "test-value")
        self.assertEqual(found, [sample])
        self.assertEqual(failures, [])

    def test_tmdb_discovery_requires_explicit_token_and_never_starts_on_cancel(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(bulkrr, "SETTINGS", Path(folder) / "settings.json"):
                with patch("keyring.get_password", return_value=None):
                    window = bulkrr.Main()
                    try:
                        with patch.object(bulkrr.QInputDialog, "getText", return_value=("", False)):
                            with patch.object(window, "run_worker") as worker:
                                window.load_tmdb_trending("movie")
                                worker.assert_not_called()
                        with patch.object(bulkrr.QInputDialog, "getText", return_value=("test-value", True)):
                            with patch.object(window, "run_worker") as worker:
                                window.load_tmdb_trending("tv")
                                worker.assert_called_once_with(
                                    "trending_tmdb",
                                    config={"kind": "tv", "access_token": "test-value"},
                                    done=window.tmdb_trending_loaded,
                                )
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
