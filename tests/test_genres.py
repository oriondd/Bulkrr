import unittest
from bulkrr_genres import favorite_genres
from bulkrr_recommendations import rank_candidates


class LibraryGenreTests(unittest.TestCase):
    def test_frequency_deduplication_and_stable_ties(self):
        movies = [
            {"genres": ["Horror", "Horror", "Thriller"]},
            {"genres": ["Horror", "Drama"]},
        ]
        shows = [{"genres": ["Thriller", "Drama"]}]
        self.assertEqual(favorite_genres(movies, shows), ["drama", "horror", "thriller"])

    def test_invalid_genres_ignored(self):
        self.assertEqual(favorite_genres([
            None, {"genres": "Horror"}, {"genres": [None, "", "Mystery", "mystery"]},
        ]), ["mystery"])
        with self.assertRaises(ValueError):
            favorite_genres(limit=0)

    def test_genre_preferences_rank_existing_discovery_candidates(self):
        preferences = favorite_genres([{"genres": ["Mystery", "Horror"]}])
        candidates = [
            {"title": "Comedy Movie", "genres": ["Comedy"], "popularity": 1000},
            {"title": "Detective Movie", "genres": ["Mystery"], "popularity": 1},
        ]
        self.assertEqual(rank_candidates(candidates, preferred_genres=preferences)[0]["title"], "Detective Movie")


if __name__ == "__main__":
    unittest.main()
