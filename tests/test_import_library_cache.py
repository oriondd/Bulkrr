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

    def test_successful_additions_reuse_library_snapshot(self):
        calls, output = self.run_batch([
            {"id": 1, "tmdbId": 101}, {"id": 2, "tmdbId": 102},
        ])
        self.assertEqual(sum(method == "GET" for _, _, method in calls), 1)
        self.assertEqual(sum(method == "POST" for _, _, method in calls), 2)
        self.assertEqual(len(output[0]), 2)

    def test_incomplete_add_response_invalidates_snapshot(self):
        calls, output = self.run_batch([
            {"id": 1}, {"id": 2, "tmdbId": 102},
        ])
        self.assertEqual(sum(method == "GET" for _, _, method in calls), 2)
        self.assertEqual(len(output[0]), 2)


if __name__ == "__main__":
    unittest.main()
