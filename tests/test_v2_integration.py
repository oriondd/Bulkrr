"""Phase 3-5 contract checks across discovery, library and review boundaries."""
import unittest

from bulkrr_bulk import plan_searches
from bulkrr_discovery import queue_lines
from bulkrr_library import missing_movies, upgrade_movies
from bulkrr_recommendations import rank_candidates
from bulkrr_trending import parse_trending
from bulkrr_core import title_parts


class V2IntegrationTests(unittest.TestCase):
    def test_trending_recommendation_enters_explicit_review_format(self):
        response = {"data": {"Page": {"media": [
            {"title": {"english": "Space Mystery"}, "startDate": {"year": 2026}, "trending": 80},
            {"title": {"english": "Romance Comedy"}, "startDate": {"year": 2025}, "trending": 90},
        ]}}}
        records = parse_trending(response)
        selected = rank_candidates(records, "space mystery")
        self.assertEqual(queue_lines(selected), ["anime: Space Mystery (2026)"])
        self.assertEqual(title_parts(queue_lines(selected)[0]), ("anime", "Space Mystery", 2026))

    def test_missing_and_upgrade_searches_never_overlap(self):
        movies = [
            {"id": 1, "title": "Absent", "hasFile": False, "monitored": True},
            {"id": 2, "title": "Below cutoff", "hasFile": True, "monitored": True,
             "movieFile": {"qualityCutoffNotMet": True}},
            {"id": 3, "title": "Complete", "hasFile": True, "monitored": True,
             "movieFile": {"qualityCutoffNotMet": False}},
        ]
        missing = missing_movies(movies)
        upgrades = upgrade_movies(movies)
        self.assertEqual([x["id"] for x in missing], [1])
        self.assertEqual([x["id"] for x in upgrades], [2])
        self.assertEqual(plan_searches("radarr", [x["id"] for x in upgrades]),
                         [{"name": "MoviesSearch", "movieIds": [2]}])


if __name__ == "__main__":
    unittest.main()
