import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [("companies", "0002_initial"), ("sources", "0003_cnpj_manifest")]
    operations = [
        migrations.CreateModel(
            name="WebsitePage",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("url", models.URLField(max_length=1000)),
                ("page_type", models.CharField(choices=[("HOME", "Inicial"), ("ABOUT", "Sobre"), ("PRODUCT", "Produto/solução"), ("CASE", "Caso/cliente"), ("NEWS", "Notícia/blog"), ("CAREERS", "Carreiras"), ("OTHER", "Outra")], default="OTHER", max_length=16)),
                ("title", models.CharField(blank=True, max_length=500)),
                ("extracted_text", models.TextField()),
                ("content_hash", models.CharField(max_length=64)),
                ("http_status", models.PositiveSmallIntegerField()),
                ("content_type", models.CharField(max_length=120)),
                ("observed_at", models.DateTimeField()),
                ("collected_at", models.DateTimeField(auto_now_add=True)),
                ("last_seen_at", models.DateTimeField()),
                ("current", models.BooleanField(default=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="website_pages", to="companies.company")),
                ("source_record", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="website_page", to="sources.sourcerecord")),
            ],
            options={
                "ordering": ("-observed_at", "url"),
                "indexes": [models.Index(fields=["company", "current", "observed_at"], name="page_company_current_idx")],
                "constraints": [models.UniqueConstraint(fields=("company", "url", "content_hash"), name="unique_company_page_content")],
            },
        )
    ]
