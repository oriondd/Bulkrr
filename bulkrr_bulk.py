"""Explicit, non-destructive bulk search planning for Radarr and Sonarr.

All functions are pure: callers must confirm the plan before executing commands.
"""

def plan_searches(app, ids):
    if app not in ("radarr", "sonarr"):
        raise ValueError("Unsupported server type")
    unique = []
    seen = set()
    for value in ids:
        if type(value) is not int or value <= 0:
            raise ValueError("Library IDs must be positive integers")
        if value not in seen:
            seen.add(value)
            unique.append(value)
    if len(unique) > 500:
        raise ValueError("Bulk operations are limited to 500 items")
    if not unique:
        return []
    if app == "radarr":
        return [{"name": "MoviesSearch", "movieIds": unique}]
    return [{"name": "SeriesSearch", "seriesId": ident} for ident in unique]


def estimate_storage(item_count, average_gib):
    """Rough capacity estimate; not an assertion about actual release sizes."""
    if type(item_count) is not int or item_count < 0:
        raise ValueError("Item count must be a nonnegative integer")
    if not isinstance(average_gib, (float, int)) or isinstance(average_gib, bool) or average_gib < 0:
        raise ValueError("Average size must be nonnegative")
    if average_gib == float("inf") or average_gib != average_gib:
        raise ValueError("Average size must be finite")
    return round(item_count * average_gib, 2)


def plan_episode_searches(episodes):
    """Plan explicit Sonarr episode upgrade searches without changing files.

    Only monitored, aired episodes with a file explicitly below the quality
    cutoff qualify. Unknown cutoff status and missing files are excluded.
    """
    from datetime import datetime, timezone
    if not isinstance(episodes, list) or len(episodes) > 5000:
        raise ValueError("Expected at most 5000 episode records")
    eligible, seen = [], set()
    now = datetime.now(timezone.utc)
    for episode in episodes:
        if not isinstance(episode, dict) or episode.get("monitored") is not True:
            continue
        ident = episode.get("id")
        if type(ident) is not int or ident <= 0 or ident in seen:
            continue
        file_info = episode.get("episodeFile")
        if not isinstance(file_info, dict) or file_info.get("qualityCutoffNotMet") is not True:
            continue
        air_date = episode.get("airDateUtc")
        if not isinstance(air_date, str):
            continue
        try:
            air_time = datetime.fromisoformat(air_date.replace("Z", "+00:00"))
        except ValueError:
            continue
        if air_time.tzinfo is None or air_time > now:
            continue
        seen.add(ident)
        eligible.append(ident)
        if len(eligible) > 500:
            raise ValueError("Episode searches are limited to 500 items")
    return [{"name": "EpisodeSearch", "episodeIds": eligible}] if eligible else []
