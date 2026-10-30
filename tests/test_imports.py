"""Phase 2 import and session regression tests (no Qt required)."""

import tempfile
import unittest
from pathlib import Path

from bulkrr_imports import load_session, normalize_titles, parse_source, read_source, save_session


class ImportTests(unittest.TestCase):
    def test_txt_deduplicates_and_ignores_comments(self):
        self.assertEqual(parse_source("movie: Alien\n# note\nMOVIE: ALIEN\n\ntv: Lost", ".txt"), ["movie: Alien", "tv: Lost"])

    def test_csv_headers_and_categories(self):
        text = 'title,type,year\n"The Matrix",movie,1999\n"Death Note",anime,2006\n'
        self.assertEqual(parse_source(text, ".csv"), ["movie: The Matrix (1999)", "anime: Death Note (2006)"])

    def test_csv_single_column_without_header(self):
        self.assertEqual(parse_source("Alien\nPredator\n", ".csv"), ["Alien", "Predator"])

    def test_reject_unknown_file_type(self):
        with self.assertRaises(ValueError):
            parse_source("anything", ".exe")

    def test_reject_oversized_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "titles.txt"
            path.write_text("movie: Alien", encoding="utf-8")
            with self.assertRaises(ValueError):
                read_source(path, max_bytes=2)

    def test_session_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.json"
            self.assertEqual(save_session(path, "movie: Alien\nmovie: Alien\ntv: Lost"), 2)
            self.assertEqual(load_session(path), ["movie: Alien", "tv: Lost"])
            self.assertNotIn("api_key", path.read_text(encoding="utf-8"))

    def test_headerless_csv_named_title_is_not_dropped(self):
        self.assertEqual(parse_source("Title of a Movie\\nAnother Movie\\n", ".csv"), ["Title of a Movie", "Another Movie"])

    def test_session_file_size_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.json"
            path.write_bytes(b" " * 5_000_001)
            with self.assertRaisesRegex(ValueError, "5 MB"):
                load_session(path)

    def test_invalid_session_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text('{"version": 999, "titles": []}', encoding="utf-8")
            with self.assertRaises(ValueError):
                load_session(path)


if __name__ == "__main__":
    unittest.main()
