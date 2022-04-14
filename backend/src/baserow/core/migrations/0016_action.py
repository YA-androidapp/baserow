# Generated by Django 3.2.12 on 2022-03-31 13:29

import baserow.core.action.models
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0015_alter_userprofile_language"),
    ]

    operations = [
        migrations.CreateModel(
            name="Action",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("session", models.TextField(blank=True, null=True)),
                ("created_on", models.DateTimeField(auto_now_add=True)),
                ("type", models.TextField()),
                (
                    "params",
                    models.JSONField(
                        encoder=baserow.core.action.models.JSONEncoderSupportingDataClasses
                    ),
                ),
                ("scope", models.TextField()),
                ("undone_at", models.DateTimeField(blank=True, null=True)),
                ("error", models.TextField(blank=True, null=True)),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ("-created_on",),
            },
        ),
        migrations.AddIndex(
            model_name="action",
            index=models.Index(
                fields=["user", "-created_on", "scope", "session"],
                name="core_action_user_id_c23214_idx",
            ),
        ),
    ]
