"""Regression tests for per-destination library caching during approved imports."""
import unittest
from unittest.mock import patch

import bulkrr


def approved(title, metadata_id):
    return {
        "input": title, "selected": 0, "action": "add",
        "matches": [{
            "app": "radarr", "type": "movie", "id": metadata_id,
            "data": {"title": title, "tmdbId": metadata_id},
        }],
    }


class ImportLibraryCacheTests(unittest.TestCase):
    def run_batch(self, responses):
        worker = bulkrr.Worker(
            "import", {"radarr": {"url": "http://example.invalid", "key": "test"}},
            items=[approved("First", 101), approved("Second", 102)],
            config={"movie_folder": "/movies", "radarr_profile": 1,
                    "search": False, "dry_run": False},
        )
        calls = []
        output = []
        def fake_call(app, endpoint, method="GET", payload=None):
            calls.append((app, endpoint, method))
            if method == "GET":
                return []
            return responses.pop(0)
        worker.call = fake_call
        worker.finished_data.connect(output.append)
        worker.run()
        return calls, output

    def test_invalid_root_folder_does_not_submit_import(self):
        worker = bulkrr.Worker(
            "import", {"radarr": {"url": "http://example.invalid", "key": "test"}},
            items=[approved("First", 101)],
            config={"movie_folder": ["not", "a", "path"], "radarr_profile": 1,
                    "search": False, "dry_run": False},
        )
        calls = []
        output = []
        def fake_call(app, endpoint, method="GET", payload=None):
            calls.append((app, endpoint, method))
            return []
        worker.call = fake_call
        worker.finished_data.connect(output.append)
        worker.run()
        self.assertEqual(output[0][0][1], "red")
        self.assertIn("Invalid root folder", output[0][0][2])
        self.assertEqual(sum(method == "POST" for _, _, method in calls), 0)

    def test_invalid_sonarr_root_folder_does_not_submit_import(self):
        item = {
            "input": "Example Series", "selected": 0, "action": "add",
            "matches": [{
                "app": "sonarr", "type": "tv", "id": 202,
                "data": {"title": "Example Series", "tvdbId": 202},
            }],
        }
        worker = bulkrr.Worker(
            "import", {"sonarr": {"url": "http://example.invalid", "key": "test"}},
            items=[item],
            config={"tv_folder": ["invalid", "path"], "sonarr_profile": 1,
                    "search": True, "dry_run": False},
        )
        calls = []
        output = []
        def fake_call(app, endpoint, method="GET", payload=None):
            calls.append((app, endpoint, method))
            return []
        worker.call = fake_call
        worker.finished_data.connect(output.append)
        worker.run()
        self.assertEqual(output[0][0][1], "red")
        self.assertIn("Invalid root folder", output[0][0][2])
        self.assertEqual(sum(method == "POST" for _, _, method in calls), 0)

    def test_dry_run_rejects_invalid_destinations_without_writes(self):
        for folder, profile, expected in (
            (["invalid", "path"], 1, "Invalid root folder"),
            ("/movies", "not-a-number", "Invalid quality profile"),
            ("/movies", 0, "Invalid quality profile"),
        ):
            with self.subTest(folder=folder, profile=profile):
                worker = bulkrr.Worker(
                    "import",
                    {"radarr": {"url": "http://example.invalid", "key": "test"}},
                    items=[approved("First", 101)],
                    config={"movie_folder": folder, "radarr_profile": profile,
                            "search": False, "dry_run": True},
                )
                calls = []
                output = []
                def fake_call(app, endpoint, method="GET", payload=None):
                    calls.append((app, endpoint, method))
                    return []
                worker.call = fake_call
                worker.finished_data.connect(output.append)
                worker.run()
                self.assertEqual(output[0][0][1], "red")
                self.assertIn(expected, output[0][0][2])
                self.assertFalse(any(method == "POST" for _, _, method in calls))

    def test_invalid_profile_does_not_abort_entire_batch(self):
        worker = bulkrr.Worker(
            "import", {"radarr": {"url": "http://example.invalid", "key": "test"}},
            items=[approved("First", 101), approved("Second", 102)],
            config={"movie_folder": "/movies", "radarr_profile": "not-a-number",
                    "search": False, "dry_run": False},
        )
        calls = []
        output = []
        def fake_call(app, endpoint, method="GET", payload=None):
            calls.append((app, endpoint, method))
            return []
        worker.call = fake_call
        worker.finished_data.connect(output.append)
        worker.run()
        self.assertEqual(len(output[0]), 2)
        self.assertTrue(all(row[1] == "red" for row in output[0]))
        self.assertTrue(all("Invalid quality profile" in row[2] for row in output[0]))
        self.assertEqual(sum(method == "POST" for _, _, method in calls), 0)

    def test_malformed_library_entry_fails_without_writing(self):
        worker = bulkrr.Worker(
            "import", {"radarr": {"url": "http://example.invalid", "key": "test"}},
            items=[approved("First", 101)],
            config={"movie_folder": "/movies", "radarr_profile": 1,
                    "search": True, "dry_run": False},
        )
        calls = []
        output = []
        def fake_call(app, endpoint, method="GET", payload=None):
            calls.append((app, endpoint, method))
            return [None, {"tmdbId": 101}]
        worker.call = fake_call
        worker.finished_data.connect(output.append)
        worker.run()
        self.assertEqual(sum(method == "POST" for _, _, method in calls), 0)
        self.assertEqual(output[0][0][1], "red")
        self.assertIn("invalid library listing", output[0][0][2])

    def test_malformed_library_listing_fails_without_writing(self):
        worker = bulkrr.Worker(
            "import", {"radarr": {"url": "http://example.invalid", "key": "test"}},
            items=[approved("First", 101)],
            config={"movie_folder": "/movies", "radarr_profile": 1,
                    "search": True, "dry_run": False},
        )
        calls = []
        output = []
        def fake_call(app, endpoint, method="GET", payload=None):
            calls.append((app, endpoint, method))
            return {"unexpected": "object"}
        worker.call = fake_call
        worker.finished_data.connect(output.append)
        worker.run()
        self.assertEqual(sum(method == "POST" for _, _, method in calls), 0)
        self.assertEqual(output[0][0][1], "red")
        self.assertIn("invalid library listing", output[0][0][2])

    def test_successful_additions_reuse_library_snapshot(self):
        calls, output = self.run_batch([
            {"id": 1, "tmdbId": 101}, {"id": 2, "tmdbId": 102},
        ])
        self.assertEqual(sum(method == "GET" for _, _, method in calls), 1)
        self.assertEqual(sum(method == "POST" for _, _, method in calls), 2)
        self.assertEqual(len(output[0]), 2)

    def test_duplicate_metadata_id_in_batch_is_not_added_twice(self):
        worker = bulkrr.Worker(
            "import", {"radarr": {"url": "http://example.invalid", "key": "test"}},
            items=[approved("First", 101), approved("Same Movie", 101)],
            config={"movie_folder": "/movies", "radarr_profile": 1,
                    "search": False, "dry_run": False},
        )
        calls = []
        output = []
        def fake_call(app, endpoint, method="GET", payload=None):
            calls.append((app, endpoint, method))
            if method == "GET":
                return []
            return {"id": 1, "tmdbId": 101}
        worker.call = fake_call
        worker.finished_data.connect(output.append)
        worker.run()
        self.assertEqual(sum(method == "GET" for _, _, method in calls), 1)
        self.assertEqual(sum(method == "POST" for _, _, method in calls), 1)
        self.assertEqual(output[0][1][2], "Skipped existing library title")

    def test_duplicate_add_after_incomplete_response_is_not_repeated(self):
        worker = bulkrr.Worker(
            "import", {"radarr": {"url": "http://example.invalid", "key": "test"}},
            items=[approved("First", 101), approved("Same Movie", 101)],
            config={"movie_folder": "/movies", "radarr_profile": 1,
                    "search": False, "dry_run": False},
        )
        calls = []
        output = []
        def fake_call(app, endpoint, method="GET", payload=None):
            calls.append((app, endpoint, method))
            if method == "GET":
                return []
            return {"id": 1}
        worker.call = fake_call
        worker.finished_data.connect(output.append)
        worker.run()
        self.assertEqual(sum(method == "POST" for _, _, method in calls), 1)
        self.assertEqual(output[0][1][2], "Skipped existing library title")

    def test_incomplete_add_response_invalidates_snapshot(self):
        calls, output = self.run_batch([
            {"id": 1}, {"id": 2, "tmdbId": 102},
        ])
        self.assertEqual(sum(method == "GET" for _, _, method in calls), 2)
        self.assertEqual(len(output[0]), 2)


if __name__ == "__main__":
    unittest.main()
