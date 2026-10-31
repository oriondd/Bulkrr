import unittest
from datetime import date
from bulkrr_calendar import parse_schedule, fetch_schedule


class CalendarTests(unittest.TestCase):
    def test_schedule_normalization(self):
        data = [
            {"show": {"id": 1, "name": "A &amp; B"}, "airdate": "2026-11-01", "season": 2, "number": 3, "name": "Episode"},
            {"show": {"id": 1, "name": "A &amp; B"}, "airdate": "2026-11-01", "season": 2, "number": 3},
            {"show": {"id": 2, "name": "Bad"}, "airdate": "not-a-date"},
        ]
        items = parse_schedule(data)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "A & B")

    def test_invalid_response(self):
        with self.assertRaises(ValueError):
            parse_schedule({})
        with self.assertRaises(ValueError):
            fetch_schedule(day="2026-11-01")


if __name__ == "__main__":
    unittest.main()
