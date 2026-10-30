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
    return round(item_count * average_gib, 2)
