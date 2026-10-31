"""Regression tests for Phase 3 read-only inventory."""

import unittest

from bulkrr_library import missing_movies, missing_series, upgrade_movies


class MissingInventoryTests(unittest.TestCase):
    def test_movies_only_missing(self):
        movies = [
            {"id": 1, "title": "Missing", "year": 2001, "hasFile": False, "monitored": True},
            {"id": 2, "title": "Present", "hasFile": True},
            {"id": 3, "title": "Present too", "movieFile": {"id": 9}},
        ]
        self.assertEqual(missing_movies(movies), [
            {"id": 1, "title": "Missing", "year": 2001, "monitored": True, "status": "missing"}
        ])

    def test_series_counts_and_unknown_statistics(self):
        shows = [
            {"id": 4, "title": "Partial", "statistics": {"totalEpisodeCount": 12, "episodeFileCount": 8}},
            {"id": 5, "title": "Complete", "statistics": {"totalEpisodeCount": 10, "episodeFileCount": 10}},
            {"id": 6, "title": "Unknown"},
            {"id": 7, "title": "Not aired", "statistics": {"totalEpisodeCount": 0, "episodeFileCount": 0}},
        ]
        self.assertEqual(missing_series(shows), [
            {"id": 4, "title": "Partial", "year": None, "monitored": False, "total": 12, "available": 8, "missing": 4}
        ])

    def test_upgrade_movies_requires_explicit_below_cutoff_file(self):
        movies = [
            {"id": 1, "title": "Upgrade", "hasFile": True,
             "movieFile": {"qualityCutoffNotMet": True}, "monitored": True},
            {"id": 2, "title": "Complete", "hasFile": True,
             "movieFile": {"qualityCutoffNotMet": False}},
            {"id": 3, "title": "Unknown", "hasFile": True, "movieFile": {}},
            {"id": 4, "title": "Missing", "hasFile": False,
             "movieFile": {"qualityCutoffNotMet": True}},
            {"id": True, "title": "Invalid", "hasFile": True,
             "movieFile": {"qualityCutoffNotMet": True}},
            {"id": 6, "title": "Bad file", "hasFile": True, "movieFile": "bad"},
        ]
        self.assertEqual(upgrade_movies(movies), [{
            "id": 1, "title": "Upgrade", "year": None,
            "monitored": True, "status": "upgrade",
        }])

    def test_malformed_episode_statistics_are_not_reported_as_missing(self):
        series = [
            {"id": 1, "title": "Negative", "statistics": {"totalEpisodeCount": 10, "episodeFileCount": -1}},
            {"id": 2, "title": "Overflow", "statistics": {"totalEpisodeCount": 10, "episodeFileCount": 12}},
            {"id": 3, "title": "Boolean", "statistics": {"totalEpisodeCount": True, "episodeFileCount": 0}},
            {"id": 4, "title": "Valid", "statistics": {"totalEpisodeCount": 10, "episodeFileCount": 7}},
        ]
        self.assertEqual([item["id"] for item in missing_series(series)], [4])

    def test_counts_never_negative(self):
        self.assertEqual(missing_series([{
            "id": 8, "title": "Extra", "statistics": {"totalEpisodeCount": 4, "episodeFileCount": 5}
        }]), [])


if __name__ == "__main__":
    unittest.main()
