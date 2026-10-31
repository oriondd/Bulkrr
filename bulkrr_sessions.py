"""Versioned, bounded review-session snapshots without server credentials.

Snapshots are advisory. Import matches must be reanalyzed against live
Sonarr/Radarr libraries before the user can import anything.
"""
import json
from pathlib import Path
from bulkrr_imports import normalize_titles

VERSION = 2
MAX_BYTES = 5_000_000


def snapshot(titles, items):
    records = []
    for item in items:
        if not isinstance(item, dict):
            continue
        selected = item.get("selected", -1)
        matches = item.get("matches", [])
        match = matches[selected] if isinstance(matches, list) and type(selected) is int and 0 <= selected < len(matches) else None
        records.append({
            "input": str(item.get("input", ""))[:500],
            "status": str(item.get("status", "review"))[:32],
            "action": str(item.get("action", "skip")) if item.get("action") in ("skip", "add", "upgrade", "replace") else "skip",
            "selected_title": str(match.get("label", ""))[:500] if isinstance(match, dict) else "",
        })
    return {"version": VERSION, "titles": normalize_titles(titles.splitlines()), "review": records}


def encode_snapshot(titles, items):
    data = json.dumps(snapshot(titles, items), ensure_ascii=False, indent=2).encode("utf-8")
    if len(data) > MAX_BYTES:
        raise ValueError("Review session exceeds 5 MB")
    return data


def decode_snapshot(data):
    if len(data) > MAX_BYTES:
        raise ValueError("Review session exceeds 5 MB")
    obj = json.loads(data)
    if not isinstance(obj, dict) or obj.get("version") != VERSION or not isinstance(obj.get("titles"), list) or not isinstance(obj.get("review"), list):
        raise ValueError("Invalid review session")
    if any(not isinstance(title, str) for title in obj["titles"]):
        raise ValueError("Invalid title")
    if any(not isinstance(item, dict) for item in obj["review"]):
        raise ValueError("Invalid review record")
    if len(obj["review"]) > 10000 or len(obj["titles"]) > 10000:
        raise ValueError("Review session has too many entries")
    if any(len(title) > 1000 for title in obj["titles"]):
        raise ValueError("Review session title is too long")
    return {"titles": normalize_titles(obj["titles"]), "review": obj["review"]}


def save_review(path, titles, items):
    import os
    import tempfile
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=".tmp", delete=False) as stream:
            temp = Path(stream.name)
            stream.write(encode_snapshot(titles, items))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, destination)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def load_review(path):
    source = Path(path)
    if source.stat().st_size > MAX_BYTES:
        raise ValueError("Review session exceeds 5 MB")
    return decode_snapshot(source.read_bytes())
