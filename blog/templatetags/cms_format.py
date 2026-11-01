from django import template
from django.utils import timezone


register = template.Library()

MONTHS = {
    1: "янв.", 2: "февр.", 3: "марта", 4: "апр.", 5: "мая", 6: "июня",
    7: "июля", 8: "авг.", 9: "сент.", 10: "окт.", 11: "нояб.", 12: "дек.",
}


@register.filter
def cms_datetime(value):
    if not value:
        return "—"
    value = timezone.localtime(value) if timezone.is_aware(value) else value
    return f"{value.day} {MONTHS[value.month]} {value.year} · {value:%H:%M}"
