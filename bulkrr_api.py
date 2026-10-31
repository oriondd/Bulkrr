"""Radarr/Sonarr HTTP client.

Only read-only GET requests are retried. Never automatically retry writes:
a timed-out POST may already have succeeded.
"""

import json
import time
import urllib.error
import urllib.request


def get_json(base, key, path, method="GET", payload=None):
    url = base.rstrip("/") + "/api/v3/" + path.lstrip("/")
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "X-Api-Key": key,
            "Content-Type": "application/json",
            "User-Agent": "Bulkrr/1.5",
        },
    )
    attempts = 3 if method.upper() == "GET" else 1
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                body = response.read(32 * 1024 * 1024 + 1)
                if len(body) > 32 * 1024 * 1024:
                    raise ValueError("Server response exceeds 32 MiB limit")
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as exc:
            retryable = exc.code in (429, 502, 503, 504)
            if retryable and attempt + 1 < attempts:
                time.sleep(0.5 * (attempt + 1))
                continue
            # Do not echo server response bodies: they may contain secrets.
            raise RuntimeError(
                f"{method.upper()} {path.split('?')[0]} failed: HTTP {exc.code}"
            ) from None
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt + 1 < attempts:
                time.sleep(0.5 * (attempt + 1))
                continue
            raise RuntimeError(
                f"{method.upper()} {path.split('?')[0]} failed: network or timeout error"
            ) from None
