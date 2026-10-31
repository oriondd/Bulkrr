import unittest
from bulkrr_bulk import plan_searches, estimate_storage


class BulkPlanningTests(unittest.TestCase):
    def test_radarr_deduplicates(self):
        self.assertEqual(plan_searches("radarr", [4, 4, 5]), [{"name": "MoviesSearch", "movieIds": [4, 5]}])

    def test_sonarr_series_commands(self):
        self.assertEqual(plan_searches("sonarr", [3, 7]), [{"name": "SeriesSearch", "seriesId": 3}, {"name": "SeriesSearch", "seriesId": 7}])

    def test_empty_is_noop(self):
        self.assertEqual(plan_searches("radarr", []), [])

    def test_reject_invalid_ids(self):
        for ids in ([0], [-1], ["5"], [True], list(range(1, 502))):
            with self.subTest(ids=str(ids)[:20]):
                with self.assertRaises(ValueError):
                    plan_searches("radarr", ids)

    def test_storage_estimate(self):
        self.assertEqual(estimate_storage(8, 1.5), 12)
        with self.assertRaises(ValueError):
            estimate_storage(-1, 2)
        for invalid in (float("inf"), float("-inf"), float("nan")):
            with self.subTest(value=str(invalid)), self.assertRaises(ValueError):
                estimate_storage(1, invalid)

    def test_episode_upgrade_search_filters_and_deduplicates(self):
        from bulkrr_bulk import plan_episode_searches
        base = {"monitored": True, "airDateUtc": "2020-01-01T00:00:00Z",
                "episodeFile": {"qualityCutoffNotMet": True}}
        episodes = [dict(base, id=3), dict(base, id=3),
                    dict(base, id=4, monitored=False),
                    dict(base, id=5, episodeFile={"qualityCutoffNotMet": False}),
                    dict(base, id=6, airDateUtc="2999-01-01T00:00:00Z"),
                    dict(base, id=7, episodeFile=None),
                    dict(base, id=True), dict(base, id=8, airDateUtc="bad")]
        self.assertEqual(plan_episode_searches(episodes),
                         [{"name": "EpisodeSearch", "episodeIds": [3]}])

    def test_episode_upgrade_search_bounded_and_read_only(self):
        from bulkrr_bulk import plan_episode_searches
        import copy
        episode = {"id": 1, "monitored": True, "airDateUtc": "2020-01-01T00:00:00Z",
                   "episodeFile": {"qualityCutoffNotMet": True}}
        original = copy.deepcopy(episode)
        self.assertEqual(plan_episode_searches([episode]),
                         [{"name": "EpisodeSearch", "episodeIds": [1]}])
        self.assertEqual(episode, original)
        with self.assertRaises(ValueError):
            plan_episode_searches([episode] * 5001)


if __name__ == "__main__":
    unittest.main()
