from django_filters import rest_framework as filters

from .constants import normalize_locale
from .models import Article


class ArticleFilter(filters.FilterSet):
    category = filters.CharFilter(method="filter_category")
    tag = filters.CharFilter(field_name="tags__slug")
    locale = filters.CharFilter(method="filter_locale")

    def filter_locale(self, queryset, name, value):
        return queryset.filter(locale=normalize_locale(value))

    def filter_category(self, queryset, name, value):
        if str(value).isdigit():
            return queryset.filter(category_id=value)
        locale = normalize_locale(self.request.query_params.get("locale") if self.request else None)
        return queryset.filter(**{f"category__slug_{locale}": value})

    class Meta:
        model = Article
        fields = ("locale", "category", "tag")
