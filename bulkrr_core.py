"""Pure metadata parsing and matching helpers for Bulkrr.

No Qt or network dependency: safe to import in unit tests.
"""

import difflib
import re
import urllib.parse


def title_parts(text):
    text = text.strip()
    typ = None
    m = re.match(r"^(movie|tv|anime)\s*:\s*(.*)$", text, re.I)
    if m:
        typ, text = m.group(1).lower(), m.group(2).strip()
    y = re.search(r"\((\d{4})\)\s*$", text)
    year = int(y.group(1)) if y else None
    if y:
        text = text[: y.start()].strip()
    return typ, text, year


def similarity(a, b):
    return difflib.SequenceMatcher(None, a.casefold(), b.casefold()).ratio()


def candidate_score(query, year, obj):
    title = obj.get("title") or ""
    score = similarity(query, title)
    if year and obj.get("year"):
        diff = abs(year - int(obj["year"]))
        score += 0.08 if diff == 0 else (0.02 if diff == 1 else -0.12)
    return score


def classify(series):
    genres = [g.casefold() for g in (series.get("genres") or [])]
    lang = series.get("originalLanguage") or {}
    lang = str(lang.get("name", "") if isinstance(lang, dict) else lang).casefold()
    if "anime" in genres or ("animation" in genres and "japanese" in lang):
        return "anime"
    return "tv"


def poster_url(match):
    if not match:
        return None
    for entry in match.get("data", {}).get("images", []) or []:
        if entry.get("coverType", "").lower() in ("poster", "cover"):
            url = entry.get("remoteUrl") or entry.get("url")
            if url and urllib.parse.urlparse(url).scheme in ("https", "http"):
                return url
    return None
