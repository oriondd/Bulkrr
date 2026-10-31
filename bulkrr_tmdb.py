"""Read-only TMDB trending movie/TV discovery with a user-provided read access token.

TMDB is not queried without explicit user credentials. No tokens are written
to Bulkrr settings or logs, and no media is imported automatically.
"""
import json
import re
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
        if year is not None and not 1880 <= year <= 2200:
            year = None
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
            "popularity": 0,  # TMDB trending endpoint already supplies ranked results
            "genres": [GENRES[genre] for genre in genres[:20] if type(genre) is int and genre in GENRES],
            "release_date": raw_date,
            "tmdb_id": record.get("id") if type(record.get("id")) is int else None,
            "poster_url": ("https://image.tmdb.org/t/p/w342" + record["poster_path"])
                if isinstance(record.get("poster_path"), str)
                and re.fullmatch(r"/[A-Za-z0-9_-]+\.(?:jpg|jpeg|png|webp)", record["poster_path"]) else None,
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



def fetch_new_releases(kind, access_token, days=45, limit=20):
    """Discover recently released titles, not trending titles.

    The date window uses the local calendar date and TMDB release/first-air
    dates. No library changes occur during this read-only request.
    """
    import datetime
    from urllib.parse import urlencode
    if kind not in ("movie", "tv"):
        raise ValueError("Release type must be movie or tv")
    if type(days) is not int or not 1 <= days <= 90:
        raise ValueError("Release window must be 1–90 days")
    if type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError("Release limit must be 1–20")
    if (not isinstance(access_token, str) or not access_token.strip()
            or len(access_token) > 512 or any(ch.isspace() for ch in access_token)):
        raise ValueError("Provide a TMDB API read access token")
    today = datetime.date.today()
    first = today - datetime.timedelta(days=days)
    field = "primary_release_date" if kind == "movie" else "first_air_date"
    params = {
        "language": "en-US", "sort_by": "popularity.desc",
        "include_adult": "false", "page": "1",
        field + ".gte": first.isoformat(),
        field + ".lte": today.isoformat(),
    }
    if kind == "movie":
        params["region"] = "US"
    request = urllib.request.Request(
        f"{BASE}/discover/{kind}?" + urlencode(params),
        headers={"Accept": "application/json", "User-Agent": "Bulkrr/2.0",
                 "Authorization": "Bearer " + access_token.strip()},
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        raw = response.read(512 * 1024 + 1)
    if len(raw) > 512 * 1024:
        raise ValueError("TMDB response exceeds size limit")
    records = normalize_trending(json.loads(raw.decode("utf-8")), kind)
    # Keep only records with a verifiable in-window release date.
    return [
        item for item in records
        if item.get("release_date") and first.isoformat() <= item["release_date"] <= today.isoformat()
    ][:limit]


def normalize_collection(payload):
    """Return movie candidates from a verified TMDB collection detail response."""
    if not isinstance(payload, dict) or not isinstance(payload.get("parts"), list):
        raise ValueError("TMDB returned invalid collection metadata")
    records, seen = [], set()
    for movie in payload["parts"][:200]:
        if not isinstance(movie, dict):
            continue
        title = movie.get("title")
        if not isinstance(title, str) or not title.strip():
            continue
        title = title.strip()[:250]
        date = movie.get("release_date")
        year = int(date[:4]) if isinstance(date, str) and len(date) >= 4 and date[:4].isdigit() else None
        if year is not None and not 1880 <= year <= 2200:
            year = None
        ident = movie.get("id")
        if type(ident) is not int or ident <= 0 or ident in seen:
            continue
        seen.add(ident)
        records.append({
            "title": title, "year": year, "type": "movie",
            "overview": str(movie.get("overview") or "")[:1000],
            "genres": [], "tmdb_id": ident, "popularity": 0,
            "poster_url": ("https://image.tmdb.org/t/p/w342" + movie["poster_path"])
                if isinstance(movie.get("poster_path"), str)
                and re.fullmatch(r"/[A-Za-z0-9_-]+\.(?:jpg|jpeg|png|webp)", movie["poster_path"]) else None,
        })
    return records


def fetch_collection(collection_id, access_token):
    """Fetch one explicitly identified TMDB collection; never modify libraries."""
    if type(collection_id) is not int or not 1 <= collection_id <= 2_147_483_647:
        raise ValueError("Collection ID must be a positive integer")
    if (not isinstance(access_token, str) or not access_token.strip()
            or len(access_token) > 512 or any(ch.isspace() for ch in access_token)):
        raise ValueError("Provide a TMDB API read access token")
    request = urllib.request.Request(
        f"{BASE}/collection/{collection_id}?language=en-US",
        headers={"Accept": "application/json", "User-Agent": "Bulkrr/2.0",
                 "Authorization": "Bearer " + access_token.strip()},
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        raw = response.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError("TMDB collection response exceeds size limit")
    return normalize_collection(json.loads(raw.decode("utf-8")))


def normalize_collection_search(payload):
    """Parse TMDB collection search results without trusting arbitrary metadata."""
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise ValueError("TMDB returned invalid collection search metadata")
    results, seen = [], set()
    for item in payload["results"][:50]:
        if not isinstance(item, dict):
            continue
        ident, name = item.get("id"), item.get("name")
        if type(ident) is not int or ident <= 0 or ident in seen:
            continue
        if not isinstance(name, str) or not name.strip():
            continue
        seen.add(ident)
        results.append({"id": ident, "name": name.strip()[:250]})
    return results


def search_collections(term, access_token):
    """Search official TMDB collections, returning IDs for explicit user selection."""
    from urllib.parse import urlencode
    if not isinstance(term, str) or not 2 <= len(term.strip()) <= 100:
        raise ValueError("Enter a collection name between 2 and 100 characters")
    if (not isinstance(access_token, str) or not access_token.strip()
            or len(access_token) > 512 or any(ch.isspace() for ch in access_token)):
        raise ValueError("Provide a TMDB API read access token")
    request = urllib.request.Request(
        BASE + "/search/collection?" + urlencode({
            "query": term.strip(), "language": "en-US", "include_adult": "false",
        }),
        headers={"Accept": "application/json", "User-Agent": "Bulkrr/2.0",
                 "Authorization": "Bearer " + access_token.strip()},
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        raw = response.read(512 * 1024 + 1)
    if len(raw) > 512 * 1024:
        raise ValueError("TMDB collection search response exceeds size limit")
    return normalize_collection_search(json.loads(raw.decode("utf-8")))
