from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("blog", "0010_tag_locale")]

    operations = [
        migrations.AlterField(model_name="article", name="slug", field=models.SlugField(max_length=220)),
        migrations.AddField(model_name="article", name="is_demo", field=models.BooleanField(db_index=True, default=False, editable=False)),
    ]
