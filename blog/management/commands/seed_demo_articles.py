from datetime import timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from blog.constants import ARTICLE_SLUG_MAX_LENGTH
from blog.models import Article, ArticleGalleryImage, Category, Tag
from blog.slugs import readable_slug


ROOT_DIR = Path(__file__).resolve().parents[3]
FAKER_DIR = ROOT_DIR / "for_faker"
LOCALES = ("ru", "en")

COPY = {
    "ru": {
        "titles": ["Как начать разговор без неловкости", "Почему ясные границы делают общение спокойнее", "Пять привычек для честного диалога", "Когда пауза в переписке не означает отказ", "Как обсуждать сложную тему без давления", "Маленькие шаги к уверенному знакомству", "Что помогает чувствовать себя безопаснее онлайн"],
        "tags": ["общение", "знакомства", "границы", "безопасность", "доверие"],
        "excerpt": "Практичные наблюдения, которые помогают говорить яснее и внимательнее слушать собеседника",
    },
    "en": {
        "titles": ["How to start a conversation without pressure", "Why clear boundaries make communication easier", "Five habits for an honest dialogue", "When a pause in chat does not mean rejection", "How to discuss a difficult topic with care", "Small steps toward confident dating", "What helps you feel safer online"],
        "tags": ["communication", "dating", "boundaries", "safety", "trust"],
        "excerpt": "Practical ideas for speaking clearly, listening closely and building more comfortable conversations",
    },
    "id": {
        "titles": ["Cara memulai percakapan tanpa tekanan", "Mengapa batas yang jelas membuat komunikasi lebih mudah", "Lima kebiasaan untuk dialog yang jujur", "Saat jeda dalam chat bukan berarti penolakan", "Cara membahas topik sulit dengan tenang", "Langkah kecil untuk perkenalan yang percaya diri"],
        "tags": ["komunikasi", "perkenalan", "batas", "keamanan", "kepercayaan"],
        "excerpt": "Catatan praktis untuk berbicara lebih jelas, mendengar dengan perhatian dan membangun percakapan yang nyaman",
    },
}


def article_html(locale: str, index: int) -> str:
    title = COPY[locale]["titles"][index % len(COPY[locale]["titles"])]
    paragraphs = [
        f"<p>{COPY[locale]['excerpt']} В этой статье разбираем ситуацию шаг за шагом и оставляем место для собственного темпа</p>",
        "<p><strong>Начните с простого вопроса</strong>, а затем дайте человеку время ответить <em>без спешки и догадок</em></p>",
        "<h2>Что можно сделать уже сегодня</h2><p>Полезно заранее назвать цель разговора, обозначить границы и проверить, одинаково ли вы понимаете договорённость</p>",
        "<ul><li>Выбирайте конкретные слова</li><li>Задавайте один вопрос за раз</li><li>Не требуйте немедленного ответа</li></ul>",
        "<h3>Небольшая практика</h3><p>Попробуйте сформулировать просьбу через факт, влияние и следующий шаг. Такая структура снижает напряжение и помогает сохранить уважение</p>",
        "<blockquote><p>Хороший разговор строится не на идеальных словах, а на внимании к человеку напротив</p><cite>Редакция Chatus</cite></blockquote>",
        f"<p>Если тема кажется слишком большой, разделите её на несколько коротких сообщений. Материал «{title}» можно использовать как отправную точку для своей следующей беседы</p>",
        "<ol><li>Сформулируйте мысль</li><li>Выслушайте ответ</li><li>Уточните следующий шаг</li></ol><p>Подробнее о подходе можно прочитать <a href=\"https://chatus.com\">на сайте Chatus</a></p>",
    ]
    return "".join(paragraphs[: 4 + index % 5])


class Command(BaseCommand):
    help = "Create exactly 20 local demo articles using only files from for_faker"

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete only demo articles and their media")

    def handle(self, *args, **options):
        if not FAKER_DIR.is_dir():
            raise CommandError("Directory for_faker is required")
        source_images = sorted(path for path in FAKER_DIR.iterdir() if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".avif", ".gif"})
        if not source_images:
            raise CommandError("for_faker does not contain supported images")

        with transaction.atomic():
            demo_articles = Article.objects.filter(is_demo=True)
            removed = demo_articles.count()
            demo_articles.delete()
            if options["reset"]:
                self.stdout.write(self.style.SUCCESS(f"Removed {removed} demo articles"))
                return

            call_command("seed_categories", verbosity=0)
            categories = list(Category.objects.order_by("pk"))
            user_model = get_user_model()
            author = user_model.objects.filter(is_staff=True, is_active=True).first()
            if not author:
                author, _ = user_model.objects.get_or_create(username="demo-seed", defaults={"is_staff": True, "is_active": True})
                author.set_unusable_password()
                author.save(update_fields=["password"])

            now = timezone.now()
            for index in range(20):
                locale = LOCALES[index % len(LOCALES)]
                data = COPY[locale]
                title = data["titles"][index % len(data["titles"])]
                status = Article.Status.DRAFT if index % 5 == 0 else Article.Status.PUBLISHED
                published_at = None if status == Article.Status.DRAFT else now - timedelta(days=index * 3 + 1)
                if index in {7, 16}:
                    published_at = now + timedelta(days=index - 5)
                slug_prefix = f"demo-{locale}-{index + 1}"
                article = Article(
                    locale=locale,
                    category=categories[index % len(categories)],
                    author=author,
                    title=title,
                    slug=f"{slug_prefix}-{slugify(title)[:ARTICLE_SLUG_MAX_LENGTH - len(slug_prefix) - 1]}",
                    excerpt=data["excerpt"],
                    content=article_html(locale, index),
                    cover_alt=title,
                    reading_time=3 + index % 12,
                    status=status,
                    editorial_status=(
                        Article.EditorialStatus.READY
                        if status == Article.Status.PUBLISHED or index % 3 == 0
                        else Article.EditorialStatus.DRAFT
                    ),
                    published_at=published_at,
                    seo_title=title[:70],
                    seo_description=data["excerpt"][:170],
                    meta_keywords=", ".join(data["tags"][:3]) if locale == "ru" else "",
                    is_demo=True,
                )
                cover_source = source_images[index % len(source_images)]
                article.cover_image = ContentFile(cover_source.read_bytes(), name=cover_source.name)
                article.save()

                tags = []
                for name in data["tags"][: 1 + index % 3]:
                    tag, _ = Tag.objects.get_or_create(
                        locale=locale,
                        name=name,
                        defaults={"slug": readable_slug(name, fallback=f"tag-{locale}-{index}", max_length=100)},
                    )
                    tags.append(tag)
                article.tags.set(tags)

                gallery_count = 0 if index % 4 == 0 else 1 if index % 4 == 1 else 2
                captions = {}
                for gallery_number in range(1, gallery_count + 1):
                    captions[str(gallery_number)] = f"Подборка изображений для материала «{title}»"
                    for image_number in range(1 + (index + gallery_number) % 5):
                        source = source_images[(index + gallery_number + image_number) % len(source_images)]
                        gallery_image = ArticleGalleryImage(article=article, gallery_number=gallery_number, sort_order=image_number, alt=f"{title} — изображение {image_number + 1}")
                        gallery_image.image = ContentFile(source.read_bytes(), name=source.name)
                        gallery_image.save()
                article.gallery_captions = captions
                article.save(update_fields=["gallery_captions", "updated_at"])
        self.stdout.write(self.style.SUCCESS("Created 20 demo articles"))
