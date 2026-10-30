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
        if not isinstance(total, int) or not isinstance(available, int):
            continue
        if total <= 0:
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
