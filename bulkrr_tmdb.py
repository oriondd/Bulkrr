"""Read-only TMDB trending movie/TV discovery with a user-provided API key.

TMDB is not queried without explicit user credentials. No API keys are written
to Bulkrr settings or logs, and no media is imported automatically.
"""
import json
import urllib.parse
import urllib.request

BASE = "https://api.themoviedb.org/3"


def normalize_trending(payload, kind):
    if kind not in ("movie", "tv"):
        raise ValueError("Trending type must be movie or tv")
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise ValueError("TMDB returned an invalid trending response")
    found, seen = [], set()
    for record in payload["results"][:50]:
        if not isinstance(record, dict):
            continue
        title = record.get("title" if kind == "movie" else "name")
        if not isinstance(title, str) or not title.strip():
            continue
        title = title.strip()[:250]
        raw_date = record.get("release_date" if kind == "movie" else "first_air_date")
        if not isinstance(raw_date, str):
            raw_date = ""
        year = int(raw_date[:4]) if len(raw_date) >= 4 and raw_date[:4].isdigit() else None
        key = (title.casefold(), year)
        if key in seen:
            continue
        seen.add(key)
        genres = record.get("genre_ids")
        if not isinstance(genres, list):
            genres = []
        found.append({
            "title": title,
            "type": kind,
            "year": year,
            "overview": str(record.get("overview") or "")[:1000],
            "popularity": 0,
            "genres": [],
            "release_date": raw_date,
            "tmdb_id": record.get("id") if type(record.get("id")) is int else None,
        })
    return found


def fetch_trending(kind, api_key, window="week", limit=20):
    if kind not in ("movie", "tv") or window not in ("day", "week"):
        raise ValueError("Unsupported TMDB trending request")
    if type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError("TMDB trending limit must be 1–20")
    if not isinstance(api_key, str) or not api_key.strip() or len(api_key) > 256:
        raise ValueError("Provide a TMDB API key")
    path = f"{BASE}/trending/{kind}/{window}"
    query = urllib.parse.urlencode({"api_key": api_key.strip(), "language": "en-US"})
    request = urllib.request.Request(
        path + "?" + query,
        headers={"Accept": "application/json", "User-Agent": "Bulkrr/2.0"},
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        raw = response.read(512 * 1024 + 1)
    if len(raw) > 512 * 1024:
        raise ValueError("TMDB response exceeds size limit")
    return normalize_trending(json.loads(raw.decode("utf-8")), kind)[:limit]
