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

    def test_collection_name_search_requires_token_and_only_returns_ids(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(bulkrr, "SETTINGS", Path(folder) / "settings.json"):
                with patch("keyring.get_password", return_value=None):
                    window = bulkrr.Main()
                    try:
                        with patch.object(bulkrr.QInputDialog, "getText",
                                          side_effect=[("Star Wars", True), ("test-token", True)]):
                            with patch.object(window, "run_worker") as worker:
                                window.search_tmdb_collections()
                                worker.assert_called_once_with(
                                    "tmdb_collection_search",
                                    config={"term": "Star Wars", "access_token": "test-token"},
                                    done=window.tmdb_collections_found,
                                )
                        with patch.object(bulkrr.QInputDialog, "getItem",
                                          return_value=("Example Collection (TMDB ID: 42)", True)):
                            with patch.object(bulkrr.QMessageBox, "information") as notice:
                                window.tmdb_collections_found([{"id": 42, "name": "Example Collection"}])
                                self.assertIn("42", notice.call_args.args[2])
                        self.assertEqual(window.input.toPlainText(), "")
                    finally:
                        window.close()

    def test_verified_collection_requires_id_and_token_and_stays_read_only(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(bulkrr, "SETTINGS", Path(folder) / "settings.json"):
                with patch("keyring.get_password", return_value=None):
                    window = bulkrr.Main()
                    try:
                        with patch.object(bulkrr.QInputDialog, "getInt", return_value=(42, True)):
                            with patch.object(bulkrr.QInputDialog, "getText", return_value=("test-token", True)):
                                with patch.object(window, "run_worker") as worker:
                                    window.load_tmdb_collection()
                                    worker.assert_called_once_with(
                                        "tmdb_collection",
                                        config={"collection_id": 42, "access_token": "test-token"},
                                        done=window.tmdb_collection_loaded,
                                    )
                        window.tmdb_collection_loaded([
                            {"title": "Collection Film", "type": "movie", "year": 2026},
                        ])
                        self.assertEqual(window.input.toPlainText(), "")
                        self.assertEqual(len(window.discover_records), 1)
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


    def test_sonarr_episode_preview_is_read_only_and_filters_eligibility(self):
        worker = bulkrr.Worker("episode_upgrade_preview",
                               {"sonarr": {"url": "http://localhost:8989", "key": "test"}},
                               config={"series_ids": [11]})
        results, failures = [], []
        worker.finished_data.connect(results.append)
        worker.failed.connect(failures.append)
        sample = [{"id": 21, "monitored": True,
                   "airDateUtc": "2020-01-01T00:00:00Z",
                   "episodeFile": {"qualityCutoffNotMet": True}},
                  {"id": 22, "monitored": True,
                   "airDateUtc": "2020-01-01T00:00:00Z",
                   "episodeFile": {"qualityCutoffNotMet": False}}]
        with patch.object(worker, "call", return_value=sample) as api:
            worker.run()
        api.assert_called_once_with("sonarr", "episode?seriesId=11&includeEpisodeFile=true")
        self.assertEqual(results, [[{"name": "EpisodeSearch", "episodeIds": [21]}]])
        self.assertEqual(failures, [])

    def test_sonarr_episode_upgrade_requires_confirmed_search_task(self):
        worker = bulkrr.Worker("episode_upgrade_search",
                               {"sonarr": {"url": "http://localhost:8989", "key": "test"}},
                               config={"episode_ids": [21]})
        results, failures = [], []
        worker.finished_data.connect(results.append)
        worker.failed.connect(failures.append)
        with patch.object(worker, "call", return_value={}) as api:
            worker.run()
        api.assert_called_once_with("sonarr", "command", "POST",
                                    {"name": "EpisodeSearch", "episodeIds": [21]})
        self.assertEqual(results, [{"queued": 1, "errors": []}])
        self.assertEqual(failures, [])


    def test_multi_server_routing_preview_never_calls_api(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(bulkrr, "SETTINGS", Path(folder) / "settings.json"):
                with patch("keyring.get_password", return_value=None):
                    window = bulkrr.Main()
                    try:
                        window.extra_profiles = [
                            {"id": "sonarr_extra", "kind": "sonarr",
                             "url": "http://extra:8989", "label": "Anime"}]
                        window.refresh_extra_list()
                        window.extra_list.setCurrentRow(0)
                        window.items = [{"input": "Example", "matches": [
                            {"app": "sonarr", "type": "anime", "label": "Example"}],
                            "selected": 0, "status": "ready", "message": "Ready"}]
                        window.refresh()
                        window.table.selectRow(0)
                        with patch.object(window, "run_worker") as worker:
                            with patch.object(bulkrr.QMessageBox, "information") as notice:
                                window.preview_extra_routing()
                                self.assertIn("No server requests", notice.call_args.args[2])
                            worker.assert_not_called()
                    finally:
                        window.close()

    def test_episode_upgrade_cancel_does_not_start_search(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(bulkrr, "SETTINGS", Path(folder) / "settings.json"):
                with patch("keyring.get_password", return_value=None):
                    window = bulkrr.Main()
                    try:
                        with patch.object(bulkrr.QMessageBox, "question",
                                          return_value=bulkrr.QMessageBox.StandardButton.No):
                            with patch.object(window, "run_worker") as worker:
                                window.episode_upgrades_previewed(
                                    [{"name": "EpisodeSearch", "episodeIds": [21]}])
                                worker.assert_not_called()
                    finally:
                        window.close()

    def test_routed_library_check_worker_reads_only_selected_profile(self):
        worker = bulkrr.Worker("routed_library_check", {}, config={
            "routes": [{"profile": {"id": "anime", "kind": "sonarr",
                                    "url": "http://anime:8989", "label": "Anime"},
                        "item_ids": [1]}],
            "credentials": {"anime": "test-secret"},
        })
        results, failures = [], []
        worker.finished_data.connect(results.append)
        worker.failed.connect(failures.append)
        with patch.object(bulkrr, "get_json", return_value=[{"id": 2}]) as api:
            worker.run()
        api.assert_called_once_with("http://anime:8989", "test-secret", "series")
        self.assertEqual(results[0][0]["library_count"], 1)
        self.assertEqual(failures, [])

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
