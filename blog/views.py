from django.http import JsonResponse
from django.conf import settings
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .filters import ArticleFilter
from .constants import normalize_locale
from .models import Article, Category, Tag
from .serializers import ArticleDetailSerializer, ArticleListSerializer, CategorySerializer, TagSerializer


def health(request):
    return JsonResponse({"status": "ok", "service": "chatus-api"})


@method_decorator(cache_page(settings.BLOG_API_CACHE_SECONDS), name="dispatch")
class ArticleViewSet(viewsets.ReadOnlyModelViewSet):
    filterset_class = ArticleFilter
    lookup_field = "slug"
    ordering_fields = ("published_at", "created_at")
    ordering = ("-published_at",)
    search_fields = ("title", "excerpt")

    def get_queryset(self):
        locale = normalize_locale(self.request.query_params.get("locale"))
        return Article.published.select_related("category", "author").prefetch_related("tags", "gallery").filter(locale=locale)

    def get_serializer_class(self):
        return ArticleDetailSerializer if self.action == "retrieve" else ArticleListSerializer

    @action(detail=True, methods=("get",))
    def related(self, request, *args, **kwargs):
        article = self.get_object()
        queryset = (
            Article.published
            .select_related("category", "author")
            .prefetch_related("tags")
            .filter(locale=article.locale)
            .exclude(pk=article.pk)
        )
        tag_ids = list(article.tags.values_list("pk", flat=True))
        related = list(queryset.filter(tags__in=tag_ids).distinct().order_by("?")[:12]) if tag_ids else []
        if len(related) < 12:
            excluded_ids = [item.pk for item in related]
            related.extend(list(queryset.exclude(pk__in=excluded_ids).order_by("?")[:12 - len(related)]))
        return Response(ArticleListSerializer(related, many=True, context=self.get_serializer_context()).data)


@method_decorator(cache_page(settings.BLOG_API_CACHE_SECONDS), name="dispatch")
class CategoryViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = CategorySerializer
    pagination_class = None

    def get_queryset(self):
        locale = normalize_locale(self.request.query_params.get("locale"))
        public_articles = Article.published.filter(locale=locale)
        return Category.objects.filter(is_active=True, articles__in=public_articles).distinct()


@method_decorator(cache_page(settings.BLOG_API_CACHE_SECONDS), name="dispatch")
class TagViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = TagSerializer
    pagination_class = None

    def get_queryset(self):
        queryset = Tag.objects.all()
        return queryset.filter(locale=normalize_locale(self.request.query_params.get("locale")))
