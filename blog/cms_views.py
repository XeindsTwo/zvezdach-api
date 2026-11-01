import json
import uuid
from functools import wraps

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.views import LoginView
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_GET, require_POST
from .cms_forms import ArticleForm, ArticleGalleryFormSet, CategoryForm, CmsAuthenticationForm
from .constants import normalize_locale
from .image_processing import optimize_image
from .models import Article, Category, Tag
from .slugs import readable_slug


def can_access_cms(user):
    return user.is_authenticated and user.is_active and (user.is_staff or user.is_superuser)


def can_publish(user):
    return can_access_cms(user)


def cms_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"{reverse_lazy('cms:login')}?next={request.path}")
        if not can_access_cms(request.user):
            raise Http404
        return view(request, *args, **kwargs)

    return wrapped


class CmsLoginView(LoginView):
    template_name = "cms/auth/login.html"
    authentication_form = CmsAuthenticationForm
    redirect_authenticated_user = True

    def get_success_url(self):
        if not can_access_cms(self.request.user):
            logout(self.request)
            return str(reverse_lazy("cms:login"))
        return self.get_redirect_url() or str(reverse_lazy("cms:article-list"))

    def form_valid(self, form):
        response = super().form_valid(form)
        if self.request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"ok": True, "redirect": self.get_success_url()})
        return response

    def form_invalid(self, form):
        if self.request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse(
                {"ok": False, "message": "Неверный логин или пароль"},
                status=422,
            )
        return super().form_invalid(form)


@require_POST
def cms_logout(request):
    logout(request)
    return redirect("cms:login")


def visible_articles(user):
    return Article.objects.select_related("category", "author").prefetch_related("tags", "gallery")


@cms_required
def dashboard(request):
    return redirect("cms:article-list")


@cms_required
def article_list(request):
    all_articles = visible_articles(request.user)
    queryset = all_articles
    search = request.GET.get("q", "").strip()
    locale = request.GET.get("locale", "").strip()
    status = request.GET.get("status", "").strip()
    editorial_status = request.GET.get("editorial_status", "").strip()
    if search:
        queryset = queryset.filter(Q(title__icontains=search) | Q(slug__icontains=search))
    if locale in {"ru", "en", "id"}:
        queryset = queryset.filter(locale=locale)
    else:
        locale = ""
    if status:
        queryset = queryset.filter(status=status)
    if editorial_status in {Article.EditorialStatus.DRAFT, Article.EditorialStatus.READY}:
        queryset = queryset.filter(editorial_status=editorial_status)
    else:
        editorial_status = ""
    page = Paginator(queryset, 20).get_page(request.GET.get("page"))
    return render(
        request,
        "cms/articles/list.html",
        {
            "page": page,
            "search": search,
            "locale_filter": locale,
            "status_filter": status,
            "editorial_status_filter": editorial_status,
        },
    )


def save_tags(article, raw_value):
    names = []
    try:
        parsed = json.loads(raw_value or "[]")
        names = parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        names = [item.strip() for item in (raw_value or "").split(",")]

    tags = []
    for raw_name in names:
        name = str(raw_name).strip()[:80]
        if not name:
            continue
        existing = Tag.objects.filter(locale=article.locale, name__iexact=name).first()
        if existing:
            tags.append(existing)
            continue
        base_slug = readable_slug(name, fallback=f"tag-{article.locale}", max_length=90)
        slug = base_slug
        suffix = 2
        while Tag.objects.filter(locale=article.locale, slug=slug).exists():
            slug = f"{base_slug[:94]}-{suffix}"
            suffix += 1
        tags.append(Tag.objects.create(locale=article.locale, name=name, slug=slug))
    article.tags.set(tags)


def clean_error_message(message, label="Поле"):
    message = str(message).strip().rstrip(".")
    if message.lower() == "this field is required":
        return f"Заполните поле «{label}»"
    return message


def article_form_errors(form, gallery_formset):
    errors = []
    for name, field_errors in form.errors.items():
        label = form.fields[name].label if name in form.fields else "Статья"
        errors.extend(clean_error_message(error, label) for error in field_errors)
    for index, gallery_form in enumerate(gallery_formset.forms, start=1):
        number = gallery_form.data.get(f"gallery-{index - 1}-gallery_number") or index
        for name, field_errors in gallery_form.errors.items():
            label = gallery_form.fields[name].label if name in gallery_form.fields else "Изображение"
            errors.extend(
                f"Галерея №{number}: {clean_error_message(error, label)}"
                for error in field_errors
            )
    errors.extend(clean_error_message(error, "Галерея") for error in gallery_formset.non_form_errors())
    return list(dict.fromkeys(errors))


