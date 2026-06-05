from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("order_page", "0038_bundle_unit_pricing_flags_formitem_unit_pricing_flags"),
    ]

    operations = [
        migrations.CreateModel(
            name="FramerRegistrationSubmission",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "source",
                    models.CharField(
                        choices=[
                            ("override", "Framer override API"),
                            ("webhook", "Framer webhook"),
                        ],
                        db_index=True,
                        max_length=20,
                    ),
                ),
                (
                    "framer_submission_id",
                    models.CharField(blank=True, default="", max_length=128),
                ),
                (
                    "email",
                    models.EmailField(blank=True, db_index=True, max_length=254, null=True),
                ),
                ("raw_payload", models.JSONField(default=dict)),
                ("parsed_payload", models.JSONField(blank=True, null=True)),
                (
                    "http_status",
                    models.PositiveSmallIntegerField(blank=True, null=True),
                ),
                ("response_payload", models.JSONField(blank=True, null=True)),
                ("success", models.BooleanField(db_index=True, default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={
                "db_table": "framer_registration_submission",
                "ordering": ["-created_at"],
            },
        ),
    ]
