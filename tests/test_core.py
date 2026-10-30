"""Regression tests for Bulkrr's existing title parsing and matching helpers."""

import unittest

from bulkrr import candidate_score, classify, poster_url, similarity, title_parts


class TitleParsingTests(unittest.TestCase):
    def test_movie_with_year(self):
        self.assertEqual(title_parts("movie: Joker (2019)"), ("movie", "Joker", 2019))

    def test_anime_prefix_is_case_insensitive(self):
        self.assertEqual(
            title_parts("ANIME: 91 Days (2016)"), ("anime", "91 Days", 2016)
        )

    def test_title_without_prefix_or_year(self):
        self.assertEqual(title_parts("Severance"), (None, "Severance", None))

    def test_title_with_internal_parentheses(self):
        self.assertEqual(
            title_parts("tv: The Office (US) (2005)"),
            ("tv", "The Office (US)", 2005),
        )


class MatchingTests(unittest.TestCase):
    def test_similarity_ignores_case(self):
        self.assertEqual(similarity("JOKER", "joker"), 1.0)

    def test_matching_year_is_preferred(self):
        exact = candidate_score("Joker", 2019, {"title": "Joker", "year": 2019})
        wrong = candidate_score("Joker", 2019, {"title": "Joker", "year": 2000})
        self.assertGreater(exact, wrong)

    def test_anime_genre_is_detected(self):
        self.assertEqual(classify({"genres": ["Anime"]}), "anime")

    def test_japanese_animation_is_detected(self):
        self.assertEqual(
            classify(
                {
                    "genres": ["Animation"],
                    "originalLanguage": {"name": "Japanese"},
                }
            ),
            "anime",
        )

    def test_non_anime_is_tv(self):
        self.assertEqual(classify({"genres": ["Drama"]}), "tv")

    def test_poster_requires_http_url(self):
        match = {
            "data": {
                "images": [
                    {"coverType": "poster", "remoteUrl": "file:///private/poster.jpg"}
                ]
            }
        }
        self.assertIsNone(poster_url(match))

    def test_poster_selects_https_url(self):
        match = {
            "data": {
                "images": [
                    {"coverType": "poster", "remoteUrl": "https://example.org/a.jpg"}
                ]
            }
        }
        self.assertEqual(poster_url(match), "https://example.org/a.jpg")


if __name__ == "__main__":
    unittest.main()
