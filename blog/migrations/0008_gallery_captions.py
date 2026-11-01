from django.db import migrations, models


def preserve_gallery_captions(apps, schema_editor):
    Article = apps.get_model("blog", "Article")
    for article in Article.objects.prefetch_related("gallery").iterator(chunk_size=100):
        captions = {}
        for image in article.gallery.all():
            if image.caption and str(image.gallery_number) not in captions:
                captions[str(image.gallery_number)] = image.caption
        if captions:
            article.gallery_captions = captions
            article.save(update_fields=("gallery_captions",))


class Migration(migrations.Migration):
    dependencies = [("blog", "0007_group_article_galleries")]

    operations = [
        migrations.AddField(
            model_name="article",
            name="gallery_captions",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.RunPython(preserve_gallery_captions, migrations.RunPython.noop),
        migrations.RemoveField(model_name="articlegalleryimage", name="caption"),
    ]
