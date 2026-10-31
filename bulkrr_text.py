"""Text formatting helpers for external media metadata."""

from html.parser import HTMLParser
import re


class _PlainTextParser(HTMLParser):
    """Convert harmless media description markup into readable plain text."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden_depth += 1
        elif not self.hidden_depth and tag in {"br", "p", "div", "li"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self.hidden_depth:
            self.hidden_depth -= 1
        elif not self.hidden_depth and tag in {"p", "div", "li"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden_depth:
            self.parts.append(data)


def clean_media_overview(value):
    """Render TMDB/AniList descriptions as safe, readable plain text."""
    from html import unescape

    source = unescape(str(value or "No synopsis available.")).strip()
    # Some metadata providers escape HTML twice. Normalize only known
    # formatting tags to avoid interpreting arbitrary escaped user text.
    source = re.sub(
        r"(?i)&lt;(/?(?:br|p|div|li))\\s*/?&gt;",
        lambda match: "<" + match.group(1) + ">",
        source,
    )
    parser = _PlainTextParser()
    parser.feed(source)
    parser.close()
    lines = [" ".join(line.split()) for line in "".join(parser.parts).splitlines()]
    return "\n".join(line for line in lines if line).strip() or "No synopsis available."
