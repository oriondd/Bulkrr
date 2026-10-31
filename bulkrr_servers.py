"""Multiple server profile validation and migration.

API keys are never serialized by this module. Callers should store secrets in
the operating-system keyring using each profile's stable identifier.
"""
import re
from urllib.parse import urlsplit

IDENTIFIER = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def validate_profiles(profiles):
    if not isinstance(profiles, list):
        raise ValueError("Profiles must be a list")
    seen = set()
    clean = []
    for item in profiles:
        if not isinstance(item, dict):
            raise ValueError("Invalid server profile")
        identifier = item.get("id")
        kind = item.get("kind")
        url = item.get("url")
        if not isinstance(identifier, str) or not IDENTIFIER.fullmatch(identifier):
            raise ValueError("Invalid profile ID")
        if identifier in seen:
            raise ValueError("Duplicate profile ID")
        if kind not in ("sonarr", "radarr"):
            raise ValueError("Invalid server kind")
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            raise ValueError("Invalid server URL")
        parsed = urlsplit(url)
        if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Server URL must contain a host and no credentials or query")
        if any(character in url for character in ("@", "\n", "\r", "\t")):
            raise ValueError("Credentials and control characters are not permitted in URLs")
        seen.add(identifier)
        clean.append({"id": identifier, "kind": kind, "url": url.rstrip("/"), "label": str(item.get("label") or identifier)[:80]})
    return clean


def legacy_profiles(settings):
    profiles = []
    for kind in ("radarr", "sonarr"):
        url = settings.get(kind + "_url")
        if url:
            profiles.append({"id": kind + "_default", "kind": kind, "url": url, "label": kind.title()})
    return validate_profiles(profiles)


def public_profiles(profiles):
    """Safe-to-save settings subset; reject unexpected embedded secrets."""
    return validate_profiles(profiles)
