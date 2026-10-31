"""Local genre preferences derived from connected library metadata.

No viewing activity or personal data is transmitted. Only genre frequencies
from already-connected Sonarr/Radarr libraries are considered.
"""
from collections import Counter


def favorite_genres(movies=(), series=(), limit=6):
    if type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError("Genre limit must be between 1 and 20")
    counts = Counter()
    for collection in (movies, series):
        if not isinstance(collection, (list, tuple)):
            continue
        for item in collection[:10000]:
            if not isinstance(item, dict):
                continue
            genres = item.get("genres")
            if not isinstance(genres, list):
                continue
            seen = set()
            for genre in genres[:30]:
                if not isinstance(genre, str):
                    continue
                name = genre.strip()
                key = name.casefold()
                if not name or len(name) > 80 or key in seen:
                    continue
                seen.add(key)
                counts[key] += 1
    return [name for name, _ in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))[:limit]]
