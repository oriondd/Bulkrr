"""Dry-run safety checks: no API write calls, even for existing titles."""

import unittest

from bulkrr import Worker


class DryRunTests(unittest.TestCase):
    def make_item(self, action=None):
        item = {
            "input": "movie: Joker (2019)",
            "matches": [
                {
                    "app": "radarr",
                    "type": "movie",
                    "id": 475557,
                    "data": {"title": "Joker", "tmdbId": 475557},
                }
            ],
            "selected": 0,
        }
        if action:
            item["action"] = action
        return item

    def run_preview(self, existing, action=None):
        worker = Worker(
            "import",
            {"radarr": {"url": "http://localhost", "key": "fake"}},
            items=[self.make_item(action)],
            config={
                "dry_run": True,
                "search": True,
                "movie_folder": "/Movies",
                "radarr_profile": 4,
            },
        )
        calls = []
        results = []
        errors = []
        worker.call = lambda app, path, method="GET", payload=None: (
            calls.append((path, method)) or existing
        )
        worker.finished_data.connect(results.append)
        worker.failed.connect(errors.append)
        worker.run()
        self.assertFalse(errors, errors)
        self.assertEqual(len(results), 1)
        self.assertTrue(all(method == "GET" for _, method in calls))
        return results[0][0][2]

    def test_new_title_preview_does_not_write(self):
        self.assertIn("Would add", self.run_preview([]))

    def test_existing_upgrade_preview_does_not_write(self):
        self.assertIn(
            "Would request search",
            self.run_preview([{"tmdbId": 475557, "id": 42}], "upgrade"),
        )

    def test_existing_skip_preview_does_not_write(self):
        self.assertIn(
            "Would skip",
            self.run_preview([{"tmdbId": 475557, "id": 42}], "skip"),
        )


if __name__ == "__main__":
    unittest.main()
