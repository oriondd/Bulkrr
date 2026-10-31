"""Headless GUI construction smoke tests for the unified 2.0 screens."""
import os
import gc
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from qt_app import APP
import bulkrr


class MainWindowSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = APP
        # Headless UI tests must not start background HTTP poster threads.
        cls.poster_patch = patch.object(bulkrr, "poster_url", return_value=None)
        cls.poster_patch.start()

    @classmethod
    def tearDownClass(cls):
        cls.poster_patch.stop()
        # Destroy native Qt objects while QApplication is still alive.
        cls.app.closeAllWindows()
        cls.app.processEvents()
        gc.collect()
        cls.app.processEvents()

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

    def test_refresh_handles_partial_match_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(bulkrr, "SETTINGS", Path(folder) / "settings.json"):
                with patch("keyring.get_password", return_value=None):
                    window = bulkrr.Main()
                    try:
                        window.items = [{
                            "input": "Fallback Title",
                            "matches": [{"app": "radarr", "type": "movie",
                                         "id": 22, "data": {"title": "Film"}}],
                            "selected": 0, "status": "ready"
                        }]
                        window.refresh()
                        self.assertEqual(window.table.item(0, 2).text(), "Film")
                        window.table.selectRow(0)
                        window.show_selected_poster()
                        self.assertIn("Film", window.preview_info.text())
                        window.items[0]["matches"] = [{"app": "sonarr", "type": "tv", "id": 11}]
                        window.refresh()
                        self.assertEqual(window.table.item(0, 2).text(), "Fallback Title")
                    finally:
                        window.close()

    def test_multi_destination_gui_prepares_separate_batches_without_api_calls(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(bulkrr, "SETTINGS", Path(folder) / "settings.json"):
                with patch("keyring.get_password", return_value="secret"):
                    window = bulkrr.Main()
                    try:
                        window.extra_profiles = [
                            {"id": "shows", "kind": "sonarr", "url": "http://shows:8989",
                             "label": "Shows"},
                            {"id": "films", "kind": "radarr", "url": "http://films:7878",
                             "label": "Films"}]
                        window.refresh_extra_list()
                        window.items = [
                            {"input": "Show", "matches": [{"app": "sonarr", "type": "tv",
                              "id": 11, "data": {"title": "Show"}}], "selected": 0,
                             "status": "ready"},
                            {"input": "Film", "matches": [{"app": "radarr", "type": "movie",
                              "id": 22, "data": {"title": "Film"}}], "selected": 0,
                             "status": "ready"}]
                        window.refresh()
                        window.table.setSelectionMode(
                            bulkrr.QAbstractItemView.SelectionMode.MultiSelection)
                        window.table.selectRow(0)
                        window.table.selectRow(1)
                        with patch.object(bulkrr.QInputDialog, "getItem",
                                          side_effect=[("Shows (shows)", True),
                                                       ("Films (films)", True)]):
                            with patch.object(bulkrr.QInputDialog, "getInt",
                                              side_effect=[(3, True), (7, True)]):
                                with patch.object(bulkrr.QInputDialog, "getText",
                                                  side_effect=[("/tv", True),
                                                               ("/anime", True),
                                                               ("/movies", True)]):
                                    with patch.object(window, "run_worker") as worker:
                                        window.prepare_extra_import()
                        worker.assert_called_once()
                        self.assertEqual(worker.call_args.args[0], "routed_import_preview")
                        batches = worker.call_args.kwargs["config"]["batches"]
                        self.assertEqual(len(batches), 2)
                        self.assertEqual(batches[0]["items"][0]["payload"]["rootFolderPath"], "/tv")
                        self.assertEqual(batches[1]["items"][0]["payload"]["rootFolderPath"], "/movies")
                    finally:
                        window.close()

    def test_routed_import_worker_writes_only_approved_new_titles(self):
        batch = {"profile": {"id": "films", "kind": "radarr",
                             "url": "http://films:7878"},
                 "items": [{"item_id": 1, "metadata_id": 22,
                            "duplicate_action": "skip",
                            "payload": {"title": "Film", "rootFolderPath": "/movies",
                                        "qualityProfileId": 7}}]}
        config = {"batches": [batch], "credentials": {"films": "secret"},
                  "approved": True, "search": False}
        worker = bulkrr.Worker("routed_import_execute", {}, config=config)
        results, failures = [], []
        worker.finished_data.connect(results.append)
        worker.failed.connect(failures.append)
        with patch.object(bulkrr, "get_json", side_effect=[
            [], {"id": 100}]) as api:
            worker.run()
        self.assertEqual(failures, [])
        self.assertEqual(results[0][0]["status"], "added")
        self.assertEqual(api.call_count, 2)
        self.assertEqual(api.call_args.args[3], "POST")
        self.assertEqual(api.call_args.args[4]["qualityProfileId"], 7)
        self.assertFalse(api.call_args.args[4]["addOptions"]["searchForMovie"])

    def test_routed_preview_rejection_never_starts_import(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(bulkrr, "SETTINGS", Path(folder) / "settings.json"):
                with patch("keyring.get_password", return_value=None):
                    window = bulkrr.Main()
                    try:
                        window.pending_routed_import = {"batches": [], "credentials": {}}
                        with patch.object(bulkrr.QMessageBox, "question",
                                          return_value=bulkrr.QMessageBox.StandardButton.No) as ask:
                            with patch.object(window, "run_worker") as worker:
                                window.routed_import_previewed([
                                    {"action": "add", "error": None}])
                        ask.assert_called_once()
                        worker.assert_not_called()
                        self.assertIsNone(window.pending_routed_import)
                    finally:
                        window.close()

    def test_routed_preview_all_existing_never_requests_approval(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(bulkrr, "SETTINGS", Path(folder) / "settings.json"):
                with patch("keyring.get_password", return_value=None):
                    window = bulkrr.Main()
                    try:
                        window.pending_routed_import = {"batches": [], "credentials": {}}
                        with patch.object(bulkrr.QMessageBox, "question") as ask:
                            with patch.object(bulkrr.QMessageBox, "information") as notice:
                                window.routed_import_previewed([
                                    {"action": "skip", "error": None}])
                        ask.assert_not_called()
                        notice.assert_called_once()
                        self.assertIsNone(window.pending_routed_import)
                    finally:
                        window.close()

    def test_routed_preview_failed_library_check_blocks_approval(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(bulkrr, "SETTINGS", Path(folder) / "settings.json"):
                with patch("keyring.get_password", return_value=None):
                    window = bulkrr.Main()
                    try:
                        window.pending_routed_import = {"batches": [], "credentials": {}}
                        with patch.object(bulkrr.QMessageBox, "question") as ask:
                            with patch.object(bulkrr.QMessageBox, "warning") as warning:
                                window.routed_import_previewed([
                                    {"action": "add", "error": "Destination unreachable"}])
                        ask.assert_not_called()
                        warning.assert_called_once()
                        self.assertIsNone(window.pending_routed_import)
                    finally:
                        window.close()

    def test_routed_import_search_flag_enabled_after_approval(self):
        batch = {"profile": {"id": "films", "kind": "radarr",
                             "url": "http://films:7878"},
                 "items": [{"item_id": 1, "metadata_id": 22,
                            "duplicate_action": "skip",
                            "payload": {"title": "Film", "rootFolderPath": "/movies",
                                        "qualityProfileId": 7}}]}
        worker = bulkrr.Worker("routed_import_execute", {}, config={
            "batches": [batch], "credentials": {"films": "secret"},
            "approved": True, "search": True})
        results, failures = [], []
        worker.finished_data.connect(results.append)
        worker.failed.connect(failures.append)
        with patch.object(bulkrr, "get_json", side_effect=[[], {"id": 100}]) as api:
            worker.run()
        self.assertFalse(failures)
        self.assertEqual(results[0][0]["status"], "added")
        self.assertTrue(api.call_args.args[4]["addOptions"]["searchForMovie"])

    def test_routed_import_search_flag_enabled_for_sonarr(self):
        batch = {"profile": {"id": "shows", "kind": "sonarr",
                             "url": "http://shows:8989"},
                 "items": [{"item_id": 1, "metadata_id": 11,
                            "duplicate_action": "skip",
                            "payload": {"title": "Show", "rootFolderPath": "/tv",
                                        "qualityProfileId": 3}}]}
        worker = bulkrr.Worker("routed_import_execute", {}, config={
            "batches": [batch], "credentials": {"shows": "secret"},
            "approved": True, "search": True})
        results, failures = [], []
        worker.finished_data.connect(results.append)
        worker.failed.connect(failures.append)
        with patch.object(bulkrr, "get_json", side_effect=[[], {"id": 101}]) as api:
            worker.run()
        self.assertFalse(failures)
        self.assertEqual(results[0][0]["status"], "added")
        self.assertTrue(api.call_args.args[4]["addOptions"]["searchForMissingEpisodes"])

    def test_resume_merges_only_unfinished_titles(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(bulkrr, "SETTINGS", Path(folder) / "settings.json"):
                with patch("keyring.get_password", return_value=None):
                    window = bulkrr.Main()
                    try:
                        complete = {"input": "Finished", "matches": [],
                                    "selected": -1, "status": "skipped",
                                    "action": "skip", "message": "User excluded"}
                        pending = {"input": "Pending", "matches": [],
                                   "selected": -1, "status": "skipped",
                                   "action": "skip",
                                   "message": "Analysis stopped before lookup"}
                        window.items = [complete, pending]
                        window._resume_previous_items = list(window.items)
                        result = {"input": "Pending", "matches": [],
                                  "selected": -1, "status": "error",
                                  "message": "No matching title found"}
                        window.resumed_analysis([result])
                        self.assertIs(window.items[0], complete)
                        self.assertEqual(window.items[1]["input"], "Pending")
                        self.assertEqual(window.items[1]["status"], "skipped")
                        self.assertEqual(window.items[1]["message"],
                                         "No reliable metadata match — excluded from import")
                    finally:
                        window.close()

    def test_import_uses_current_search_checkbox_without_saving(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(bulkrr, "SETTINGS", Path(folder) / "settings.json"):
                with patch("keyring.get_password", return_value=None):
                    window = bulkrr.Main()
                    try:
                        window.settings = {"search": True}
                        window.server_data = {"connected": True}
                        window.search.setChecked(False)
                        window.items = [{
                            "input": "movie: Alien", "status": "ready", "selected": 0,
                            "matches": [{"label": "Alien", "type": "movie", "app": "radarr",
                                         "data": {"title": "Alien"}}], "message": "Ready",
                        }]
                        window.refresh()
                        with patch.object(bulkrr.QMessageBox, "question",
                                          return_value=bulkrr.QMessageBox.StandardButton.Yes):
                            with patch.object(window, "run_worker") as worker:
                                window.import_items()
                                self.assertEqual(worker.call_args.kwargs["config"]["search"], False)
                    finally:
                        window.close()

    def test_empty_single_title_recheck_does_not_leave_working_row(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(bulkrr, "SETTINGS", Path(folder) / "settings.json"):
                with patch("keyring.get_password", return_value=None):
                    window = bulkrr.Main()
                    try:
                        window.items = [
                            {"input": "movie: Corrected", "status": "working", "action": "review",
                             "matches": [], "selected": -1, "message": "Rechecking corrected title"},
                        ]
                        window._edit_recheck_row = 0
                        window.edited_title_analyzed([])
                        self.assertEqual(window.items[0]["status"], "error")
                        self.assertNotEqual(window.items[0]["status"], "ready")
                    finally:
                        window.close()

    def test_edit_recheck_rejects_duplicate_input_without_network(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(bulkrr, "SETTINGS", Path(folder) / "settings.json"):
                with patch("keyring.get_password", return_value=None):
                    window = bulkrr.Main()
                    try:
                        window.server_data = {"connected": True}
                        window.input.setPlainText("movie: Alien\\nmovie: Arrival")
                        window.items = [
                            {"input": "movie: Alien", "status": "review", "matches": [],
                             "selected": -1, "message": "Review"},
                            {"input": "movie: Arrival", "status": "review", "matches": [],
                             "selected": -1, "message": "Review"},
                        ]
                        window.refresh()
                        window.table.selectRow(0)
                        with patch.object(bulkrr.QInputDialog, "getText", return_value=("movie: Arrival", True)):
                            with patch.object(bulkrr.QMessageBox, "warning") as warning:
                                with patch.object(window, "run_worker") as run_worker:
                                    window.edit_selected_title()
                                    warning.assert_called_once()
                                    run_worker.assert_not_called()
                        self.assertEqual(window.input.toPlainText(), "movie: Alien\\nmovie: Arrival")
                    finally:
                        window.close()

    def test_progress_updates_existing_row_without_full_table_refresh(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(bulkrr, "SETTINGS", Path(folder) / "settings.json"):
                with patch("keyring.get_password", return_value=None):
                    window = bulkrr.Main()
                    try:
                        window.items = [
                            {"input": "movie: Progress", "status": "ready",
                             "matches": [], "selected": -1, "message": "Waiting"}
                        ]
                        window.refresh()
                        with patch.object(window, "refresh") as refresh:
                            window.row_update(0, "working", "Downloading metadata")
                            refresh.assert_not_called()
                        self.assertEqual(window.table.item(0, 6).text(), "Downloading metadata")
                        self.assertEqual(window.items[0]["status"], "working")
                    finally:
                        window.close()

    def test_large_review_batch_5000_rows_filters_without_losing_indices(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(bulkrr, "SETTINGS", Path(folder) / "settings.json"):
                with patch("keyring.get_password", return_value=None):
                    window = bulkrr.Main()
                    try:
                        window.items = [
                            {"input": f"movie: Load Test {i:04d}",
                             "status": "ready" if i % 5 else "review",
                             "matches": [], "selected": -1, "message": "Synthetic fixture"}
                            for i in range(5000)
                        ]
                        window.refresh()
                        self.assertEqual(window.table.rowCount(), 5000)
                        window.review_search.setText("Load Test 4999")
                        self.assertEqual(window.review_visible_count.text(), "1 of 5,000 shown")
                        self.assertFalse(window.table.isRowHidden(4999))
                        self.assertTrue(window.table.isRowHidden(4998))
                        window.review_search.clear()
                        self.assertEqual(window.review_visible_count.text(), "5,000 of 5,000 shown")
                    finally:
                        window.close()

    def test_resume_preserves_unfinished_placeholders_and_prior_decisions(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(bulkrr, "SETTINGS", Path(folder) / "settings.json"):
                with patch("keyring.get_password", return_value=None):
                    window = bulkrr.Main()
                    try:
                        previous = [
                            {"input": "movie: Existing", "status": "ready", "action": "upgrade",
                             "duplicate": {"id": 1}, "matches": [], "message": "User selected upgrade"},
                            {"input": "movie: Pending", "status": "review", "action": "review",
                             "matches": [], "message": "Analysis stopped before lookup"},
                        ]
                        window._resume_previous_items = previous
                        window.resumed_analysis([{
                            "input": "movie: Pending", "status": "review", "action": "review",
                            "matches": [], "message": "Analysis stopped before lookup",
                        }])
                        self.assertEqual(window.items[0]["action"], "upgrade")
                        self.assertEqual(window.items[1]["message"], "Analysis stopped before lookup")
                        self.assertNotEqual(window.items[1]["status"], "skipped")
                    finally:
                        window.close()

    def test_partial_category_decisions_preserve_previous_manual_choices(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(bulkrr, "SETTINGS", Path(folder) / "settings.json"):
                with patch("keyring.get_password", return_value=None):
                    window = bulkrr.Main()
                    try:
                        prior = {"input": "Existing", "status": "ready", "action": "upgrade",
                                 "duplicate": {"id": 1}, "matches": [], "message": "User selected upgrade"}
                        new = {"input": "New", "status": "duplicate", "action": "review",
                               "duplicate": {"id": 2}, "matches": [], "message": "Detected"}
                        window.items = [prior, new]
                        window.apply_category_decisions([new])
                        self.assertEqual(prior["action"], "upgrade")
                        self.assertEqual(prior["status"], "ready")
                        self.assertEqual(new["status"], "skipped")
                        self.assertEqual(new["action"], "skip")
                    finally:
                        window.close()

    def test_restoring_exclusion_requires_review_again(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(bulkrr, "SETTINGS", Path(folder) / "settings.json"):
                with patch("keyring.get_password", return_value=None):
                    window = bulkrr.Main()
                    try:
                        window.items = [
                            {"input": "Movie A", "status": "skipped", "action": "skip",
                             "matches": [{"label": "Movie A", "type": "movie", "app": "radarr", "data": {"title": "Movie A"}}], "selected": 0,
                             "message": "Excluded from import by user selection"},
                        ]
                        window.refresh()
                        window.table.selectRow(0)
                        window.restore_selected_rows()
                        self.assertEqual(window.items[0]["status"], "review")
                        self.assertEqual(window.items[0]["action"], "review")
                    finally:
                        window.close()

    def test_selected_row_exclusion_is_preview_only(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(bulkrr, "SETTINGS", Path(folder) / "settings.json"):
                with patch("keyring.get_password", return_value=None):
                    window = bulkrr.Main()
                    try:
                        window.items = [
                            {"input": "Movie A", "status": "ready", "action": "add",
                             "matches": [], "selected": -1},
                            {"input": "Movie B", "status": "ready", "action": "add",
                             "matches": [], "selected": -1},
                        ]
                        window.refresh()
                        window.table.selectRow(0)
                        with patch.object(bulkrr.QMessageBox, "question",
                                          return_value=bulkrr.QMessageBox.StandardButton.Yes):
                            window.skip_selected_rows()
                        self.assertEqual(window.items[0]["status"], "skipped")
                        self.assertEqual(window.items[0]["action"], "skip")
                        self.assertEqual(window.items[1]["status"], "ready")
                    finally:
                        window.close()

    def test_review_filters_and_sidebar_navigation(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(bulkrr, "SETTINGS", Path(folder) / "settings.json"):
                with patch("keyring.get_password", return_value=None):
                    window = bulkrr.Main()
                    try:
                        self.assertEqual(window.navigation.count(), 5)
                        self.assertEqual(window.tabs.currentIndex(), 1)
                        window.items = [
                            {"input": "Ready", "matches": [], "selected": -1, "status": "ready"},
                            {"input": "Review", "matches": [], "selected": -1, "status": "review"},
                            {"input": "Skipped", "matches": [], "selected": -1, "status": "skipped"},
                        ]
                        window.refresh()
                        self.assertIsNone(window.table.cellWidget(0, 0))
                        self.assertEqual(window.table.item(0, 0).text(), "●")
                        window.review_search.setText("Review")
                        self.assertEqual(window.review_visible_count.text(), "1 of 3 shown")
                        window.review_search.clear()
                        window.review_filter.setCurrentIndex(1)
                        self.assertEqual([window.table.isRowHidden(i) for i in range(3)],
                                         [True, False, True])
                        window.review_filter.setCurrentIndex(3)
                        self.assertEqual([window.table.isRowHidden(i) for i in range(3)],
                                         [True, True, False])
                        window.navigation.setCurrentRow(4)
                        self.assertEqual(window.tabs.currentIndex(), 4)
                    finally:
                        window.close()

    def test_category_decisions_are_preview_only_and_preserve_ambiguous_review(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(bulkrr, "SETTINGS", Path(folder) / "settings.json"):
                with patch("keyring.get_password", return_value=None):
                    window = bulkrr.Main()
                    try:
                        items = [
                            {"input": "Existing", "matches": [{"id": 1, "type": "movie", "data": {"title": "Existing"}, "app": "radarr", "score": 0.99}], "selected": 0,
                             "status": "duplicate", "duplicate": {"files": 0}, "action": "add"},
                            {"input": "Missing", "matches": [], "selected": -1,
                             "status": "error", "duplicate": None, "action": "add"},
                            {"input": "Ambiguous", "matches": [{"id": 2, "type": "movie", "data": {"title": "Ambiguous"}, "app": "radarr", "score": 0.75}], "selected": 0,
                             "status": "review", "duplicate": None, "action": "add"},
                            {"input": "Ready", "matches": [{"id": 3, "type": "movie", "data": {"title": "Ready"}, "app": "radarr", "score": 0.99}], "selected": 0,
                             "status": "ready", "duplicate": None, "action": "add"},
                        ]
                        with patch.object(window, "run_worker") as writes:
                            window.analyzed(items)
                        writes.assert_not_called()
                        self.assertEqual([i["status"] for i in window.items],
                                         ["skipped", "skipped", "review", "ready"])
                        self.assertEqual([i["action"] for i in window.items],
                                         ["skip", "skip", "review", "add"])
                    finally:
                        window.close()

    def test_analysis_stop_skips_remaining_titles_without_more_lookups(self):
        worker = bulkrr.Worker("analyze", {}, items=[
            "movie: First (2020)", "movie: Second (2021)", "movie: Third (2022)"])
        results = []
        worker.finished_data.connect(results.append)
        worker.request_stop_after_current()
        with patch.object(bulkrr, "get_json") as api:
            worker.run()
        api.assert_not_called()
        self.assertEqual(len(results[0]), 3)
        self.assertTrue(all(item["status"] == "skipped" for item in results[0]))

    def test_bulk_skip_duplicates_and_unresolved_matches(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(bulkrr, "SETTINGS", Path(folder) / "settings.json"):
                with patch("keyring.get_password", return_value=None):
                    window = bulkrr.Main()
                    try:
                        window.items = [
                            {"input": "Existing", "matches": [], "selected": -1,
                             "status": "duplicate", "duplicate": {"title": "Existing"}},
                            {"input": "Ambiguous", "matches": [], "selected": -1,
                             "status": "review"},
                            {"input": "Good", "matches": [], "selected": -1,
                             "status": "ready"}]
                        with patch.object(bulkrr.QMessageBox, "question",
                                          return_value=bulkrr.QMessageBox.StandardButton.Yes):
                            window.skip_all_duplicates()
                            window.skip_all_unresolved()
                        self.assertEqual([item["status"] for item in window.items],
                                         ["skipped", "skipped", "ready"])
                    finally:
                        window.close()

    def test_routed_import_worker_refuses_unapproved_writes(self):
        worker = bulkrr.Worker("routed_import_execute", {}, config={
            "batches": [], "credentials": {}, "approved": False})
        failures = []
        worker.failed.connect(failures.append)
        with patch.object(bulkrr, "get_json") as api:
            worker.run()
        self.assertEqual(api.call_count, 0)
        self.assertIn("PermissionError", failures[0])


if __name__ == "__main__":
    unittest.main()
