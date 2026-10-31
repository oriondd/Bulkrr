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


if __name__ == "__main__":
    unittest.main()
