"""Public AniList trending anime discovery (read-only, no credentials).

All returned entries are metadata candidates; Bulkrr's review workflow is
still required before any Sonarr/Radarr operation.
"""
import json
import urllib.request

ENDPOINT = "https://graphql.anilist.co"
QUERY = """query ($page: Int, $perPage: Int) {
  Page(page: $page, perPage: $perPage) {
    media(type: ANIME, sort: TRENDING_DESC) {
      title { english romaji }
      startDate { year }
      description(asHtml: false)
      trending
    }
  }
}"""


def parse_trending(payload):
    """Validate and normalize AniList's public GraphQL response."""
    if not isinstance(payload, dict) or payload.get("errors"):
        raise ValueError("AniList returned an invalid or unsuccessful response")
    page = payload.get("data", {}).get("Page", {})
    records = page.get("media") if isinstance(page, dict) else None
    if not isinstance(records, list):
        raise ValueError("AniList response does not contain a media list")
    result = []
    seen = set()
    for record in records[:50]:
        if not isinstance(record, dict):
            continue
        names = record.get("title")
        if not isinstance(names, dict):
            continue
        title = names.get("english") or names.get("romaji")
        if not isinstance(title, str) or not title.strip():
            continue
        title = title.strip()[:250]
        year_data = record.get("startDate")
        year = year_data.get("year") if isinstance(year_data, dict) else None
        if type(year) is not int or not 1880 <= year <= 2200:
            year = None
        key = (title.casefold(), year)
        if key in seen:
            continue
        seen.add(key)
        score = record.get("trending")
        if type(score) is not int or score < 0:
            score = 0
        result.append({
            "title": title,
            "type": "anime",
            "year": year,
            "overview": str(record.get("description") or "")[:1000],
            "popularity": score,
            "release_date": str(year) if year else "",
        })
    return result


def fetch_trending_anime(limit=25):
    """Fetch the current AniList trending ranking with bounded IO."""
    if type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError("Trending limit must be between 1 and 50")
    body = json.dumps({
        "query": QUERY,
        "variables": {"page": 1, "perPage": limit},
    }).encode("utf-8")
    request = urllib.request.Request(
        ENDPOINT,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Bulkrr/2.0 (anime discovery)",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        raw = response.read(512 * 1024 + 1)
    if len(raw) > 512 * 1024:
        raise ValueError("AniList response exceeds the maximum supported size")
    return parse_trending(json.loads(raw.decode("utf-8")))[:limit]
