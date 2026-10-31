"""Pure, safe franchise/collection expansion for existing import review."""
from bulkrr_imports import normalize_titles


def expand_collection(records, kind="movie", limit=100):
    if kind not in ("movie", "tv"):
        raise ValueError("Unsupported collection type")
    if not isinstance(records, list):
        raise ValueError("Collection results must be a list")
    if not isinstance(limit, int) or not 1 <= limit <= 500:
        raise ValueError("Invalid collection size")
    titles = []
    seen = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        title = record.get("title") or record.get("name")
        if not isinstance(title, str) or not title.strip():
            continue
        year = record.get("year")
        if year is None:
            released = record.get("inCinemas") or record.get("firstAired") or ""
            if isinstance(released, str) and len(released) >= 4 and released[:4].isdigit():
                year = int(released[:4])
        suffix = f" ({year})" if isinstance(year, int) and 1880 <= year <= 2200 else ""
        line = f"{kind}: {title.strip()}{suffix}"
        key = line.casefold()
        if key in seen:
            continue
        seen.add(key)
        titles.append(line)
        if len(titles) >= limit:
            break
    return normalize_titles(titles)
