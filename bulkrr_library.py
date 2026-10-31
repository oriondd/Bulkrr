"""Read-only library inventory helpers for Sonarr and Radarr.

These functions never request downloads, modify entries, or delete files.
"""


def missing_movies(movies):
    """Return movies without a downloaded file, preserving their library metadata."""
    result = []
    for movie in movies:
        if not isinstance(movie, dict):
            continue
        if movie.get("hasFile") or movie.get("movieFile"):
            continue
        result.append({
            "id": movie.get("id"),
            "title": movie.get("title") or "Untitled movie",
            "year": movie.get("year"),
            "monitored": bool(movie.get("monitored", False)),
            "status": "missing",
        })
    return result


def missing_series(series):
    """Summarize missing episodes using Sonarr's per-series statistics.

    Sonarr may omit statistics; unknown counts must not be treated as zero.
    """
    result = []
    for show in series:
        if not isinstance(show, dict):
            continue
        stats = show.get("statistics")
        if not isinstance(stats, dict):
            continue
        total = stats.get("totalEpisodeCount")
        available = stats.get("episodeFileCount")
        if type(total) is not int or type(available) is not int:
            continue
        if total <= 0 or available < 0 or available > total:
            continue
        missing = max(0, total - available)
        if missing == 0:
            continue
        result.append({
            "id": show.get("id"),
            "title": show.get("title") or "Untitled series",
            "year": show.get("year"),
            "monitored": bool(show.get("monitored", False)),
            "total": total,
            "available": available,
            "missing": missing,
        })
    return result



def upgrade_movies(movies):
    """Find Radarr movies whose existing file explicitly misses its quality cutoff.

    A missing/unknown cutoff flag is *not* treated as upgrade eligible. This
    is intentionally conservative and never changes the configured profile.
    """
    result = []
    for movie in movies:
        if not isinstance(movie, dict) or not movie.get("hasFile"):
            continue
        movie_file = movie.get("movieFile")
        if not isinstance(movie_file, dict):
            continue
        if movie_file.get("qualityCutoffNotMet") is not True:
            continue
        ident = movie.get("id")
        if type(ident) is not int or ident <= 0:
            continue
        result.append({
            "id": ident,
            "title": movie.get("title") or "Untitled movie",
            "year": movie.get("year"),
            "monitored": bool(movie.get("monitored", False)),
            "status": "upgrade",
        })
    return result
