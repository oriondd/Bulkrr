"""API error and retry regression tests (no real network calls)."""

import io
import unittest
import urllib.error
from unittest.mock import patch

from bulkrr_api import get_json


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return b'{"ok": true}'


class ApiTests(unittest.TestCase):
    @patch("bulkrr_api.urllib.request.urlopen")
    def test_successful_get(self, open_url):
        open_url.return_value = FakeResponse()
        self.assertEqual(
            get_json("http://localhost:7878", "secret", "system/status"), {"ok": True}
        )

    @patch("bulkrr_api.time.sleep")
    @patch("bulkrr_api.urllib.request.urlopen")
    def test_get_retries_temporary_failure(self, open_url, sleep):
        open_url.side_effect = [
            urllib.error.HTTPError(
                "http://localhost", 503, "Unavailable", {}, io.BytesIO(b"secret")
            ),
            FakeResponse(),
        ]
        self.assertEqual(
            get_json("http://localhost:7878", "secret", "movie"), {"ok": True}
        )
        self.assertEqual(open_url.call_count, 2)

    @patch("bulkrr_api.urllib.request.urlopen")
    def test_post_is_never_retried(self, open_url):
        open_url.side_effect = urllib.error.URLError("connection reset")
        with self.assertRaises(RuntimeError):
            get_json(
                "http://localhost:7878", "secret", "movie", "POST", {"title": "Example"}
            )
        self.assertEqual(open_url.call_count, 1)

    @patch("bulkrr_api.urllib.request.urlopen")
    def test_http_error_does_not_expose_response_body(self, open_url):
        open_url.side_effect = urllib.error.HTTPError(
            "http://localhost", 401, "Unauthorized", {}, io.BytesIO(b"private-token")
        )
        with self.assertRaises(RuntimeError) as context:
            get_json("http://localhost:7878", "secret", "movie")
        self.assertNotIn("private-token", str(context.exception))
        self.assertNotIn("secret", str(context.exception))


if __name__ == "__main__":
    unittest.main()
