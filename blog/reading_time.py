import math
import re
from html import unescape

WORDS_PER_MINUTE = {
    "ru": 180,
    "en": 200,
    "id": 200,
}

GALLERY_MARKER_RE = re.compile(r"\[\[gallery\d*\]\]", re.IGNORECASE)
HTML_TAG_RE = re.compile(r"<[^>]+>", re.DOTALL)
WORD_RE = re.compile(r"[^\W_]+(?:[’'\-][^\W_]+)*", re.UNICODE)


def calculate_reading_time(content: str, locale: str) -> int:
    """Return an integer reading estimate for TinyMCE HTML content."""
    # Replace tags with spaces instead of simply deleting them: TinyMCE often
    # stores adjacent block tags, and their boundary must not join two words.
    plain_text = unescape(HTML_TAG_RE.sub(" ", content or ""))
    plain_text = GALLERY_MARKER_RE.sub(" ", plain_text)
    word_count = len(WORD_RE.findall(plain_text))
    words_per_minute = WORDS_PER_MINUTE.get(locale, WORDS_PER_MINUTE["en"])
    return max(1, math.ceil(word_count / words_per_minute))
