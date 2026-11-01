import re

from django.db import migrations, models
from django.db.models import Q


def number_existing_galleries(apps, schema_editor):
    Article = apps.get_model("blog", "Article")
    for article in Article.objects.filter(content__icontains="[[gallery]]").iterator():
        article.content = re.sub(r"\[\[gallery\]\]", "[[gallery1]]", article.content, flags=re.IGNORECASE)
        article.save(update_fields=("content",))


def restore_legacy_markers(apps, schema_editor):
    Article = apps.get_model("blog", "Article")
    for article in Article.objects.filter(content__icontains="[[gallery1]]").iterator():
        article.content = re.sub(r"\[\[gallery1\]\]", "[[gallery]]", article.content, flags=re.IGNORECASE)
        article.save(update_fields=("content",))


class Migration(migrations.Migration):
    dependencies = [("blog", "0006_merge_localized_categories")]

    operations = [
        migrations.AddField(
            model_name="articlegalleryimage",
            name="gallery_number",
            field=models.PositiveSmallIntegerField(default=1),
        ),
        migrations.AlterModelOptions(
            name="articlegalleryimage",
            options={"ordering": ("gallery_number", "sort_order", "pk")},
        ),
        migrations.AddConstraint(
            model_name="articlegalleryimage",
            constraint=models.CheckConstraint(condition=Q(gallery_number__gte=1), name="gallery_number_positive"),
        ),
        migrations.RunPython(number_existing_galleries, restore_legacy_markers),
    ]
