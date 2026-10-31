"""GitHub release metadata validation for optional update notifications.

This module does not install updates or execute downloaded code.
"""
import json
import urllib.request
from urllib.parse import urlparse


RELEASES_API = "https://api.github.com/repos/oriondd/Bulkrr/releases/latest"


def parse_version(version):
    if not isinstance(version, str):
        raise ValueError("Version must be text")
    value = version.removeprefix("v").split("-", 1)[0]
    parts = value.split(".")
    if len(parts) != 3 or any(not p.isdecimal() for p in parts):
        raise ValueError("Invalid semantic version")
    return tuple(map(int, parts))


def update_available(current, remote):
    return parse_version(remote) > parse_version(current)


def parse_release(payload):
    if not isinstance(payload, dict):
        raise ValueError("Invalid release metadata")
    tag = payload.get("tag_name")
    url = payload.get("html_url")
    if not isinstance(tag, str) or not isinstance(url, str):
        raise ValueError("Missing release metadata")
    parse_version(tag)
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "github.com" or parsed.username or parsed.password or parsed.port or parsed.query or parsed.fragment or not parsed.path.startswith("/oriondd/Bulkrr/releases/tag/"):
        raise ValueError("Untrusted release URL")
    return {"tag": tag, "url": url, "notes": str(payload.get("body") or "")[:3000]}


def fetch_latest_release(timeout=8):
    request = urllib.request.Request(RELEASES_API, headers={"Accept": "application/vnd.github+json", "User-Agent": "Bulkrr/2.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read(200_001)
        if len(data) > 200_000:
            raise ValueError("Release response too large")
    return parse_release(json.loads(data))
