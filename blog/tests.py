import io
import os
import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import models
from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from PIL import Image

from .models import Article, ArticleGalleryImage, Category, Tag
from .image_processing import MAX_GIF_UPLOAD_SIZE, MAX_IMAGE_DIMENSION, optimize_image, validate_image_upload
from .reading_time import calculate_reading_time
from .templatetags.cms_format import cms_datetime


class CmsSecurityTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="cms-security", password="correct-password", is_staff=True)

    def test_login_limit_and_audit(self):
        from .models import CmsAuditEvent, CmsLoginAttempt

        url = reverse("cms:login")
        for _ in range(5):
            self.client.post(url, {"username": self.user.username, "password": "wrong"}, REMOTE_ADDR="192.0.2.10")
        self.assertEqual(CmsLoginAttempt.objects.filter(ip="192.0.2.10").count(), 5)
        response = self.client.post(url, {"username": self.user.username, "password": "correct-password"}, REMOTE_ADDR="192.0.2.10")
        self.assertEqual(response.status_code, 429)
        response = self.client.post(url, {"username": self.user.username, "password": "correct-password"}, REMOTE_ADDR="192.0.2.11")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(CmsAuditEvent.objects.filter(actor=self.user.username, ip="192.0.2.11", action="login").exists())

    def test_untrusted_forwarded_ip_is_ignored(self):
        from django.test import RequestFactory
        from .cms_views import cms_ip

        request = RequestFactory().get("/cms/login/", REMOTE_ADDR="192.0.2.10", HTTP_X_FORWARDED_FOR="198.51.100.20")
        self.assertEqual(cms_ip(request), "192.0.2.10")


def test_image(name="source.png", color=(255, 174, 25)):
    buffer = io.BytesIO()
    Image.new("RGB", (48, 32), color).save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


def test_image_format(name, image_format, size=(100, 100)):
    buffer = io.BytesIO()
    Image.new("RGB", size, (255, 174, 25)).save(buffer, format=image_format)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/bmp")


def test_gif(name="animation.gif"):
    buffer = io.BytesIO()
    first = Image.new("RGB", (24, 24), (255, 174, 25))
    second = Image.new("RGB", (24, 24), (42, 27, 0))
    first.save(buffer, format="GIF", save_all=True, append_images=[second], duration=100, loop=0)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/gif")


class PublicBlogApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.author = get_user_model().objects.create_user(username="author", password="test-password")
        self.category = Category.objects.create(name_ru="Психология", name_en="Psychology", name_id="Psikologi")

    def create_article(self, *, slug: str, status: str, published_at=None, locale="ru"):
        return Article.objects.create(
            locale=locale,
            category=self.category,
            author=self.author,
            title=f"Article {slug}",
            slug=slug,
            excerpt="Short description",
            content="Article body",
            status=status,
            editorial_status=Article.EditorialStatus.READY,
            published_at=published_at,
            reading_time=7,
        )

    def test_health_endpoint(self):
        response = self.client.get(reverse("health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_article_list_exposes_only_currently_published_articles(self):
        visible = self.create_article(
            slug="visible",
            status=Article.Status.PUBLISHED,
            published_at=timezone.now() - timedelta(minutes=1),
        )
        self.create_article(slug="draft", status=Article.Status.DRAFT)
        self.create_article(
            slug="future",
            status=Article.Status.PUBLISHED,
            published_at=timezone.now() + timedelta(days=1),
        )

        response = self.client.get(reverse("article-list"), {"locale": "ru"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(response.json()["results"][0]["slug"], visible.slug)

    def test_public_article_cache_is_cleared_after_article_update(self):
        article = self.create_article(
            slug="cached",
            status=Article.Status.PUBLISHED,
            published_at=timezone.now() - timedelta(minutes=1),
        )
        url = reverse("article-detail", kwargs={"slug": article.slug})

        first = self.client.get(url, {"locale": "ru"})
        self.assertEqual(first.status_code, 200)
        self.assertIn("max-age=", first.headers.get("Cache-Control", ""))

        with self.captureOnCommitCallbacks(execute=True):
            article.title = "Updated cached title"
            article.save()

        second = self.client.get(url, {"locale": "ru"})
        self.assertEqual(second.json()["title"], "Updated cached title")

    def test_article_list_filters_by_category(self):
        self.create_article(
            slug="psychology-article",
            status=Article.Status.PUBLISHED,
            published_at=timezone.now(),
        )
        other = Category.objects.create(name_ru="Обновления", name_en="Updates", name_id="Pembaruan")
        Article.objects.create(
            locale="ru",
            category=other,
            author=self.author,
            title="Update",
            slug="update",
            excerpt="Update excerpt",
            content="Update body",
            status=Article.Status.PUBLISHED,
            published_at=timezone.now(),
        )

        response = self.client.get(reverse("article-list"), {"locale": "ru", "category": self.category.pk})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(response.json()["results"][0]["category"]["id"], self.category.pk)
        self.assertEqual(response.json()["results"][0]["category"]["name"], "Психология")

    def test_article_list_filters_by_localized_category_slug(self):
        self.create_article(
            slug="psychology-by-slug",
            status=Article.Status.PUBLISHED,
            published_at=timezone.now(),
        )
        response = self.client.get(
            reverse("article-list"),
            {"locale": "ru", "category": self.category.slug_ru},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(response.json()["results"][0]["slug"], "psychology-by-slug")

    def test_category_api_returns_name_for_requested_language(self):
        self.create_article(
            slug="category-visible",
            status=Article.Status.PUBLISHED,
            published_at=timezone.now(),
            locale="id",
        )
        response = self.client.get(reverse("category-list"), {"locale": "id"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["name"], "Psikologi")
        self.assertEqual(response.json()[0]["slug"], "psikologi")
        self.assertEqual(response.json()[0]["name_ru"], "Психология")
        self.assertEqual(response.json()[0]["slug_ru"], "psihologiya")

    def test_public_api_hides_editorial_drafts_and_their_empty_categories(self):
        hidden_category = Category.objects.create(name_ru="Скрытая", name_en="Hidden", name_id="Tersembunyi")
        Article.objects.create(
            locale="ru",
            category=hidden_category,
            author=self.author,
            title="Редакционный черновик",
            slug="editorial-draft",
            excerpt="Черновик",
            content="<p>Ещё не готово</p>",
            status=Article.Status.PUBLISHED,
            editorial_status=Article.EditorialStatus.DRAFT,
            published_at=timezone.now(),
        )

        detail = self.client.get(reverse("article-detail", kwargs={"slug": "editorial-draft"}), {"locale": "ru"})
        listing = self.client.get(reverse("article-list"), {"locale": "ru"})
        categories = self.client.get(reverse("category-list"), {"locale": "ru"})

        self.assertEqual(detail.status_code, 404)
        self.assertEqual(listing.json()["count"], 0)
        self.assertNotIn(hidden_category.pk, {item["id"] for item in categories.json()})

    def test_categories_generate_unique_localized_slugs(self):
        duplicate = Category.objects.create(name_ru="Психология", name_en="Psychology", name_id="Psikologi")
        self.assertEqual(self.category.slug_ru, "psihologiya")
        self.assertEqual(duplicate.slug_ru, "psihologiya-2")
        self.assertEqual(duplicate.slug_en, "psychology-2")
        self.assertEqual(duplicate.slug_id, "psikologi-2")

    def test_related_articles_prioritize_shared_tags_fill_to_twelve_and_keep_locale(self):
        source = self.create_article(
            slug="source",
            status=Article.Status.PUBLISHED,
            published_at=timezone.now(),
        )
        shared_tag = Tag.objects.create(locale="ru", name="Общение", slug="obschenie")
        source.tags.add(shared_tag)
        related_slugs = set()
        for index in range(5):
            item = self.create_article(
                slug=f"related-{index}",
                status=Article.Status.PUBLISHED,
                published_at=timezone.now(),
            )
            item.tags.add(shared_tag)
            related_slugs.add(item.slug)
        for index in range(10):
            self.create_article(
                slug=f"fallback-{index}",
                status=Article.Status.PUBLISHED,
                published_at=timezone.now(),
            )
        Article.objects.create(
            locale="en", category=self.category, author=self.author, title="Wrong locale", slug="wrong-locale",
            excerpt="English", content="English", status=Article.Status.PUBLISHED, published_at=timezone.now(),
        )

        response = self.client.get(reverse("article-related", kwargs={"slug": source.slug}), {"locale": "ru"})
        payload = response.json()
        returned_slugs = {item["slug"] for item in payload}

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(payload), 12)
        self.assertTrue(related_slugs.issubset(returned_slugs))
        self.assertNotIn(source.slug, returned_slugs)
        self.assertNotIn("wrong-locale", returned_slugs)

    def test_draft_article_detail_is_not_public(self):
        self.create_article(slug="private-draft", status=Article.Status.DRAFT)
        response = self.client.get(reverse("article-detail", kwargs={"slug": "private-draft"}))
        self.assertEqual(response.status_code, 404)

    def test_api_uses_en_for_missing_or_invalid_locale_without_mixing_articles(self):
        english = Article.objects.create(
            locale="en", category=self.category, author=self.author, title="English", slug="same-slug",
            excerpt="English", content="<p>English</p>", status=Article.Status.PUBLISHED,
            editorial_status=Article.EditorialStatus.READY, published_at=timezone.now(),
        )
        Article.objects.create(
            locale="ru", category=self.category, author=self.author, title="Русская", slug="same-slug",
            excerpt="Русская", content="<p>Русская</p>", status=Article.Status.PUBLISHED,
            editorial_status=Article.EditorialStatus.READY, published_at=timezone.now(),
        )
        list_response = self.client.get(reverse("article-list"))
        invalid_response = self.client.get(reverse("article-list"), {"locale": "de"})
        detail_response = self.client.get(reverse("article-detail", kwargs={"slug": "same-slug"}), {"locale": "unknown"})
        self.assertTrue(all(item["locale"] == "en" for item in list_response.json()["results"]))
        self.assertTrue(all(item["locale"] == "en" for item in invalid_response.json()["results"]))
        self.assertEqual(detail_response.json()["id"], english.pk)


class CustomCmsTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp(prefix="chatus-test-media-")
        self.media_override = override_settings(MEDIA_ROOT=self.media_root)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        self.addCleanup(shutil.rmtree, self.media_root, True)
        self.category = Category.objects.create(name_ru="Общение", name_en="Communication", name_id="Komunikasi")
        self.user = get_user_model().objects.create_user(username="content", password="test-password", is_staff=True)

    def article_payload(self, **overrides):
        payload = {
            "locale": "ru",
            "category": self.category.pk,
            "title": "Как начать разговор",
            "slug": "",
            "excerpt": "Короткое описание",
            "content": "<h2 class=\"accent\">" + "полезное слово " * 410 + "</h2>",
            "status": Article.Status.PUBLISHED,
            "editorial_status": Article.EditorialStatus.DRAFT,
            "published_at": timezone.localdate().strftime("%Y-%m-%d"),
            "seo_title": "SEO title",
            "seo_description": "SEO description",
            "meta_keywords": "общение, знакомства",
            "cover_alt": "Люди общаются",
            "cover_image": test_image("default-cover.png"),
            "reading_time": "5",
            "tags_input": '["Психология", "Знакомства"]',
            "gallery-TOTAL_FORMS": "0",
            "gallery-INITIAL_FORMS": "0",
            "gallery-MIN_NUM_FORMS": "0",
            "gallery-MAX_NUM_FORMS": "50",
        }
        payload.update(overrides)
        return payload

    def test_cms_requires_login(self):
        response = self.client.get(reverse("cms:dashboard"))
        self.assertRedirects(response, f"{reverse('cms:login')}?next={reverse('cms:dashboard')}")

    def test_regular_authenticated_user_cannot_access_cms(self):
        regular_user = get_user_model().objects.create_user(username="regular", password="test-password")
        article = Article.objects.create(
            locale="ru", category=self.category, author=self.user, title="Article", slug="article",
            excerpt="Excerpt", content="Content",
        )
        self.client.force_login(regular_user)
        self.assertEqual(self.client.get(reverse("cms:article-list")).status_code, 404)
        self.assertEqual(self.client.post(reverse("cms:article-create"), self.article_payload()).status_code, 404)
        self.assertEqual(self.client.post(reverse("cms:article-edit", kwargs={"pk": article.pk}), self.article_payload()).status_code, 404)
        self.assertEqual(self.client.post(reverse("cms:article-delete", kwargs={"pk": article.pk})).status_code, 404)

    def test_cms_home_opens_article_management(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("cms:dashboard"))
        self.assertRedirects(response, reverse("cms:article-list"))

    def test_ajax_login_returns_json_without_rendering_a_new_page(self):
        ajax = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest", "HTTP_ACCEPT": "application/json"}
        invalid = self.client.post(reverse("cms:login"), {"username": "content", "password": "wrong"}, **ajax)
        self.assertEqual(invalid.status_code, 422)
        self.assertFalse(invalid.json()["ok"])

        valid = self.client.post(reverse("cms:login"), {"username": "content", "password": "test-password"}, **ajax)
        self.assertEqual(valid.status_code, 200)
        self.assertTrue(valid.json()["ok"])
        self.assertEqual(valid.json()["redirect"], reverse("cms:article-list"))

    def test_login_screen_uses_fetch_enhancement(self):
        response = self.client.get(reverse("cms:login"))
        self.assertContains(response, 'id="login-form"')
        self.assertContains(response, "cms/js/login.js")
        self.assertContains(response, "Авторизация")

    def test_category_management_uses_single_page_modal(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("cms:category-list"))
        self.assertContains(response, 'id="category-modal"')
        self.assertContains(response, "Добавить категорию")
        self.assertContains(response, "Название на английском")
        self.assertContains(response, 'placeholder="Например: Safety"')
        self.assertContains(response, "cms/images/zvezdach-logo.svg")
        self.assertNotContains(response, "data-category-search")
        self.assertNotContains(response, "Короткий адрес")
        self.assertNotContains(response, "RU · EN · ID")
        self.assertNotContains(response, "hover:-translate-y-0.5")
        self.assertNotContains(response, "Структура блога")

    def test_category_can_be_created_and_updated_without_page_reload(self):
        self.client.force_login(self.user)
        ajax = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest", "HTTP_ACCEPT": "application/json"}
        created = self.client.post(
            reverse("cms:category-create"),
            {"name_ru": "Безопасность", "name_en": "Safety", "name_id": "Keamanan", "is_active": "on"},
            **ajax,
        )
        self.assertEqual(created.status_code, 200)
        self.assertTrue(created.json()["created"])
        category = Category.objects.get(name_en="Safety")
        updated = self.client.post(
            reverse("cms:category-edit", kwargs={"pk": category.pk}),
            {"name_ru": "Безопасность", "name_en": "Safety and privacy", "name_id": "Keamanan"},
            **ajax,
        )
        self.assertEqual(updated.status_code, 200)
        self.assertFalse(updated.json()["created"])
        category.refresh_from_db()
        self.assertEqual(category.name_en, "Safety and privacy")
        self.assertFalse(category.is_active)

    def test_logged_in_user_can_publish_with_tags_and_automatic_reading_time(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("cms:article-create"), self.article_payload())

        article = Article.objects.get(slug="kak-nachat-razgovor")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(article.author, self.user)
        self.assertEqual(article.status, Article.Status.PUBLISHED)
        self.assertEqual(article.reading_time, 5)
        self.assertEqual(article.cover_alt, article.title)
        self.assertSetEqual(set(article.tags.values_list("name", flat=True)), {"Психология", "Знакомства"})
        self.assertSetEqual(set(article.tags.values_list("locale", flat=True)), {"ru"})

    def test_reading_time_is_calculated_from_content_instead_of_cms_value(self):
        self.client.force_login(self.user)
        self.client.post(reverse("cms:article-create"), self.article_payload(reading_time="12"))
        self.assertEqual(Article.objects.get(slug="kak-nachat-razgovor").reading_time, 5)

    def test_reading_time_uses_locale_speed_and_ignores_html_and_gallery_markers(self):
        content = "<h3>Заголовок</h3><p>" + "слово " * 179 + "</p><p>[[gallery1]]</p>"
        self.assertEqual(calculate_reading_time(content, "ru"), 1)
        self.assertEqual(calculate_reading_time(content + " ещё", "ru"), 2)
        self.assertEqual(calculate_reading_time("<p>word </p>" * 201, "en"), 2)
        self.assertEqual(calculate_reading_time("", "id"), 1)

    def test_explicit_save_action_creates_a_draft_even_with_tampered_status(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("cms:article-create"),
            self.article_payload(action="save", status=Article.Status.PUBLISHED, cover_image="", cover_alt="", seo_title="", seo_description="", published_at=""),
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Article.objects.filter(status=Article.Status.DRAFT).exists())

    def test_explicit_publish_action_publishes_and_defaults_to_today(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("cms:article-create"),
            self.article_payload(action="publish", status=Article.Status.DRAFT, published_at=""),
        )
        self.assertEqual(response.status_code, 302)
        article = Article.objects.get()
        self.assertEqual(article.status, Article.Status.PUBLISHED)
        self.assertEqual(article.editorial_status, Article.EditorialStatus.READY)
        self.assertIsNotNone(article.published_at)

    def test_article_can_be_marked_ready_without_being_published(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("cms:article-create"),
            self.article_payload(
                action="save",
                editorial_status=Article.EditorialStatus.READY,
                cover_image="",
                seo_title="",
                seo_description="",
                published_at="",
            ),
        )
        article = Article.objects.get()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(article.status, Article.Status.DRAFT)
        self.assertEqual(article.editorial_status, Article.EditorialStatus.READY)

    def test_save_changes_keeps_an_existing_article_published(self):
        self.client.force_login(self.user)
        self.client.post(reverse("cms:article-create"), self.article_payload(action="publish"))
        article = Article.objects.get()
        response = self.client.post(
            reverse("cms:article-edit", kwargs={"pk": article.pk}),
            self.article_payload(action="save", status=Article.Status.DRAFT, title="Обновлённый заголовок"),
        )
        self.assertEqual(response.status_code, 302)
        article.refresh_from_db()
        self.assertEqual(article.status, Article.Status.PUBLISHED)
        self.assertEqual(article.title, "Обновлённый заголовок")

    def test_article_slug_is_generated_from_title_and_made_unique(self):
        self.client.force_login(self.user)
        first = self.client.post(reverse("cms:article-create"), self.article_payload(slug=""))
        second = self.client.post(reverse("cms:article-create"), self.article_payload(slug=""))

        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        self.assertSetEqual(
            set(Article.objects.values_list("slug", flat=True)),
            {"kak-nachat-razgovor", "kak-nachat-razgovor-2"},
        )

    def test_article_slug_can_be_edited_manually(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("cms:article-create"),
            self.article_payload(slug="moi-osobyi-adres"),
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Article.objects.filter(locale="ru", slug="moi-osobyi-adres").exists())

    def test_article_editor_exposes_productive_editing_tools(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("cms:article-create"))
        self.assertContains(response, 'id="readiness-panel"')
        self.assertContains(response, 'id="cover-preview"')
        self.assertContains(response, "800 × 495 px")
        self.assertContains(response, "до 2 МБ")
        self.assertContains(response, "image/avif,image/gif")
        self.assertContains(response, 'size-[22px]', count=6)
        self.assertContains(response, 'data-date-picker="true"')
        self.assertContains(response, 'data-counter-for="id_seo_title"')
        self.assertContains(response, 'data-custom-select="true"')
        self.assertContains(response, 'placeholder="Например: Как начать разговор с незнакомцем"')
        self.assertContains(response, "min-h-[200px] max-h-[300px]")
        self.assertContains(response, 'value="save"')
        self.assertContains(response, 'value="publish"')
        self.assertContains(response, "Опубликовать")
        self.assertNotContains(response, 'name="content" cols="40" rows="24" data-editor="tinymce" placeholder="Начните писать статью…" required')
        self.assertContains(response, "Адрес статьи")
        self.assertContains(response, "Заполняется из заголовка автоматически")
        self.assertNotContains(response, "Автоматически создадим версии WebP")
        self.assertNotContains(response, "Панель управления")
        self.assertNotContains(response, 'id="save-status"')
        self.assertNotContains(response, 'id="article-preview-panel"')
        self.assertEqual(response.context["form"]["cover_image"].field.widget.input_type, "file")
        self.assertEqual(response.context["form"]["cover_alt"].field.widget.__class__.__name__, "HiddenInput")
        self.assertContains(response, "Alt обложки автоматически повторяет заголовок статьи")
        self.assertContains(response, "Категория и теги")
        self.assertContains(response, 'placeholder="Введите тег"')
        self.assertContains(response, "Введите минимум 3 символа")

    def test_article_list_has_compact_filters_without_statistics(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("cms:article-list"))
        self.assertContains(response, 'data-custom-select="true"', count=3)
        self.assertContains(response, 'name="editorial_status"')
        self.assertContains(response, "Любая готовность")
        self.assertNotContains(response, "Всего статей")
        self.assertNotContains(response, "Управление блогом")

    def test_article_list_filters_by_editorial_status(self):
        Article.objects.create(
            locale="ru", category=self.category, author=self.user, title="Готовая статья", slug="ready",
            excerpt="Excerpt", content="Content", editorial_status=Article.EditorialStatus.READY,
        )
        Article.objects.create(
            locale="ru", category=self.category, author=self.user, title="Рабочий черновик", slug="draft",
            excerpt="Excerpt", content="Content", editorial_status=Article.EditorialStatus.DRAFT,
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse("cms:article-list"), {"editorial_status": "ready"})
        self.assertContains(response, "Готовая статья")
        self.assertNotContains(response, "Рабочий черновик")

    def test_tinymce_supports_responsive_youtube_embeds(self):
        editor_script = (Path(__file__).parent / "static" / "cms" / "js" / "editor.js").read_text(encoding="utf-8")
        self.assertIn('youtubeEmbed', editor_script)
        self.assertIn('label: "Код iframe"', editor_script)
        self.assertIn('youtubeVideoIdFromIframe', editor_script)
        self.assertIn('youtube-nocookie.com/embed/', editor_script)
        self.assertIn('aspect-ratio:16/9', editor_script)
        self.assertIn('restoreMissingGalleryMarkers', editor_script)
        self.assertIn('editor.selection.collapse(false)', editor_script)
        self.assertIn('data-gallery-marker', editor_script)
        self.assertIn('editorIsFullscreen', editor_script)
        self.assertIn('isDraft ? "save" : "publish"', editor_script)

    def test_tinymce_preserves_and_edits_html_tables(self):
        editor_script = (Path(__file__).parent / "static" / "cms" / "js" / "editor.js").read_text(encoding="utf-8")
        self.assertIn('searchreplace table visualblocks', editor_script)
        self.assertIn('youtubeEmbed table | articleGallery', editor_script)
        self.assertIn('table[class|style|width|height|border|cellpadding|cellspacing]', editor_script)
        self.assertNotIn('textarea,table,thead,tbody,tfoot,tr,td,th,caption,col,colgroup', editor_script)

    def test_youtube_iframe_survives_save_and_public_api(self):
        self.client.force_login(self.user)
        iframe = '<iframe src="https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ" allowfullscreen></iframe>'
        response = self.client.post(reverse("cms:article-create"), self.article_payload(action="publish", content=iframe))
        self.assertEqual(response.status_code, 302)
        article = Article.objects.get()
        self.assertIn("youtube-nocookie.com/embed/dQw4w9WgXcQ", article.content)
        cache.clear()
        public_response = self.client.get(reverse("article-detail", kwargs={"slug": article.slug}), {"locale": "ru"})
        self.assertEqual(public_response.status_code, 200)
        self.assertIn("youtube-nocookie.com/embed/dQw4w9WgXcQ", public_response.json()["content"])

    def test_html_table_survives_save_and_public_api(self):
        self.client.force_login(self.user)
        table = (
            "<h2>Side-by-side basics</h2>"
            "<table><thead><tr><th></th><th>Chatroulette</th><th>Chatus</th></tr></thead>"
            "<tbody><tr><th scope=\"row\">Registration</th><td>None required</td>"
            "<td>None required</td></tr></tbody></table>"
        )
        response = self.client.post(reverse("cms:article-create"), self.article_payload(action="publish", content=table))
        self.assertEqual(response.status_code, 302)
        article = Article.objects.get()
        self.assertIn("<table>", article.content)
        self.assertIn("<thead>", article.content)
        self.assertIn("<tbody>", article.content)
        self.assertIn('<th scope="row">Registration</th>', article.content)
        cache.clear()
        public_response = self.client.get(reverse("article-detail", kwargs={"slug": article.slug}), {"locale": "ru"})
        self.assertEqual(public_response.status_code, 200)
        self.assertIn("<table>", public_response.json()["content"])
        self.assertIn("<th>Chatroulette</th>", public_response.json()["content"])

    def test_published_article_list_has_client_preview_link(self):
        self.client.force_login(self.user)
        self.client.post(reverse("cms:article-create"), self.article_payload(action="publish"))
        response = self.client.get(reverse("cms:article-list"))
        article = Article.objects.get()
        self.assertContains(response, "Посмотреть статью на сайте")
        self.assertContains(response, f'href="{article.public_url}"')
        self.assertContains(response, 'target="_blank"')

    @override_settings(FRONTEND_URL="https://zvezdach.com")
    def test_public_urls_follow_frontend_language_routes(self):
        from .serializers import ArticleListSerializer

        article = Article.objects.create(
            locale="ru", category=self.category, author=self.user,
            title="Подарки в Telegram", slug="telegram-podarki",
            excerpt="Короткое описание", content="Текст статьи",
        )
        self.assertEqual(article.public_url, f"https://zvezdach.com/blog/{article.slug}")
        self.assertEqual(ArticleListSerializer(article).data["url"], article.public_url)
        article.locale = "en"
        self.assertEqual(article.public_url, f"https://zvezdach.com/en/blog/{article.slug}")
        self.assertEqual(ArticleListSerializer(article).data["url"], article.public_url)

    def test_future_publication_is_shown_as_scheduled(self):
        self.client.force_login(self.user)
        self.client.post(
            reverse("cms:article-create"),
            self.article_payload(action="publish", published_at=(timezone.localdate() + timedelta(days=3)).strftime("%Y-%m-%d")),
        )
        response = self.client.get(reverse("cms:article-list"))
        self.assertContains(response, "Запланирована")
        article = Article.objects.get()
        self.assertFalse(Article.published.filter(pk=article.pk).exists())

    def test_ajax_article_update_returns_success_without_redirect(self):
        self.client.force_login(self.user)
        self.client.post(reverse("cms:article-create"), self.article_payload(action="save", status=Article.Status.DRAFT))
        article = Article.objects.get()
        response = self.client.post(
            reverse("cms:article-edit", kwargs={"pk": article.pk}),
            self.article_payload(action="save", status=Article.Status.DRAFT, title="Новый заголовок"),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertFalse(response.json()["created"])
        article.refresh_from_db()
        self.assertEqual(article.title, "Новый заголовок")

    def test_ajax_draft_errors_use_russian_field_names(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("cms:article-create"),
            self.article_payload(action="save", status=Article.Status.DRAFT, title="", excerpt="", content=""),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 422)
        messages = " ".join(response.json()["errors"])
        self.assertIn("Заголовок", messages)
        self.assertIn("Короткое описание", messages)
        self.assertIn("Текст статьи", messages)
        self.assertNotIn("This field is required", messages)

    def test_publishing_requires_at_least_one_tag(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("cms:article-create"),
            self.article_payload(action="publish", tags_input="[]"),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("Добавьте хотя бы один тег", response.json()["errors"])
        self.assertFalse(Article.objects.exists())

    def test_cms_datetime_uses_a_human_russian_date(self):
        value = timezone.make_aware(datetime(2026, 9, 20, 18, 45))
        self.assertEqual(cms_datetime(value), "20 сент. 2026 · 18:45")

    def test_delete_button_is_next_to_article_actions(self):
        self.client.force_login(self.user)
        self.client.post(reverse("cms:article-create"), self.article_payload(action="save", status=Article.Status.DRAFT))
        article = Article.objects.get()
        response = self.client.get(reverse("cms:article-edit", kwargs={"pk": article.pk}))
        content = response.content.decode()
        self.assertContains(response, 'form="delete-form"')
        self.assertLess(content.index('form="delete-form"'), content.index('id="publish-button"'))

    def test_published_article_requires_cover_and_seo_but_defaults_publication_date(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("cms:article-create"),
            self.article_payload(cover_image="", cover_alt="", seo_title="", seo_description="", published_at=""),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Добавьте обложку перед публикацией")
        self.assertContains(response, "Добавьте заголовок для поисковиков")
        self.assertNotContains(response, "Укажите дату публикации.")
        self.assertFalse(Article.objects.filter(slug="kak-nachat-razgovor").exists())

    def test_unfinished_draft_can_be_saved_without_publication_fields(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("cms:article-create"),
            self.article_payload(status=Article.Status.DRAFT, cover_image="", cover_alt="", seo_title="", seo_description="", published_at=""),
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Article.objects.filter(slug="kak-nachat-razgovor", status=Article.Status.DRAFT).exists())

    def test_logged_in_user_sees_all_articles(self):
        other = get_user_model().objects.create_user(username="other", password="test-password")
        Article.objects.create(
            locale="ru", category=self.category, author=other, title="Общая статья",
            slug="shared", excerpt="Excerpt", content="Content",
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse("cms:article-list"))
        self.assertContains(response, "Общая статья")

    def test_tag_autocomplete_starts_at_three_characters(self):
        Tag.objects.create(locale="ru", name="Психология", slug="psychology")
        Tag.objects.create(locale="en", name="Psychology", slug="psychology")
        self.client.force_login(self.user)
        short = self.client.get(reverse("cms:tag-search"), {"q": "Пс", "locale": "ru"})
        full = self.client.get(reverse("cms:tag-search"), {"q": "Пси", "locale": "ru"})
        wrong_locale = self.client.get(reverse("cms:tag-search"), {"q": "Пси", "locale": "en"})
        self.assertEqual(short.json()["results"], [])
        self.assertEqual(full.json()["results"][0]["name"], "Психология")
        self.assertEqual(wrong_locale.json()["results"], [])

    def test_tag_management_is_split_into_language_sections(self):
        Tag.objects.create(locale="ru", name="Общение", slug="obschenie")
        Tag.objects.create(locale="en", name="Communication", slug="communication")
        self.client.force_login(self.user)
        response = self.client.get(reverse("cms:tag-list"))
        self.assertContains(response, "Русские теги")
        self.assertContains(response, "Английские теги")
        self.assertContains(response, "Индонезийские теги")
        self.assertContains(response, "#Общение")
        self.assertContains(response, "#Communication")

    def test_seed_categories_uses_shared_localized_category_model(self):
        call_command("seed_categories")
        self.assertEqual(Category.objects.filter(name_en="Safety and anonymity").count(), 1)
        category = Category.objects.get(name_en="Safety and anonymity")
        self.assertEqual(category.name_ru, "Безопасность и анонимность")
        self.assertEqual(category.name_id, "Keamanan dan anonimitas")
        self.assertTrue(category.is_active)

    def test_seed_demo_articles_creates_resettable_data_without_touching_real_content(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from PIL import Image
        fixture_dir = tempfile.TemporaryDirectory()
        self.addCleanup(fixture_dir.cleanup)
        Image.new("RGB", (64, 64), "#1db1ee").save(Path(fixture_dir.name) / "test.png")
        fixture_patch = patch("blog.management.commands.seed_demo_articles.FAKER_DIR", Path(fixture_dir.name))
        fixture_patch.start()
        self.addCleanup(fixture_patch.stop)
        real_article = Article.objects.create(
            locale="en", category=self.category, author=self.user, title="Real article", slug="real-article",
            excerpt="Real", content="<p>Real content</p>", status=Article.Status.DRAFT,
        )
        call_command("seed_demo_articles")
        demos = Article.objects.filter(is_demo=True)
        self.assertEqual(demos.count(), 20)
        self.assertSetEqual(set(demos.values_list("locale", flat=True)), {"ru", "en", "id"})
        self.assertGreater(len(set(demos.values_list("content", flat=True))), 10)
        self.assertTrue(demos.filter(gallery__isnull=True).exists())
        self.assertTrue(demos.annotate(gallery_total=models.Count("gallery")).filter(gallery_total__gt=5).exists())
        self.assertFalse(ArticleGalleryImage.objects.values("article_id", "gallery_number").annotate(total=models.Count("id")).filter(total__gt=5).exists())
        self.assertTrue(all("for_faker" not in image for image in demos.values_list("cover_image", flat=True)))
        call_command("seed_demo_articles", "--reset")
        self.assertFalse(Article.objects.filter(is_demo=True).exists())
        self.assertTrue(Article.objects.filter(pk=real_article.pk).exists())

    def test_same_tag_name_is_stored_separately_for_each_language(self):
        self.client.force_login(self.user)
        ru_response = self.client.post(
            reverse("cms:article-create"),
            self.article_payload(title="Русская статья", slug="ru-article", tags_input='["Общение"]'),
        )
        en_response = self.client.post(
            reverse("cms:article-create"),
            self.article_payload(
                locale="en",
                title="English article",
                slug="en-article",
                meta_keywords="must be removed",
                tags_input='["Общение"]',
            ),
        )
        self.assertEqual(ru_response.status_code, 302)
        self.assertEqual(en_response.status_code, 302)
        self.assertSetEqual(set(Tag.objects.filter(name="Общение").values_list("locale", flat=True)), {"ru", "en"})
        self.assertEqual(Article.objects.get(locale="en").meta_keywords, "")

    def test_article_rejects_a_tag_from_another_language(self):
        article = Article.objects.create(
            locale="en",
            category=self.category,
            author=self.user,
            title="English",
            slug="english",
            excerpt="Excerpt",
            content="Content",
        )
        russian_tag = Tag.objects.create(locale="ru", name="Общение", slug="obschenie")
        with self.assertRaisesMessage(ValidationError, "Теги должны относиться к языку статьи"):
            article.tags.add(russian_tag)

    def test_standard_django_admin_is_not_exposed(self):
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 404)

    def test_cover_and_gallery_are_saved_as_webp_and_avif(self):
        self.client.force_login(self.user)
        payload = self.article_payload(
            action="publish",
            cover_image=test_image("cover.png"),
            gallery_captions='{"1":"Общая подпись галереи"}',
            **{
                "gallery-TOTAL_FORMS": "1",
                "gallery-0-image": test_image("gallery.jpeg", (30, 40, 50)),
                "gallery-0-alt": "Описание изображения",
                "gallery-0-gallery_number": "1",
                "gallery-0-sort_order": "0",
            },
        )
        response = self.client.post(reverse("cms:article-create"), payload)
        article = Article.objects.get(slug="kak-nachat-razgovor")
        gallery = ArticleGalleryImage.objects.get(article=article)

        self.assertEqual(response.status_code, 302)
        self.assertTrue(article.cover_image.name.endswith(".webp"))
        self.assertTrue(article.cover_image_avif.name.endswith(".avif"))
        self.assertTrue(gallery.image.name.endswith(".webp"))
        self.assertTrue(gallery.image_avif.name.endswith(".avif"))
        self.assertEqual(gallery.gallery_number, 1)
        self.assertEqual(article.gallery_captions, {"1": "Общая подпись галереи"})

        api_response = APIClient().get(reverse("article-detail", kwargs={"slug": article.slug}), {"locale": "ru"})
        payload = api_response.json()
        self.assertTrue(payload["cover_image"].endswith(".webp"))
        self.assertTrue(payload["cover_image_avif"].endswith(".avif"))
        self.assertEqual(len(payload["gallery"]), 1)
        self.assertEqual(payload["gallery"][0]["gallery_number"], 1)
        self.assertEqual(payload["gallery_captions"], {"1": "Общая подпись галереи"})

    def test_gallery_rejects_more_than_five_images_per_group(self):
        self.client.force_login(self.user)
        gallery_fields = {
            "gallery-TOTAL_FORMS": "6",
            "gallery-INITIAL_FORMS": "0",
            "gallery-MIN_NUM_FORMS": "0",
            "gallery-MAX_NUM_FORMS": "50",
        }
        for index in range(6):
            gallery_fields.update({
                f"gallery-{index}-image": test_image(f"image-{index}.png"),
                f"gallery-{index}-caption": f"Caption {index}",
                f"gallery-{index}-alt": f"Alt {index}",
                f"gallery-{index}-gallery_number": "1",
                f"gallery-{index}-sort_order": str(index),
            })
        response = self.client.post(reverse("cms:article-create"), self.article_payload(**gallery_fields))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "не больше 5", html=False)
        self.assertFalse(Article.objects.filter(slug="kak-nachat-razgovor").exists())

    def test_images_are_saved_in_separate_numbered_galleries(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("cms:article-create"),
            self.article_payload(
                content="<p>Текст</p><p>[[gallery1]]</p><p>Ещё текст</p><p>[[gallery2]]</p>",
                **{
                    "gallery-TOTAL_FORMS": "2",
                    "gallery-0-image": test_image("gallery-one.png"),
                    "gallery-0-gallery_number": "1",
                    "gallery-0-sort_order": "0",
                    "gallery-1-image": test_image("gallery-two.png"),
                    "gallery-1-gallery_number": "2",
                    "gallery-1-sort_order": "0",
                },
            ),
        )

        self.assertEqual(response.status_code, 302)
        article = Article.objects.get(slug="kak-nachat-razgovor")
        self.assertEqual(list(article.gallery.values_list("gallery_number", flat=True)), [1, 2])

    def test_editor_upload_returns_webp_and_avif_urls(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("cms:image-upload"), {"file": test_image("inline.jpg")})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["location"].endswith(".webp"))
        self.assertTrue(response.json()["avif"].endswith(".avif"))

    def test_editor_rejects_an_image_over_two_megabytes_without_saving_it(self):
        self.client.force_login(self.user)
        before = set(Path(self.media_root).rglob("*"))
        oversized = SimpleUploadedFile("huge.png", b"0" * (2 * 1024 * 1024 + 1), content_type="image/png")
        response = self.client.post(reverse("cms:image-upload"), {"file": oversized})
        after = set(Path(self.media_root).rglob("*"))
        self.assertEqual(response.status_code, 400)
        self.assertIn("не больше 2 МБ", response.json()["error"])
        self.assertSetEqual(before, after)

    def test_editor_rejects_a_real_but_unsupported_image_format(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("cms:image-upload"), {"file": test_image_format("image.bmp", "BMP")})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Разрешены только форматы", response.json()["error"])

    def test_article_cover_rejects_an_image_over_two_megabytes(self):
        self.client.force_login(self.user)
        buffer = io.BytesIO()
        Image.frombytes("RGB", (1024, 1024), os.urandom(1024 * 1024 * 3)).save(buffer, format="PNG")
        oversized = SimpleUploadedFile("large.png", buffer.getvalue(), content_type="image/png")
        self.assertGreater(oversized.size, 2 * 1024 * 1024)
        response = self.client.post(
            reverse("cms:article-create"),
            self.article_payload(cover_image=oversized),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "не больше 2 МБ")
        self.assertFalse(Article.objects.exists())

    def test_gif_is_preserved_and_has_a_five_megabyte_limit(self):
        image = test_gif()
        processed, avif = optimize_image(image)
        self.assertTrue(processed.name.endswith(".gif"))
        self.assertIsNone(avif)
        with Image.open(io.BytesIO(processed.read())) as saved:
            self.assertTrue(saved.is_animated)

        oversized = test_gif("large.gif")
        oversized.size = MAX_GIF_UPLOAD_SIZE + 1
        with self.assertRaisesMessage(ValidationError, "GIF должен весить не больше 5 МБ"):
            validate_image_upload(oversized)

    def test_large_raster_is_limited_to_1920_pixels(self):
        buffer = io.BytesIO()
        Image.new("RGB", (3000, 1200), (255, 174, 25)).save(buffer, format="PNG")
        image = SimpleUploadedFile("wide.png", buffer.getvalue(), content_type="image/png")
        processed, _ = optimize_image(image)
        with Image.open(io.BytesIO(processed.read())) as saved:
            self.assertLessEqual(max(saved.size), MAX_IMAGE_DIMENSION)
