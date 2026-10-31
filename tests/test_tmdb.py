import json
import unittest
from unittest.mock import patch

from bulkrr_tmdb import fetch_trending, normalize_trending, fetch_collection, normalize_collection


class TMDBTrendingTests(unittest.TestCase):
    def test_normalization_deduplicates_and_handles_invalid_rows(self):
        result = normalize_trending({"results": [
            {"id": 12, "title": "Movie A", "release_date": "2026-01-01", "genre_ids": [27, 9648, 999999]},
            {"id": 12, "title": "Movie A", "release_date": "2026-01-01"},
            {"title": "", "release_date": "2025-01-01"},
            {"title": "Movie B", "release_date": "unknown"},
        ]}, "movie")
        self.assertEqual([x["title"] for x in result], ["Movie A", "Movie B"])
        self.assertEqual(result[0]["year"], 2026)
        self.assertEqual(result[0]["tmdb_id"], 12)
        self.assertEqual(result[0]["genres"], ["Horror", "Mystery"])
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

    def test_verified_collection_filters_invalid_parts_and_duplicate_ids(self):
        records = normalize_collection({"parts": [
            {"id": 1, "title": "First", "release_date": "2001-02-03"},
            {"id": 1, "title": "Duplicate", "release_date": "2002-02-03"},
            {"id": 2, "title": "Second", "release_date": ""},
            {"id": True, "title": "Invalid"},
            {"id": 3, "title": ""},
        ]})
        self.assertEqual([x["title"] for x in records], ["First", "Second"])
        self.assertEqual(records[0]["year"], 2001)
        self.assertIsNone(records[1]["year"])

    def test_collection_uses_bearer_header_and_numeric_id(self):
        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self, limit):
                return b'{"parts":[]}'
        with patch("bulkrr_tmdb.urllib.request.urlopen", return_value=Response()) as mocked:
            self.assertEqual(fetch_collection(42, "test-token"), [])
        request = mocked.call_args.args[0]
        self.assertIn("/collection/42?", request.full_url)
        self.assertNotIn("test-token", request.full_url)
        self.assertEqual(request.get_header("Authorization"), "Bearer test-token")
        for ident in (0, True, -1, "42"):
            with self.subTest(ident=ident), self.assertRaises(ValueError):
                fetch_collection(ident, "test-token")

    def test_oversized_response_rejected(self):
        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self, limit):
                return b"x" * limit
        with patch("bulkrr_tmdb.urllib.request.urlopen", return_value=Response()):
            with self.assertRaisesRegex(ValueError, "exceeds size limit"):
                fetch_trending("movie", "test-token")

    def test_genre_id_types_and_malformed_results(self):
        results = normalize_trending({"results": [
            {"title": "Mystery Film", "genre_ids": [9648, True, "27", 27]},
            None,
            {"title": "No Genres", "genre_ids": "27"},
        ]}, "movie")
        self.assertEqual(results[0]["genres"], ["Mystery", "Horror"])
        self.assertEqual(results[1]["genres"], [])

    def test_invalid_token_and_request_bounds(self):
        for token in ("", "a b", None):
            with self.subTest(token=token), self.assertRaises(ValueError):
                fetch_trending("movie", token)
        with self.assertRaises(ValueError):
            fetch_trending("movie", "valid", limit=21)


if __name__ == "__main__":
    unittest.main()
