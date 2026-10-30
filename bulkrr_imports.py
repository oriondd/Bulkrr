"""Import sources and session persistence, independent of Qt and network access."""

import csv
import io
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SUPPORTED_EXTENSIONS = {".txt", ".csv"}
SESSION_VERSION = 1


def normalize_titles(lines):
    """Remove blanks and duplicate lines while preserving order and spelling."""
    seen = set()
    result = []
    for value in lines:
        title = str(value).strip().lstrip("\ufeff")
        if not title or title.startswith("#"):
            continue
        key = title.casefold()
        if key not in seen:
            seen.add(key)
            result.append(title)
    return result


def parse_source(text, suffix):
    suffix = suffix.lower()
    if suffix == ".txt":
        return normalize_titles(text.splitlines())
    if suffix != ".csv":
        raise ValueError("Only .txt and .csv files are supported")
    reader = csv.reader(io.StringIO(text, newline=""))
    rows = list(reader)
    if not rows:
        return []
    header = [str(v).strip().casefold() for v in rows[0]]
    title_index = next((i for i, v in enumerate(header) if v in ("title", "name")), None)
    has_header = title_index is not None
    type_index = next((i for i, v in enumerate(header) if v in ("type", "category", "media_type")), None)
    year_index = next((i for i, v in enumerate(header) if v == "year"), None)
    data_rows = rows[1:] if has_header else rows
    if title_index is None:
        title_index = 0
        type_index = None
        year_index = None
    titles = []
    for row in data_rows:
        if title_index >= len(row):
            continue
        title = row[title_index].strip()
        if not title:
            continue
        category = row[type_index].strip().lower() if type_index is not None and type_index < len(row) else ""
        if category in ("movie", "tv", "anime") and not title.lower().startswith(("movie:", "tv:", "anime:")):
            title = f"{category}: {title}"
        year = row[year_index].strip() if year_index is not None and year_index < len(row) else ""
        if len(year) == 4 and year.isdigit() and not title.endswith(f"({year})"):
            title += f" ({year})"
        titles.append(title)
    return normalize_titles(titles)


def read_source(path, max_bytes=5_000_000):
    source = Path(path)
    if source.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError("Unsupported file type; use TXT or CSV")
    if source.stat().st_size > max_bytes:
        raise ValueError("Import file exceeds the 5 MB limit")
    return parse_source(source.read_text(encoding="utf-8-sig"), source.suffix)


def save_session(path, text):
    """Atomically save the user's input; credentials and server data are excluded."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    data = {"version": SESSION_VERSION, "saved_at": datetime.now(timezone.utc).isoformat(), "titles": normalize_titles(text.splitlines())}
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=destination.parent, suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, indent=2)
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return len(data["titles"])


def load_session(path):
    source = Path(path)
    if source.stat().st_size > 5_000_000:
        raise ValueError("Session file exceeds the 5 MB limit")
    data = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("version") != SESSION_VERSION or not isinstance(data.get("titles"), list):
        raise ValueError("Unsupported or invalid Bulkrr session")
    if any(not isinstance(title, str) for title in data["titles"]):
        raise ValueError("Session titles must be text")
    return normalize_titles(data["titles"])
