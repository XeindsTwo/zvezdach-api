from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q
from django.db.models.signals import m2m_changed, post_delete, post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from .constants import ARTICLE_SLUG_MAX_LENGTH
from .image_processing import optimize_image
from .reading_time import calculate_reading_time
from .slugs import unique_slug


class Locale(models.TextChoices):
    EN = "en", "English"
    RU = "ru", "Russian"


class CmsLoginAttempt(models.Model):
    ip = models.GenericIPAddressField(db_index=True)
    username = models.CharField(max_length=150, blank=True)
    attempted_at = models.DateTimeField(auto_now_add=True, db_index=True)


class CmsAuditEvent(models.Model):
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)
    actor = models.CharField(max_length=150)
    ip = models.GenericIPAddressField()
    action = models.CharField(max_length=40)
    target = models.CharField(max_length=255, blank=True)


class Category(models.Model):
    name_ru = models.CharField(max_length=120)
    name_en = models.CharField(max_length=120)
    name_id = models.CharField(max_length=120, blank=True, default="")
    slug_ru = models.SlugField(max_length=140, unique=True)
    slug_en = models.SlugField(max_length=140, unique=True)
    slug_id = models.SlugField(max_length=140, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name_ru",)
        verbose_name_plural = "categories"

    def __str__(self) -> str:
        return f"{self.name_ru} / {self.name_en}"

    def name_for_locale(self, locale: str) -> str:
        return getattr(self, f"name_{locale}", self.name_en) or self.name_en

    def slug_for_locale(self, locale: str) -> str:
        return getattr(self, f"slug_{locale}", self.slug_en) or self.slug_en

    def save(self, *args, **kwargs):
        for locale in (Locale.RU, Locale.EN, "id"):
            slug_field = f"slug_{locale}"
            if not getattr(self, slug_field, ""):
                setattr(
                    self,
                    slug_field,
                    unique_slug(
                        Category,
                        getattr(self, f"name_{locale}"),
                        field=slug_field,
                        fallback=f"category-{locale}",
                        exclude_pk=self.pk,
                    ),
                )
        super().save(*args, **kwargs)


class Tag(models.Model):
    locale = models.CharField(max_length=2, choices=Locale.choices, default=Locale.EN, db_index=True)
    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("locale", "name")
        constraints = [
            models.UniqueConstraint(fields=("locale", "name"), name="unique_tag_name_per_locale"),
            models.UniqueConstraint(fields=("locale", "slug"), name="unique_tag_slug_per_locale"),
        ]

    def __str__(self) -> str:
        return f"[{self.locale.upper()}] {self.name}"


class PublishedArticleManager(models.Manager):
    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(
                status=Article.Status.PUBLISHED,
                editorial_status=Article.EditorialStatus.READY,
                published_at__lte=timezone.now(),
            )
        )


def article_cover_path(instance: "Article", filename: str) -> str:
    return f"blog/{instance.locale}/{instance.slug}/{filename}"


def article_gallery_path(instance: "ArticleGalleryImage", filename: str) -> str:
    return f"blog/{instance.article.locale}/{instance.article.slug}/gallery/{filename}"


