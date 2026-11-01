from django.core.management.base import BaseCommand

from blog.models import Category


CATEGORIES = (
    ("Знакомства и общение", "Dating and communication", "Perkenalan dan komunikasi"),
    ("Безопасность и анонимность", "Safety and anonymity", "Keamanan dan anonimitas"),
    ("Гайды по Chatus", "Chatus guides", "Panduan Chatus"),
    ("Истории пользователей", "User stories", "Cerita pengguna"),
    ("Обновления сервиса", "Service updates", "Pembaruan layanan"),
    ("Психология общения", "Communication psychology", "Psikologi komunikasi"),
)


class Command(BaseCommand):
    help = "Create or update the shared localized Chatus blog categories"

    def handle(self, *args, **options):
        for name_ru, name_en, name_id in CATEGORIES:
            Category.objects.update_or_create(
                name_en=name_en,
                defaults={"name_ru": name_ru, "name_id": name_id, "is_active": True},
            )
        self.stdout.write(self.style.SUCCESS(f"{len(CATEGORIES)} shared categories are ready"))
