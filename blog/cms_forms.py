import json
from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.forms import BaseInlineFormSet, inlineformset_factory

from .constants import ARTICLE_SLUG_MAX_LENGTH
from .models import Article, ArticleGalleryImage, Category
from .image_processing import validate_image_upload
from .slugs import readable_slug


LOCALE_CHOICES_RU = (
    ("ru", "Русский"),
    ("en", "Английский"),
    ("id", "Индонезийский"),
)

STATUS_CHOICES_RU = (
    ("draft", "Черновик"),
    ("published", "Опубликована"),
)

EDITORIAL_STATUS_CHOICES_RU = (
    ("draft", "Черновик"),
    ("ready", "Готово"),
)

def article_slug_from_title(title):
    return readable_slug(title, fallback="article", max_length=ARTICLE_SLUG_MAX_LENGTH)


INPUT_CLASS = (
    "w-full rounded-2xl border border-stone-200 bg-white px-4 py-3 text-sm text-stone-900 "
    "transition placeholder:text-stone-400 focus:border-[#1db1ee]"
)

AUTH_INPUT_CLASS = (
    "w-full rounded-xl border border-white/10 bg-[#0e0c08] px-4 py-3.5 text-sm text-white "
    "transition-colors duration-300 placeholder:text-stone-400 focus:border-[#1db1ee]"
)


class CmsAuthenticationForm(AuthenticationForm):
    username = forms.CharField(
        label="Логин",
        widget=forms.TextInput(attrs={"class": AUTH_INPUT_CLASS, "autofocus": True, "placeholder": "Введите логин"}),
    )
    password = forms.CharField(
        label="Пароль",
        strip=False,
        widget=forms.PasswordInput(attrs={"class": AUTH_INPUT_CLASS, "placeholder": "Введите пароль"}),
    )