class Article(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"

    class EditorialStatus(models.TextChoices):
        DRAFT = "draft", "Draft"
        READY = "ready", "Ready"

    locale = models.CharField(max_length=2, choices=Locale.choices, db_index=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="articles")
    tags = models.ManyToManyField(Tag, blank=True, related_name="articles")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="blog_articles",
    )
    title = models.CharField(max_length=220)
    slug = models.SlugField(max_length=ARTICLE_SLUG_MAX_LENGTH)
    excerpt = models.CharField(max_length=500)
    content = models.TextField(help_text="Article body. HTML or Markdown can be stored here.")
    cover_image = models.ImageField(upload_to=article_cover_path, blank=True)
    cover_image_avif = models.ImageField(upload_to=article_cover_path, blank=True, editable=False)
    cover_alt = models.CharField(max_length=220, blank=True)
    reading_time = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT, db_index=True)
    editorial_status = models.CharField(max_length=12, choices=EditorialStatus.choices, default=EditorialStatus.DRAFT, db_index=True)
    published_at = models.DateTimeField(blank=True, null=True, db_index=True)
    seo_title = models.CharField(max_length=70, blank=True)
    seo_description = models.CharField(max_length=170, blank=True)
    meta_keywords = models.CharField(max_length=300, blank=True)
    gallery_captions = models.JSONField(default=dict, blank=True)
    is_demo = models.BooleanField(default=False, editable=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = models.Manager()
    published = PublishedArticleManager()

    class Meta:
        ordering = ("-published_at", "-created_at")
        constraints = [
            models.UniqueConstraint(fields=("locale", "slug"), name="unique_article_slug_per_locale"),
            models.CheckConstraint(condition=Q(reading_time__gte=1), name="article_reading_time_positive"),
        ]
        indexes = [
            models.Index(fields=("locale", "status", "-published_at"), name="article_public_list_idx"),
        ]

    def __str__(self) -> str:
        return f"[{self.locale.upper()}] {self.title}"

    def clean(self):
        super().clean()
        if self.status == self.Status.PUBLISHED and not self.published_at:
            self.published_at = timezone.now()

    def save(self, *args, **kwargs):
        if self.status == self.Status.PUBLISHED and not self.published_at:
            self.published_at = timezone.now()
        self.reading_time = calculate_reading_time(self.content, self.locale)
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {"reading_time"}
        # The cover always describes the article itself. Keep this invariant at
        # the model layer so imports and future write APIs behave like the CMS.
        self.cover_alt = self.title
        if self.cover_image and not self.cover_image._committed:
            processed, avif = optimize_image(self.cover_image.file)
            self.cover_image.save(processed.name, processed, save=False)
            if avif:
                self.cover_image_avif.save(avif.name, avif, save=False)
            else:
                self.cover_image_avif = None
        super().save(*args, **kwargs)

    @property
    def localized_path(self) -> str:
        prefix = "/en" if self.locale == Locale.EN else ""
        return f"{prefix}/blog/{self.slug}"

    @property
    def public_url(self) -> str:
        return f"{settings.FRONTEND_URL}{self.localized_path}"

    @property
    def is_scheduled(self) -> bool:
        return bool(
            self.status == self.Status.PUBLISHED
            and self.published_at
            and self.published_at > timezone.now()
        )

    @property
    def category_name(self) -> str:
        return self.category.name_for_locale(self.locale)


class ArticleGalleryImage(models.Model):
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name="gallery")
    gallery_number = models.PositiveSmallIntegerField(default=1)
    image = models.ImageField(upload_to=article_gallery_path)
    image_avif = models.ImageField(upload_to=article_gallery_path, blank=True, editable=False)
    alt = models.CharField(max_length=220, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("gallery_number", "sort_order", "pk")
        constraints = [
            models.CheckConstraint(condition=Q(gallery_number__gte=1), name="gallery_number_positive"),
        ]

    def save(self, *args, **kwargs):
        if self.image and not self.image._committed:
            processed, avif = optimize_image(self.image.file)
            self.image.save(processed.name, processed, save=False)
            if avif:
                self.image_avif.save(avif.name, avif, save=False)
            else:
                self.image_avif = None
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.article.title} — gallery {self.gallery_number}, image {self.sort_order + 1}"


def delete_stored_files(*fields):
    for field in fields:
        if field and field.name:
            field.storage.delete(field.name)


def clear_public_blog_cache(*args, **kwargs):
    transaction.on_commit(cache.clear)


post_save.connect(clear_public_blog_cache, sender=Article, dispatch_uid="blog_cache_article_save")
post_delete.connect(clear_public_blog_cache, sender=Article, dispatch_uid="blog_cache_article_delete")
post_save.connect(clear_public_blog_cache, sender=ArticleGalleryImage, dispatch_uid="blog_cache_gallery_save")
post_delete.connect(clear_public_blog_cache, sender=ArticleGalleryImage, dispatch_uid="blog_cache_gallery_delete")
post_save.connect(clear_public_blog_cache, sender=Category, dispatch_uid="blog_cache_category_save")
post_delete.connect(clear_public_blog_cache, sender=Category, dispatch_uid="blog_cache_category_delete")
post_save.connect(clear_public_blog_cache, sender=Tag, dispatch_uid="blog_cache_tag_save")
post_delete.connect(clear_public_blog_cache, sender=Tag, dispatch_uid="blog_cache_tag_delete")
m2m_changed.connect(clear_public_blog_cache, sender=Article.tags.through, dispatch_uid="blog_cache_article_tags")


@receiver(m2m_changed, sender=Article.tags.through)
def validate_article_tag_locale(sender, instance, action, pk_set, reverse, **kwargs):
    if action != "pre_add" or not pk_set:
        return
    if reverse:
        has_foreign_locale = Article.objects.filter(pk__in=pk_set).exclude(locale=instance.locale).exists()
    else:
        has_foreign_locale = Tag.objects.filter(pk__in=pk_set).exclude(locale=instance.locale).exists()
    if has_foreign_locale:
        raise ValidationError("Теги должны относиться к языку статьи")


@receiver(pre_save, sender=Article)
def cleanup_replaced_cover(sender, instance, **kwargs):
    if not instance.pk:
        return
    previous = sender.objects.filter(pk=instance.pk).only("cover_image", "cover_image_avif").first()
    if previous and previous.cover_image.name != instance.cover_image.name:
        transaction.on_commit(lambda: delete_stored_files(previous.cover_image, previous.cover_image_avif))


@receiver(post_delete, sender=Article)
def cleanup_deleted_cover(sender, instance, **kwargs):
    transaction.on_commit(lambda: delete_stored_files(instance.cover_image, instance.cover_image_avif))


@receiver(pre_save, sender=ArticleGalleryImage)
def cleanup_replaced_gallery_image(sender, instance, **kwargs):
    if not instance.pk:
        return
    previous = sender.objects.filter(pk=instance.pk).only("image", "image_avif").first()
    if previous and previous.image.name != instance.image.name:
        transaction.on_commit(lambda: delete_stored_files(previous.image, previous.image_avif))


@receiver(post_delete, sender=ArticleGalleryImage)
def cleanup_deleted_gallery_image(sender, instance, **kwargs):
    transaction.on_commit(lambda: delete_stored_files(instance.image, instance.image_avif))
