import unittest
from bulkrr_recommendations import rank_candidates


class RecommendationTests(unittest.TestCase):
    def test_title_matches_outrank_description_and_popularity(self):
        candidates = [
            {"title": "The Odyssey", "overview": "Space horror", "popularity": 9999},
            {"title": "Space Horror", "overview": "", "popularity": 1},
            {"title": "Cooking Class", "overview": "", "popularity": 5000},
        ]
        found = rank_candidates(candidates, "space horror")
        self.assertEqual([item["title"] for item in found], ["Space Horror", "The Odyssey"])

    def test_genre_preference_matches(self):
        candidates = [
            {"title": "A", "genres": ["Thriller", "Mystery"]},
            {"title": "B", "genres": ["Comedy"]},
        ]
        self.assertEqual(rank_candidates(candidates, preferred_genres=["mystery"])[0]["title"], "A")

    def test_invalid_preferences_rejected(self):
        for interests, genres in (("", ()), (None, ()), ("test", [None])):
            with self.subTest(interests=interests, genres=genres), self.assertRaises(ValueError):
                rank_candidates([], interests, genres)
        with self.assertRaises(ValueError):
            rank_candidates([], "test", limit=0)

    def test_nonfinite_popularity_is_safe_and_input_unchanged(self):
        candidates = [{"title": "Mystery A", "popularity": float("nan")},
                      {"title": "Mystery B", "popularity": 2}]
        self.assertEqual(rank_candidates(candidates, "mystery")[0]["title"], "Mystery B")
        self.assertTrue(__import__("math").isnan(candidates[0]["popularity"]))


if __name__ == "__main__":
    unittest.main()
