"""Local, transparent discovery ranking without telemetry or hidden downloads.

Recommendations are ranked from the user's supplied keywords and optional
genre preferences; no account history is collected or transmitted.
"""
import math
import re

WORDS = re.compile(r"[a-z0-9]+", re.I)


def rank_candidates(candidates, interests="", preferred_genres=(), limit=50):
    """Rank normalized discovery records using local text relevance.

    A preference match outranks popularity. Popularity only breaks ties;
    missing or non-finite popularity contributes zero. The original record
    is returned unchanged so queueing remains in the manual review pipeline.
    """
    if not isinstance(interests, str):
        raise ValueError("Interests must be text")
    if not isinstance(preferred_genres, (list, tuple, set)):
        raise ValueError("Preferred genres must be a collection")
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("Recommendation limit must be between 1 and 100")
    terms = set(WORDS.findall(interests.casefold())) 
    for genre in preferred_genres:
        if not isinstance(genre, str):
            raise ValueError("Genres must be text")
        terms.update(WORDS.findall(genre.casefold()))
    if not terms:
        raise ValueError("Enter at least one interest to personalize recommendations")
    ranked = []
    for position, item in enumerate(candidates):
        if not isinstance(item, dict) or not isinstance(item.get("title"), str):
            continue
        title_words = set(WORDS.findall(item["title"].casefold()))
        other_words = set(WORDS.findall(str(item.get("overview") or "").casefold()))
        genres = item.get("genres") or []
        if isinstance(genres, (list, tuple)):
            other_words.update(WORDS.findall(" ".join(str(g) for g in genres).casefold()))
        title_hits = len(terms & title_words)
        other_hits = len(terms & other_words)
        score = 4 * title_hits + other_hits
        if not score:
            continue
        try:
            popularity = float(item.get("popularity") or 0)
            if not math.isfinite(popularity):
                popularity = 0.0
        except (TypeError, ValueError, OverflowError):
            popularity = 0.0
        ranked.append((-score, -max(0.0, popularity), position, item))
    ranked.sort(key=lambda row: row[:3])
    return [entry for _, _, _, entry in ranked[:limit]]
