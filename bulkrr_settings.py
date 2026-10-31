"""Atomic, credential-free JSON preferences persistence for Bulkrr."""
import json
import os
import tempfile
from pathlib import Path


def write_settings(path, settings):
    """Write preferences atomically; never serialize API keys or secrets."""
    if not isinstance(settings, dict):
        raise ValueError("Settings must be a JSON object")
    forbidden = {"api_key", "apikey", "password", "secret", "token"}
    def validate(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if not isinstance(key, str):
                    raise ValueError("Settings keys must be text")
                normalized = key.casefold().replace("-", "_")
                if (normalized in forbidden or normalized.endswith(("_api_key", "_apikey", "_password", "_secret", "_token"))):
                    raise ValueError("Credentials cannot be written to settings")
                validate(item)
        elif isinstance(value, list):
            for item in value:
                validate(item)
    validate(settings)
    encoded = json.dumps(settings, indent=2, ensure_ascii=False, allow_nan=False)
    if len(encoded.encode("utf-8")) > 1024 * 1024:
        raise ValueError("Settings exceed the size limit")
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=destination.parent,
            prefix=".bulkrr-settings-", suffix=".tmp", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            if os.name != "nt":
                os.chmod(temporary, 0o600)
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
