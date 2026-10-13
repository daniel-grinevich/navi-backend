import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    dependencies = [
        ("devices", "0011_raspberrypi_token_hash_is_simulated"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveField(
            model_name="raspberrypi",
            name="device_token",
        ),
        migrations.CreateModel(
            name="DeviceEvent",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "type",
                    models.CharField(
                        choices=[
                            ("connected", "Connected"),
                            ("disconnected", "Disconnected"),
                            ("heartbeat", "Heartbeat"),
                            ("order_claimed", "Order claimed"),
                            ("brew_started", "Brew started"),
                            ("brew_completed", "Brew completed"),
                            ("brew_failed", "Brew failed"),
                            ("token_rotated", "Token rotated"),
                            ("test_order", "Test order"),
                        ],
                        max_length=32,
                    ),
                ),
                ("message", models.CharField(blank=True, max_length=255)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "raspberry_pi",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="events",
                        to="devices.raspberrypi",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=["raspberry_pi", "-created_at"],
                        name="devices_dev_raspber_0011f1_idx",
                    )
                ],
            },
        ),
    ]
