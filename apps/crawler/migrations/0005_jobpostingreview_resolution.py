import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("crawler", "0004_jobpostingreview"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.AddField(model_name="jobpostingreview", name="employment_type", field=models.CharField(blank=True, max_length=120)),
        migrations.AddField(model_name="jobpostingreview", name="published_on", field=models.DateField(blank=True, null=True)),
        migrations.AddField(model_name="jobpostingreview", name="valid_through", field=models.DateField(blank=True, null=True)),
        migrations.AddField(model_name="jobpostingreview", name="job_posting", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reviews", to="crawler.jobposting")),
        migrations.AddField(model_name="jobpostingreview", name="reviewed_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="jobpostingreview", name="reviewed_by", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="job_posting_reviews", to=settings.AUTH_USER_MODEL)),
        migrations.AddField(model_name="jobpostingreview", name="resolution_note", field=models.TextField(blank=True)),
    ]
