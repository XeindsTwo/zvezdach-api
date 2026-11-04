from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("blog", "0014_alter_article_locale_alter_category_name_id_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="CmsAuditEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("occurred_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("actor", models.CharField(max_length=150)),
                ("ip", models.GenericIPAddressField()),
                ("action", models.CharField(max_length=40)),
                ("target", models.CharField(blank=True, max_length=255)),
            ],
        ),
        migrations.CreateModel(
            name="CmsLoginAttempt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ip", models.GenericIPAddressField(db_index=True)),
                ("username", models.CharField(blank=True, max_length=150)),
                ("attempted_at", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
        ),
    ]
