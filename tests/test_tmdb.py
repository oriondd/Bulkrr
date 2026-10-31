import json
import unittest
from unittest.mock import patch

from bulkrr_tmdb import fetch_trending, normalize_trending


class TMDBTrendingTests(unittest.TestCase):
    def test_normalization_deduplicates_and_handles_invalid_rows(self):
        result = normalize_trending({"results": [
            {"id": 12, "title": "Movie A", "release_date": "2026-01-01"},
            {"id": 12, "title": "Movie A", "release_date": "2026-01-01"},
            {"title": "", "release_date": "2025-01-01"},
            {"title": "Movie B", "release_date": "unknown"},
        ]}, "movie")
        self.assertEqual([x["title"] for x in result], ["Movie A", "Movie B"])
        self.assertEqual(result[0]["year"], 2026)
        self.assertEqual(result[0]["tmdb_id"], 12)
        self.assertIsNone(result[1]["year"])

    def test_tv_normalization_and_invalid_payload(self):
        self.assertEqual(normalize_trending({"results": [
            {"name": "Show", "first_air_date": "2025-06-01"},
        ]}, "tv")[0]["year"], 2025)
        with self.assertRaises(ValueError):
            normalize_trending({"results": {}}, "movie")

    def test_bearer_auth_not_url_query(self):
        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self, n):
                self.bound = n
                return b'{"results":[]}'
        response = Response()
        with patch("bulkrr_tmdb.urllib.request.urlopen", return_value=response) as mocked:
            self.assertEqual(fetch_trending("tv", "test-token"), [])
        request = mocked.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer test-token")
        self.assertNotIn("test-token", request.full_url)
        self.assertEqual(response.bound, 512 * 1024 + 1)

    def test_invalid_token_and_request_bounds(self):
        for token in ("", "a b", None):
            with self.subTest(token=token), self.assertRaises(ValueError):
                fetch_trending("movie", token)
        with self.assertRaises(ValueError):
            fetch_trending("movie", "valid", limit=21)


if __name__ == "__main__":
    unittest.main()
