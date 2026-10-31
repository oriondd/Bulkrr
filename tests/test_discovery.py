import unittest
from datetime import date
from bulkrr_discovery import normalize_discovery, upcoming, queue_lines


class DiscoveryTests(unittest.TestCase):
    def test_normalization_deduplicates_and_keeps_year(self):
        rows = [
            {"title": "Example", "release_date": "2026-11-04", "popularity": 3},
            {"title": "example", "release_date": "2026-11-04"},
            {"title": "Second", "release_date": "invalid"},
            {"title": ""},
        ]
        found = normalize_discovery(rows, "movie")
        self.assertEqual(len(found), 2)
        self.assertEqual(found[0]["year"], 2026)
        self.assertIsNone(found[1]["year"])

    def test_upcoming_filters_and_sorts(self):
        items = normalize_discovery([
            {"name": "Later", "first_air_date": "2026-12-01"},
            {"name": "Earlier", "first_air_date": "2026-11-01"},
            {"name": "Past", "first_air_date": "2020-01-01"},
            {"name": "Unknown"},
        ], "tv")
        self.assertEqual([x["title"] for x in upcoming(items, date(2026, 10, 30))], ["Earlier", "Later"])

    def test_review_queue_has_explicit_category(self):
        self.assertEqual(queue_lines([
            {"title": "Film", "type": "movie", "year": 2026},
            {"title": "Show", "type": "anime", "year": None},
            {"title": "Show", "type": "anime", "year": None},
            {"title": "", "type": "tv"},
        ]), ["movie: Film (2026)", "anime: Show"])

    def test_genres_are_bounded_and_nonfinite_popularity_is_sanitized(self):
        records = normalize_discovery([
            {"title": "Example", "genres": ["Mystery", 123, "Thriller"], "popularity": float("nan")},
            {"title": "Another", "genres": "not-a-list", "popularity": float("inf")},
        ], "tv")
        self.assertEqual(records[0]["genres"], ["Mystery", "Thriller"])
        self.assertEqual(records[0]["popularity"], 0)
        self.assertEqual(records[1]["genres"], [])
        self.assertEqual(records[1]["popularity"], 0)

    def test_unknown_category_rejected(self):
        with self.assertRaises(ValueError):
            normalize_discovery([], "podcast")


if __name__ == "__main__":
    unittest.main()
