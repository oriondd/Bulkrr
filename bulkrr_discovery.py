"""Safe discovery normalization and local recommendation helpers.

Discovery candidates are metadata only. Adding any title still requires the
existing Bulkrr review and approval workflow.
"""
from datetime import date


def normalize_discovery(records, kind):
    if kind not in ("movie", "tv", "anime"):
        raise ValueError("Unsupported discovery category")
    result = []
    seen = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        title = record.get("title") or record.get("name")
        if not isinstance(title, str) or not title.strip():
            continue
        title = title.strip()
        raw_date = record.get("release_date") or record.get("first_air_date") or record.get("inCinemas") or record.get("firstAired") or ""
        if not isinstance(raw_date, str):
            raw_date = ""
        if not raw_date and isinstance(record.get("year"), int):
            raw_date = str(record["year"])
        year = int(raw_date[:4]) if isinstance(raw_date, str) and len(raw_date) >= 4 and raw_date[:4].isdigit() else None
        key = (kind, title.casefold(), year)
        if key in seen:
            continue
        seen.add(key)
        try:
            popularity = float(record.get("popularity") or 0)
        except (TypeError, ValueError, OverflowError):
            popularity = 0.0
        result.append({
            "title": title,
            "type": kind,
            "year": year,
            "overview": str(record.get("overview") or "")[:1000],
            "popularity": popularity,
            "release_date": raw_date if isinstance(raw_date, str) else "",
        })
    return result


def upcoming(items, today=None):
    today = today or date.today()
    result = []
    for item in items:
        try:
            released = date.fromisoformat(item.get("release_date", ""))
        except (TypeError, ValueError):
            continue
        if released >= today:
            result.append(item)
    return sorted(result, key=lambda entry: entry["release_date"])


def queue_lines(items):
    """Format candidates for the existing manual-review import pipeline."""
    lines = []
    for item in items:
        kind = item.get("type")
        title = item.get("title")
        if kind not in ("movie", "tv", "anime") or not isinstance(title, str) or not title.strip():
            continue
        year = item.get("year")
        suffix = f" ({year})" if isinstance(year, int) and 1880 <= year <= 2200 else ""
        lines.append(f"{kind}: {title.strip()}{suffix}")
    return list(dict.fromkeys(lines))
