"""Opt-in extension manifest discovery; never executes third-party code.

Plugins are declarative presets that supply import titles. They cannot make
network requests, access secrets, or execute Python.
"""
import json
from pathlib import Path
from bulkrr_imports import normalize_titles

MAX_MANIFEST = 200_000


def validate_manifest(manifest):
    if not isinstance(manifest, dict) or manifest.get("schema") != 1:
        raise ValueError("Unsupported extension schema")
    name = manifest.get("name")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
        raise ValueError("Invalid extension name")
    if set(manifest) - {"schema", "name", "description", "titles"}:
        raise ValueError("Unsupported extension fields")
    titles = manifest.get("titles")
    if not isinstance(titles, list) or len(titles) > 500 or any(not isinstance(t, str) or len(t) > 500 for t in titles):
        raise ValueError("Invalid extension titles")
    description = manifest.get("description", "")
    if not isinstance(description, str) or len(description) > 500:
        raise ValueError("Invalid extension description")
    return {"name": name.strip(), "description": description, "titles": normalize_titles(titles)}


def load_manifest(path):
    path = Path(path)
    if path.suffix.lower() != ".json" or path.stat().st_size > MAX_MANIFEST:
        raise ValueError("Invalid extension file")
    return validate_manifest(json.loads(path.read_text(encoding="utf-8")))


def discover_manifests(folder):
    root = Path(folder)
    if not root.exists():
        return []
    result = []
    for path in sorted(root.glob("*.json"))[:100]:
        if path.is_symlink():
            continue
        try:
            result.append((path, load_manifest(path)))
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
            continue
    return result
