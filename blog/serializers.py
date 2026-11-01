from rest_framework import serializers

from django.conf import settings

from .models import Article, ArticleGalleryImage, Category, Tag
from .constants import normalize_locale


def absolute_file_url(serializer, field):
    if not field:
        return None
    request = serializer.context.get("request")
    return request.build_absolute_uri(field.url) if request else field.url


class CategorySerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    slug = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ("id", "name", "slug", "name_ru", "name_en", "name_id", "slug_ru", "slug_en", "slug_id")

    def get_name(self, category):
        request = self.context.get("request")
        locale = normalize_locale(request.query_params.get("locale") if request else None)
        return category.name_for_locale(locale)

    def get_slug(self, category):
        request = self.context.get("request")
        locale = normalize_locale(request.query_params.get("locale") if request else None)
        return category.slug_for_locale(locale)


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ("id", "name", "slug", "locale")


class GalleryImageSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()
    image_avif = serializers.SerializerMethodField()

    class Meta:
        model = ArticleGalleryImage
        fields = ("id", "image", "image_avif", "alt", "gallery_number", "sort_order")

    def get_image(self, item):
        return absolute_file_url(self, item.image)

    def get_image_avif(self, item):
        return absolute_file_url(self, item.image_avif)


class ArticleListSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    cover_image = serializers.SerializerMethodField()
    cover_image_avif = serializers.SerializerMethodField()
    image_alt = serializers.CharField(source="cover_alt", read_only=True)
    url = serializers.SerializerMethodField()

    class Meta:
        model = Article
        fields = (
            "id",
            "slug",
            "title",
            "excerpt",
            "locale",
            "category",
            "tags",
            "published_at",
            "reading_time",
            "cover_image",
            "cover_image_avif",
            "image_alt",
            "url",
        )

    def get_cover_image(self, article: Article):
        return absolute_file_url(self, article.cover_image)

    def get_cover_image_avif(self, article: Article):
        return absolute_file_url(self, article.cover_image_avif)

    def get_url(self, article: Article):
        return f"{settings.FRONTEND_URL}{article.localized_path}"

class ArticleDetailSerializer(ArticleListSerializer):
    gallery = GalleryImageSerializer(many=True, read_only=True)

    class Meta(ArticleListSerializer.Meta):
        fields = ArticleListSerializer.Meta.fields + (
            "content",
            "seo_title",
            "seo_description",
            "meta_keywords",
            "updated_at",
            "gallery",
            "gallery_captions",
        )
