import unittest
from bulkrr_collections import expand_collection


class CollectionTests(unittest.TestCase):
    def test_deduplicates_and_formats(self):
        data = [
            {"title": "First", "year": 2020},
            {"title": "First", "year": 2020},
            {"title": "Second", "inCinemas": "2025-05-01"},
        ]
        self.assertEqual(expand_collection(data), ["movie: First (2020)", "movie: Second (2025)"])

    def test_limit_and_validation(self):
        self.assertEqual(len(expand_collection([{"title": str(i)} for i in range(10)], limit=3)), 3)
        with self.assertRaises(ValueError):
            expand_collection([], kind="anime")


if __name__ == "__main__":
    unittest.main()
