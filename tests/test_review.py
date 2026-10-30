"""Regression tests for the import review summary."""

import unittest

from bulkrr_review import review_counts, review_summary, match_confidence


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

    def test_match_confidence_ambiguity(self):
        best = {"score": 1.0}
        close = {"score": 0.95}
        self.assertIn("Ambiguous", match_confidence(best, [best, close]))
        self.assertEqual(match_confidence(best, [best]), "Strong match")

    def test_match_confidence_low(self):
        self.assertIn("Low confidence", match_confidence({"score": 0.65}))


if __name__ == "__main__":
    unittest.main()
