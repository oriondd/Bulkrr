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

    def test_invalid_version_rejected(self):
        with self.assertRaises(ValueError):
            decode_snapshot(b'{"version": 1, "titles": [], "review": []}')


if __name__ == "__main__":
    unittest.main()
