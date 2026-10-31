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


def route_to_profiles(profiles, assignments):
    """Resolve explicitly selected server destinations without network writes.

    assignments maps a unique item ID to a profile ID and required server kind.
    No default destination is inferred: every item must have an explicit route.
    """
    validated = validate_profiles(profiles)
    by_id = {profile["id"]: profile for profile in validated}
    if not isinstance(assignments, list) or len(assignments) > 500:
        raise ValueError("Expected at most 500 explicit routing assignments")
    grouped = {}
    seen = set()
    for item in assignments:
        if not isinstance(item, dict):
            raise ValueError("Invalid routing assignment")
        item_id = item.get("item_id")
        profile_id = item.get("profile_id")
        kind = item.get("kind")
        if type(item_id) is not int or item_id <= 0 or item_id in seen:
            raise ValueError("Item IDs must be unique positive integers")
        if not isinstance(profile_id, str) or profile_id not in by_id:
            raise ValueError("An explicit known destination profile is required")
        if kind not in ("radarr", "sonarr") or by_id[profile_id]["kind"] != kind:
            raise ValueError("Destination profile does not match the item kind")
        seen.add(item_id)
        grouped.setdefault(profile_id, {"profile": dict(by_id[profile_id]), "item_ids": []})["item_ids"].append(item_id)
    return list(grouped.values())


def check_routed_libraries(routes, fetch_library):
    """Read-only multi-server inventory check, isolated by destination profile.

    fetch_library(profile) must return that profile's movie/series API records.
    Failures are reported per destination; they never fall back to another server.
    """
    if not isinstance(routes, list) or len(routes) > 500 or not callable(fetch_library):
        raise ValueError("Invalid routing checks")
    results = []
    seen = set()
    assigned_items = set()
    for route in routes:
        if not isinstance(route, dict) or not isinstance(route.get("profile"), dict):
            raise ValueError("Invalid routing group")
        profile = validate_profiles([route["profile"]])[0]
        identifier = profile["id"]
        if identifier in seen:
            raise ValueError("Duplicate routing destination")
        seen.add(identifier)
        ids = route.get("item_ids")
        if (not isinstance(ids, list) or not ids or len(ids) > 500
                or any(type(item) is not int or item <= 0 for item in ids)
                or len(ids) != len(set(ids))):
            raise ValueError("Invalid routed item IDs")
        if assigned_items.intersection(ids):
            raise ValueError("A title cannot be assigned to multiple destinations")
        assigned_items.update(ids)
        if len(assigned_items) > 500:
            raise ValueError("Routing checks are limited to 500 titles")
        try:
            records = fetch_library(profile)
            if not isinstance(records, list):
                raise ValueError("Invalid library response")
            results.append({"profile_id": identifier, "item_ids": list(ids),
                            "library_count": len(records), "error": None})
        except Exception as exc:
            results.append({"profile_id": identifier, "item_ids": list(ids),
                            "library_count": None, "error": str(exc)})
    return results
