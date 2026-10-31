import tempfile
import unittest
from pathlib import Path
from bulkrr_sessions import encode_snapshot, decode_snapshot, save_review, load_review


class ReviewSessionTests(unittest.TestCase):
    def test_roundtrip(self):
        items = [{"input": "movie: Film", "status": "ready", "action": "add", "selected": 0, "matches": [{"label": "Film (2026)", "data": {"apiKey": "secret"}}]}]
        data = encode_snapshot("movie: Film", items)
        self.assertNotIn(b"secret", data)
        self.assertEqual(decode_snapshot(data)["review"][0]["selected_title"], "Film (2026)")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session.json"
            save_review(path, "movie: Film", items)
            self.assertEqual(load_review(path)["titles"], ["movie: Film"])

    def test_oversized_review_counts_and_long_titles_rejected(self):
        import json
        for payload in (
            {"version": 2, "titles": ["x" * 1001], "review": []},
            {"version": 2, "titles": [], "review": [{}] * 10001},
            {"version": 2, "titles": [None], "review": []},
        ):
            with self.subTest(size=len(payload["review"])), self.assertRaises(ValueError):
                decode_snapshot(json.dumps(payload).encode("utf-8"))

    def test_atomic_save_keeps_previous_snapshot_if_replace_fails(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "snapshot.json"
            save_review(target, "movie: Original", [])
            original = target.read_bytes()
            with patch("bulkrr_sessions.os.replace", side_effect=OSError("disk error")):
                with self.assertRaises(OSError):
                    save_review(target, "movie: New", [])
            self.assertEqual(target.read_bytes(), original)
            self.assertEqual(list(Path(folder).glob("*.tmp")), [])

    def test_invalid_version_rejected(self):
        with self.assertRaises(ValueError):
            decode_snapshot(b'{"version": 1, "titles": [], "review": []}')


if __name__ == "__main__":
    unittest.main()
