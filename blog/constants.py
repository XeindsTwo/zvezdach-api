VALID_LOCALES = ("ru", "en", "id")
DEFAULT_LOCALE = "en"
ARTICLE_SLUG_MAX_LENGTH = 220


def normalize_locale(value: str | None) -> str:
    return value if value in VALID_LOCALES else DEFAULT_LOCALE
