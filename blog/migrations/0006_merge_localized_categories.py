from django.db import migrations, models


def merge_localized_categories(apps, schema_editor):
    Category = apps.get_model("blog", "Category")
    Article = apps.get_model("blog", "Article")
    canonical_by_slug = {}

    for category in Category.objects.order_by("pk"):
        canonical = canonical_by_slug.get(category.slug)
        if canonical is None:
            canonical = category
            canonical_by_slug[category.slug] = canonical
        localized_field = f"name_{category.locale}"
        setattr(canonical, localized_field, category.name)
        canonical.is_active = canonical.is_active or category.is_active
        canonical.save(update_fields=(localized_field, "is_active"))
        if canonical.pk != category.pk:
            Article.objects.filter(category_id=category.pk).update(category_id=canonical.pk)
            category.delete()

    for category in Category.objects.all():
        fallback = category.name_ru or category.name_en or category.name_id or "Категория"
        changed = []
        for locale in ("ru", "en", "id"):
            field = f"name_{locale}"
            if not getattr(category, field):
                setattr(category, field, fallback)
                changed.append(field)
        if changed:
            category.save(update_fields=changed)


class Migration(migrations.Migration):
    dependencies = [("blog", "0005_alter_article_options")]

    operations = [
        migrations.AddField(model_name="category", name="name_ru", field=models.CharField(blank=True, default="", max_length=120)),
        migrations.AddField(model_name="category", name="name_en", field=models.CharField(blank=True, default="", max_length=120)),
        migrations.AddField(model_name="category", name="name_id", field=models.CharField(blank=True, default="", max_length=120)),
        migrations.RunPython(merge_localized_categories, migrations.RunPython.noop),
        migrations.RemoveConstraint(model_name="category", name="unique_category_slug_per_locale"),
        migrations.RemoveField(model_name="category", name="locale"),
        migrations.RemoveField(model_name="category", name="name"),
        migrations.RemoveField(model_name="category", name="slug"),
        migrations.RemoveField(model_name="category", name="description"),
        migrations.RemoveField(model_name="category", name="sort_order"),
        migrations.AlterField(model_name="category", name="name_ru", field=models.CharField(max_length=120)),
        migrations.AlterField(model_name="category", name="name_en", field=models.CharField(max_length=120)),
        migrations.AlterField(model_name="category", name="name_id", field=models.CharField(max_length=120)),
        migrations.AlterModelOptions(name="category", options={"ordering": ("name_ru",), "verbose_name_plural": "categories"}),
    ]
