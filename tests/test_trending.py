import unittest
from unittest.mock import patch
from bulkrr_trending import fetch_trending_anime, parse_trending


class TrendingTests(unittest.TestCase):
    def test_normalize_titles_year_and_duplicates(self):
        payload = {"data": {"Page": {"media": [
            {"title": {"english": "Test Anime", "romaji": "Romaji"},
             "startDate": {"year": 2026}, "trending": 900},
            {"title": {"english": "Test Anime"}, "startDate": {"year": 2026}},
            {"title": {"english": None, "romaji": "Another"}, "trending": 2},
            {"title": {}, "startDate": {"year": 2020}},
            None,
        ]}}}
        records = parse_trending(payload)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["title"], "Test Anime")
        self.assertEqual(records[0]["year"], 2026)
        self.assertEqual(records[0]["type"], "anime")
        self.assertEqual(records[1]["title"], "Another")

    def test_invalid_payloads(self):
        for payload in ({}, {"errors": [{"message": "Rate limit"}]},
                        {"data": {"Page": {"media": "wrong"}}}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                parse_trending(payload)

    def test_limit_validation(self):
        for limit in (0, 51, True, "10"):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                fetch_trending_anime(limit)

    def test_request_is_bounded_and_has_correct_graphql_variables(self):
        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self, n):
                self.max_read = n
                return b'{"data":{"Page":{"media":[]}}}'
        response = Response()
        with patch("bulkrr_trending.urllib.request.urlopen", return_value=response) as mocked:
            self.assertEqual(fetch_trending_anime(12), [])
        request = mocked.call_args.args[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(mocked.call_args.kwargs["timeout"], 12)
        self.assertEqual(response.max_read, 512 * 1024 + 1)
        self.assertEqual(__import__("json").loads(request.data)["variables"]["perPage"], 12)


if __name__ == "__main__":
    unittest.main()
