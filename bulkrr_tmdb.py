"""Read-only TMDB trending movie/TV discovery with a user-provided read access token.

TMDB is not queried without explicit user credentials. No tokens are written
to Bulkrr settings or logs, and no media is imported automatically.
"""
import json
import urllib.request

BASE = "https://api.themoviedb.org/3"

GENRES = {
    12: "Adventure", 14: "Fantasy", 16: "Animation", 18: "Drama",
    27: "Horror", 28: "Action", 35: "Comedy", 36: "History",
    37: "Western", 53: "Thriller", 80: "Crime", 99: "Documentary",
    878: "Science Fiction", 9648: "Mystery", 10402: "Music",
    10749: "Romance", 10751: "Family", 10752: "War",
    10759: "Action & Adventure", 10762: "Kids", 10763: "News",
    10764: "Reality", 10765: "Sci-Fi & Fantasy", 10766: "Soap",
    10767: "Talk", 10768: "War & Politics",
}



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
            "genres": [GENRES[genre] for genre in genres[:20] if type(genre) is int and genre in GENRES],
            "release_date": raw_date,
            "tmdb_id": record.get("id") if type(record.get("id")) is int else None,
        })
    return found


def fetch_trending(kind, access_token, window="week", limit=20):
    if kind not in ("movie", "tv") or window not in ("day", "week"):
        raise ValueError("Unsupported TMDB trending request")
    if type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError("TMDB trending limit must be 1–20")
    if (not isinstance(access_token, str) or not access_token.strip()
            or len(access_token) > 512 or any(ch.isspace() for ch in access_token)):
        raise ValueError("Provide a TMDB API read access token")
    path = f"{BASE}/trending/{kind}/{window}"
    request = urllib.request.Request(
        path + "?language=en-US",
        headers={"Accept": "application/json", "User-Agent": "Bulkrr/2.0",
                 "Authorization": "Bearer " + access_token.strip()},
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        raw = response.read(512 * 1024 + 1)
    if len(raw) > 512 * 1024:
        raise ValueError("TMDB response exceeds size limit")
    return normalize_trending(json.loads(raw.decode("utf-8")), kind)[:limit]
