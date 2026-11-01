from django.db import migrations, models


def split_tags_by_locale(apps, schema_editor):
    Article = apps.get_model("blog", "Article")
    Tag = apps.get_model("blog", "Tag")
    through = Article.tags.through

    for tag in Tag.objects.all().order_by("pk"):
        article_ids_by_locale = {}
        links = through.objects.filter(tag_id=tag.pk).values_list("article_id", flat=True)
        for article_id, locale in Article.objects.filter(pk__in=links).values_list("pk", "locale"):
            article_ids_by_locale.setdefault(locale, []).append(article_id)

        locales = list(article_ids_by_locale) or ["en"]
        primary_locale = locales[0]
        tag.locale = primary_locale
        tag.save(update_fields=["locale"])

        for locale in locales[1:]:
            localized_tag = Tag.objects.create(locale=locale, name=tag.name, slug=tag.slug)
            through.objects.filter(
                tag_id=tag.pk,
                article_id__in=article_ids_by_locale[locale],
            ).update(tag_id=localized_tag.pk)


class Migration(migrations.Migration):
    dependencies = [("blog", "0009_manual_reading_time")]

    operations = [
        migrations.AlterField(
            model_name="tag",
            name="name",
            field=models.CharField(max_length=80),
        ),
        migrations.AlterField(
            model_name="tag",
            name="slug",
            field=models.SlugField(max_length=100),
        ),
        migrations.AddField(
            model_name="tag",
            name="locale",
            field=models.CharField(
                choices=[("en", "English"), ("ru", "Russian"), ("id", "Indonesian")],
                db_index=True,
                default="en",
                max_length=2,
            ),
        ),
        migrations.RunPython(split_tags_by_locale, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="tag",
            constraint=models.UniqueConstraint(
                fields=("locale", "name"), name="unique_tag_name_per_locale"
            ),
        ),
        migrations.AddConstraint(
            model_name="tag",
            constraint=models.UniqueConstraint(
                fields=("locale", "slug"), name="unique_tag_slug_per_locale"
            ),
        ),
        migrations.AlterModelOptions(
            name="tag",
            options={"ordering": ("locale", "name")},
        ),
    ]
