import re

from django.utils.text import slugify


CYRILLIC_SLUG_MAP = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh",
    "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p",
    "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch",
    "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
})


def readable_slug(value, *, fallback="item", max_length=140):
    transliterated = str(value or "").strip().lower().translate(CYRILLIC_SLUG_MAP)
    normalized = re.sub(r"-+", "-", slugify(transliterated)).strip("-")
    return (normalized or fallback)[:max_length].rstrip("-")


def unique_slug(model, value, *, field="slug", fallback="item", max_length=140, exclude_pk=None):
    base = readable_slug(value, fallback=fallback, max_length=max_length)
    candidate = base
    index = 2
    queryset = model.objects.all()
    if exclude_pk:
        queryset = queryset.exclude(pk=exclude_pk)
    while queryset.filter(**{field: candidate}).exists():
        suffix = f"-{index}"
        candidate = f"{base[:max_length - len(suffix)].rstrip('-')}{suffix}"
        index += 1
    return candidate
