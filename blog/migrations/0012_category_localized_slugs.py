from django.db import migrations, models


CYRILLIC_MAP = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh",
    "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p",
    "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch",
    "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
})


def fill_category_slugs(apps, schema_editor):
    from django.utils.text import slugify

    Category = apps.get_model("blog", "Category")
    for locale in ("ru", "en", "id"):
        used = set()
        for category in Category.objects.order_by("pk"):
            value = getattr(category, f"name_{locale}", "")
            base = slugify(str(value).lower().translate(CYRILLIC_MAP))[:140].strip("-") or f"category-{locale}"
            candidate = base
            index = 2
            while candidate in used:
                suffix = f"-{index}"
                candidate = f"{base[:140 - len(suffix)].rstrip('-')}{suffix}"
                index += 1
            used.add(candidate)
            setattr(category, f"slug_{locale}", candidate)
            category.save(update_fields=[f"slug_{locale}"])


class Migration(migrations.Migration):
    dependencies = [("blog", "0011_article_is_demo_slug_length")]

    operations = [
        migrations.AddField(model_name="category", name="slug_ru", field=models.CharField(blank=True, max_length=140, null=True)),
        migrations.AddField(model_name="category", name="slug_en", field=models.CharField(blank=True, max_length=140, null=True)),
        migrations.AddField(model_name="category", name="slug_id", field=models.CharField(blank=True, max_length=140, null=True)),
        migrations.RunPython(fill_category_slugs, migrations.RunPython.noop),
        migrations.AlterField(model_name="category", name="slug_ru", field=models.SlugField(max_length=140, unique=True)),
        migrations.AlterField(model_name="category", name="slug_en", field=models.SlugField(max_length=140, unique=True)),
        migrations.AlterField(model_name="category", name="slug_id", field=models.SlugField(max_length=140, unique=True)),
    ]