@cms_required
def article_form(request, pk=None):
    article = get_object_or_404(visible_articles(request.user), pk=pk) if pk else None
    publish_permission = can_publish(request.user)
    initial = {}
    if article:
        initial["tags_input"] = json.dumps(list(article.tags.values_list("name", flat=True)), ensure_ascii=False)
    form_data = request.POST or None
    submit_action = request.POST.get("action") if request.method == "POST" else None
    if form_data is not None and submit_action in {"save", "publish"}:
        form_data = form_data.copy()
        if submit_action == "publish":
            form_data["status"] = Article.Status.PUBLISHED
            form_data["editorial_status"] = Article.EditorialStatus.READY
        else:
            form_data["status"] = article.status if article else Article.Status.DRAFT
    form = ArticleForm(
        form_data,
        request.FILES or None,
        instance=article,
        initial=initial,
        can_publish=publish_permission,
    )
    gallery_formset = ArticleGalleryFormSet(
        request.POST or None,
        request.FILES or None,
        instance=article or Article(),
        prefix="gallery",
    )
    is_ajax = request.headers.get("x-requested-with") == "XMLHttpRequest"
    form_is_valid = form.is_valid() if request.method == "POST" else False
    gallery_is_valid = gallery_formset.is_valid() if request.method == "POST" else False
    if request.method == "POST" and form_is_valid and gallery_is_valid:
        created = article is None
        with transaction.atomic():
            item = form.save(commit=False)
            if article is None:
                item.author = request.user
            item.save()
            save_tags(item, form.cleaned_data.get("tags_input", ""))
            gallery_formset.instance = item
            gallery_formset.save()
        if item.is_scheduled:
            message = "Публикация запланирована"
        elif item.status == Article.Status.PUBLISHED:
            message = "Статья опубликована"
        else:
            message = "Черновик сохранён"
        edit_url = reverse("cms:article-edit", kwargs={"pk": item.pk})
        if is_ajax:
            return JsonResponse({
                "ok": True,
                "message": message,
                "created": created,
                "edit_url": edit_url,
                "status": item.status,
                "scheduled": item.is_scheduled,
            })
        messages.success(request, message)
        return redirect("cms:article-edit", pk=item.pk)
    if request.method == "POST" and is_ajax:
        return JsonResponse(
            {"ok": False, "errors": article_form_errors(form, gallery_formset)},
            status=422,
        )
    return render(
        request,
        "cms/articles/form.html",
        {"form": form, "gallery_formset": gallery_formset, "article": article, "can_publish": publish_permission},
    )


@cms_required
@require_POST
def article_delete(request, pk):
    article = get_object_or_404(visible_articles(request.user), pk=pk)
    article.delete()
    messages.success(request, "Статья удалена")
    return redirect("cms:article-list")


@cms_required
def category_list(request):
    categories = Category.objects.annotate(article_count=Count("articles"))
    return render(
        request,
        "cms/categories/list.html",
        {"categories": categories, "category_form": CategoryForm()},
    )


def category_payload(category, *, created=False):
    return {
        "id": category.pk,
        "name_ru": category.name_ru,
        "name_en": category.name_en,
        "is_active": category.is_active,
        "article_count": category.articles.count(),
        "created": created,
    }


@cms_required
def category_form(request, pk=None):
    category = get_object_or_404(Category, pk=pk) if pk else None
    form = CategoryForm(request.POST or None, instance=category)
    if request.method == "POST" and form.is_valid():
        item = form.save()
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse(category_payload(item, created=category is None))
        messages.success(request, "Категория сохранена")
        return redirect("cms:category-list")
    if request.method == "POST" and request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse(
            {"errors": {name: [str(error) for error in errors] for name, errors in form.errors.items()}},
            status=422,
        )
    if request.method == "GET":
        target = f"{reverse_lazy('cms:category-list')}?edit={category.pk}" if category else f"{reverse_lazy('cms:category-list')}?new=1"
        return redirect(target)
    return render(request, "cms/categories/form.html", {"form": form, "category": category})


@cms_required
def tag_list(request):
    tags = Tag.objects.annotate(article_count=Count("articles")).order_by("name")
    tag_sections = [
        {"locale": "ru", "title": "Русские теги", "tags": tags.filter(locale="ru")},
        {"locale": "en", "title": "Английские теги", "tags": tags.filter(locale="en")},
    ]
    return render(request, "cms/tags/list.html", {"tag_sections": tag_sections})


@cms_required
@require_GET
def tag_search(request):
    query = request.GET.get("q", "").strip()
    locale = normalize_locale(request.GET.get("locale"))
    if len(query) < 3:
        return JsonResponse({"results": []})
    results = list(
        Tag.objects.filter(locale=locale, name__icontains=query)
        .values("id", "name", "slug", "locale")[:12]
    )
    return JsonResponse({"results": results})


@cms_required
@require_POST
def image_upload(request):
    uploaded = request.FILES.get("file")
    if not uploaded:
        return JsonResponse({"error": "Нужен файл изображения"}, status=400)
    try:
        processed, avif = optimize_image(uploaded)
    except ValidationError as error:
        return JsonResponse({"error": error.messages[0]}, status=400)
    file_id = uuid.uuid4().hex
    processed_path = default_storage.save(f"blog/editor/{file_id}-{processed.name}", processed)
    payload = {"location": request.build_absolute_uri(default_storage.url(processed_path))}
    if avif:
        avif_path = default_storage.save(f"blog/editor/{file_id}.avif", avif)
        payload["avif"] = request.build_absolute_uri(default_storage.url(avif_path))
    return JsonResponse(payload)