class ArticleForm(forms.ModelForm):
    tags_input = forms.CharField(label="Теги", required=False, widget=forms.HiddenInput())

    class Meta:
        model = Article
        fields = (
            "locale",
            "category",
            "title",
            "slug",
            "excerpt",
            "content",
            "cover_image",
            "cover_alt",
            "status",
            "editorial_status",
            "published_at",
            "seo_title",
            "seo_description",
            "meta_keywords",
            "gallery_captions",
        )
        widgets = {
            "excerpt": forms.Textarea(attrs={"rows": 3}),
            "content": forms.Textarea(attrs={"rows": 24, "data-editor": "tinymce"}),
            "cover_image": forms.FileInput(attrs={"accept": "image/png,image/jpeg,image/webp,image/avif,image/gif"}),
            "cover_alt": forms.HiddenInput(),
            "gallery_captions": forms.HiddenInput(),
            "published_at": forms.DateInput(
                attrs={"type": "text", "data-date-picker": "true", "autocomplete": "off", "readonly": True},
                format="%Y-%m-%d",
            ),
        }

    def __init__(self, *args, can_publish=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["locale"].choices = LOCALE_CHOICES_RU
        self.fields["status"].choices = STATUS_CHOICES_RU
        self.fields["editorial_status"].choices = EDITORIAL_STATUS_CHOICES_RU
        self.fields["published_at"].input_formats = ("%Y-%m-%d",)
        field_labels = {
            "locale": "Язык",
            "category": "Категория",
            "title": "Заголовок",
            "slug": "Адрес статьи",
            "excerpt": "Короткое описание",
            "content": "Текст статьи",
            "cover_image": "Обложка",
            "cover_alt": "Альтернативный текст обложки",
            "status": "Состояние",
            "editorial_status": "Готовность материала",
            "published_at": "Дата публикации",
            "seo_title": "Заголовок для поисковиков",
            "seo_description": "Описание для поисковиков",
            "meta_keywords": "Ключевые слова",
        }
        for name, label in field_labels.items():
            self.fields[name].label = label
            self.fields[name].error_messages["required"] = f"Заполните поле «{label}»"
        for name, field in self.fields.items():
            if name in {"content", "tags_input", "gallery_captions"}:
                continue
            field.widget.attrs["class"] = INPUT_CLASS
            if isinstance(field.widget, forms.Select):
                field.widget.attrs["data-custom-select"] = "true"
        self.fields["excerpt"].widget.attrs["maxlength"] = 500
        self.fields["excerpt"].widget.attrs["class"] = f"{INPUT_CLASS} min-h-[200px] max-h-[300px]"
        self.fields["slug"].required = False
        self.fields["slug"].widget.attrs["maxlength"] = ARTICLE_SLUG_MAX_LENGTH
        # TinyMCE hides the original textarea. Native browser validation cannot
        # focus that hidden control and blocks submit before TinyMCE syncs it.
        self.fields["content"].widget.attrs["required"] = False
        self.fields["cover_image"].widget.attrs["class"] = "sr-only"
        self.fields["cover_alt"].required = False
        placeholders = {
            "title": "Например: Как начать разговор с незнакомцем",
            "slug": "kak-nachat-razgovor-s-neznakomtsem",
            "excerpt": "Коротко расскажите, о чём эта статья",
            "content": "Начните писать статью…",
            "seo_title": "Заголовок статьи в поисковой выдаче",
            "seo_description": "Краткое описание для поисковых систем",
            "meta_keywords": "общение, знакомства, безопасность",
            "published_at": "Выберите дату",
        }
        for name, placeholder in placeholders.items():
            self.fields[name].widget.attrs["placeholder"] = placeholder
        if not can_publish:
            self.fields["status"].disabled = True
            self.fields["published_at"].disabled = True

    def _generated_slug(self):
        base = article_slug_from_title(self.cleaned_data.get("title"))
        locale = self.cleaned_data.get("locale") or "en"
        queryset = Article.objects.filter(locale=locale)
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        candidate = base
        suffix = 2
        while queryset.filter(slug=candidate).exists():
            candidate = f"{base[:ARTICLE_SLUG_MAX_LENGTH - len(str(suffix)) - 1]}-{suffix}"
            suffix += 1
        return candidate

    def clean_slug(self):
        raw_slug = self.cleaned_data.get("slug")
        if not raw_slug:
            return ""
        slug = article_slug_from_title(raw_slug)
        locale = self.data.get("locale") or self.instance.locale or "en"
        queryset = Article.objects.filter(locale=locale, slug=slug)
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise forms.ValidationError("Такой адрес уже используется в выбранной языковой версии")
        return slug

    def save(self, commit=True):
        article = super().save(commit=False)
        if not article.slug:
            article.slug = self._generated_slug()
        article.cover_alt = article.title
        if commit:
            article.save()
            self.save_m2m()
        return article

    def clean_cover_image(self):
        image = self.cleaned_data.get("cover_image")
        if image:
            validate_image_upload(image)
        return image

    def clean(self):
        cleaned = super().clean()
        cleaned["cover_alt"] = cleaned.get("title") or ""
        if cleaned.get("locale") != "ru":
            cleaned["meta_keywords"] = ""
        if cleaned.get("status") != "published":
            return cleaned
        required_for_publication = {
            "cover_image": "Добавьте обложку перед публикацией",
            "seo_title": "Добавьте заголовок для поисковиков",
            "seo_description": "Добавьте описание для поисковиков",
        }
        for field_name, message in required_for_publication.items():
            if not cleaned.get(field_name):
                self.add_error(field_name, message)
        if not cleaned.get("published_at"):
            from django.utils import timezone

            cleaned["published_at"] = timezone.now()
        try:
            tags = json.loads(cleaned.get("tags_input") or "[]")
        except (TypeError, json.JSONDecodeError):
            tags = []
        if not isinstance(tags, list) or not any(str(tag).strip() for tag in tags):
            self.add_error("tags_input", "Добавьте хотя бы один тег")
        return cleaned


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ("name_ru", "name_en", "name_id", "is_active")
        labels = {
            "name_ru": "Название на русском",
            "name_en": "Название на английском",
            "name_id": "Название на индонезийском",
            "is_active": "Показывать на сайте",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = INPUT_CLASS
        self.fields["is_active"].widget.attrs["class"] = "peer sr-only"
        self.fields["name_ru"].widget.attrs["placeholder"] = "Например: Безопасность"
        self.fields["name_en"].widget.attrs["placeholder"] = "Например: Safety"
        self.fields["name_id"].widget.attrs["placeholder"] = "Например: Keamanan"


class GalleryImageForm(forms.ModelForm):
    class Meta:
        model = ArticleGalleryImage
        fields = ("image", "alt", "gallery_number", "sort_order")
        widgets = {"gallery_number": forms.HiddenInput(), "sort_order": forms.HiddenInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["image"].label = "Изображение галереи"
        self.fields["alt"].label = "Альтернативный текст изображения"
        self.fields["image"].error_messages["required"] = "Добавьте изображение в галерею"
        self.fields["alt"].error_messages["required"] = "Добавьте альтернативный текст изображения"
        self.fields["gallery_number"].required = False
        self.fields["gallery_number"].initial = 1
        for name in ("image", "alt"):
            self.fields[name].widget.attrs["class"] = INPUT_CLASS
        self.fields["image"].widget.attrs["class"] = "sr-only"
        self.fields["image"].widget.attrs["accept"] = "image/png,image/jpeg,image/webp,image/avif,image/gif"
        self.fields["alt"].widget.attrs["placeholder"] = "Опишите содержимое изображения"

    def clean_image(self):
        image = self.cleaned_data.get("image")
        if image:
            validate_image_upload(image)
        return image

    def clean_gallery_number(self):
        return self.cleaned_data.get("gallery_number") or 1


class BaseArticleGalleryFormSet(BaseInlineFormSet):
    default_error_messages = {
        **BaseInlineFormSet.default_error_messages,
        "too_many_forms": "В статье может быть не больше 50 изображений",
    }

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        counts = {}
        for form in self.forms:
            if not hasattr(form, "cleaned_data") or form.cleaned_data.get("DELETE"):
                continue
            if not form.cleaned_data.get("image"):
                continue
            number = form.cleaned_data.get("gallery_number") or 1
            if number < 1 or number > 10:
                raise forms.ValidationError("Номер галереи должен быть от 1 до 10")
            counts[number] = counts.get(number, 0) + 1
            if counts[number] > 5:
                raise forms.ValidationError(f"В галерее №{number} может быть не больше 5 изображений")


ArticleGalleryFormSet = inlineformset_factory(
    Article,
    ArticleGalleryImage,
    form=GalleryImageForm,
    formset=BaseArticleGalleryFormSet,
    extra=0,
    can_delete=True,
    max_num=50,
    validate_max=True,
)
