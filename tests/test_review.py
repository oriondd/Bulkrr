"""Regression tests for the import review summary."""

import unittest

from bulkrr_review import review_counts, review_summary


class ReviewSummaryTests(unittest.TestCase):
    def test_empty_summary(self):
        self.assertIn("No titles analyzed", review_summary([]))

    def test_status_counts(self):
        items = [
            {"status": "ready"},
            {"status": "ready"},
            {"status": "review"},
            {"status": "duplicate"},
            {"status": "done"},
            {"status": "error"},
            {"status": "failed"},
        ]
        self.assertEqual(review_counts(items)["ready"], 2)
        self.assertEqual(review_counts(items)["failed"], 2)
        self.assertIn("2 ready", review_summary(items))
        self.assertIn("1 duplicates", review_summary(items))


if __name__ == "__main__":
    unittest.main()
