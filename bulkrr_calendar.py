"""Optional public TV release calendar. No account or API key is required."""
from datetime import date
from html import unescape
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json
import re


API = "https://api.tvmaze.com/schedule"


def parse_schedule(entries):
    if not isinstance(entries, list):
        raise ValueError("Unexpected calendar response")
    result = []
    seen = set()
    for episode in entries[:1000]:
        if not isinstance(episode, dict):
            continue
        show = episode.get("show")
        if not isinstance(show, dict):
            continue
        title = show.get("name")
        airdate = episode.get("airdate")
        if not isinstance(title, str) or not title.strip() or not isinstance(airdate, str):
            continue
        try:
            date.fromisoformat(airdate)
        except ValueError:
            continue
        key = (show.get("id"), airdate, episode.get("season"), episode.get("number"))
        if key in seen:
            continue
        seen.add(key)
        result.append({
            "title": unescape(re.sub(r"<[^>]*>", "", title.strip()))[:200],
            "date": airdate,
            "season": episode.get("season"),
            "episode": episode.get("number"),
            "name": str(episode.get("name") or "")[:150],
        })
    return sorted(result, key=lambda entry: (entry["date"], entry["title"]))


def fetch_schedule(day=None, country="US", timeout=10):
    day = day or date.today()
    if not isinstance(day, date):
        raise ValueError("Invalid calendar date")
    if country != "US":
        raise ValueError("Only US schedules are currently supported")
    url = API + "?" + urlencode({"country": country, "date": day.isoformat()})
    request = Request(url, headers={"User-Agent": "Bulkrr/2.0", "Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError("Calendar response too large")
    return parse_schedule(json.loads(raw))
