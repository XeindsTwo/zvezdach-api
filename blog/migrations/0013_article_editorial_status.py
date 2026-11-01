from django.db import migrations, models


def mark_published_articles_ready(apps, schema_editor):
    Article = apps.get_model("blog", "Article")
    Article.objects.filter(status="published").update(editorial_status="ready")


class Migration(migrations.Migration):
    dependencies = [("blog", "0012_category_localized_slugs")]

    operations = [
        migrations.AddField(
            model_name="article",
            name="editorial_status",
            field=models.CharField(
                choices=[("draft", "Draft"), ("ready", "Ready")],
                db_index=True,
                default="draft",
                max_length=12,
            ),
        ),
        migrations.RunPython(mark_published_articles_ready, migrations.RunPython.noop),
    ]
