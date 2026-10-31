"""Text formatting helpers for external media metadata."""

import html
import re


def clean_media_overview(value):
    """Render TMDB/AniList descriptions as safe, readable plain text."""
    overview = html.unescape(str(value or "No synopsis available.")).strip()
    overview = re.sub(r"(?i)<br\s*/?>", "\n", overview)
    overview = re.sub(r"(?i)</p\s*>", "\n", overview)
    overview = re.sub(r"<[^>]+>", "", overview)
    return overview.strip()
