import hashlib

from django.db import migrations
from django.db import models


def hash_existing_tokens(apps, schema_editor):
    """Carry every existing plaintext token over as its SHA-256 hash.

    Deployed Pis keep their tokens: they keep sending the same plaintext, which
    now matches ``token_hash``. The plaintext column is dropped in 0012.
    """
    RaspberryPi = apps.get_model("devices", "RaspberryPi")
    pis = RaspberryPi.objects.exclude(device_token__isnull=True).exclude(
        device_token=""
    )
    for pi in pis.only("pk", "device_token"):
        RaspberryPi.objects.filter(pk=pi.pk).update(
            token_hash=hashlib.sha256(pi.device_token.encode()).hexdigest()
        )


class Migration(migrations.Migration):
    dependencies = [
        ("devices", "0010_alter_raspberrypi_last_seen"),
    ]

    operations = [
        migrations.AddField(
            model_name="raspberrypi",
            name="token_hash",
            field=models.CharField(
                blank=True, editable=False, max_length=64, null=True, unique=True
            ),
        ),
        migrations.AddField(
            model_name="raspberrypi",
            name="is_simulated",
            field=models.BooleanField(
                default=False,
                help_text="A local/QEMU simulator rather than real hardware.",
            ),
        ),
        # Irreversible by design: plaintext tokens can't be recovered from hashes.
        migrations.RunPython(hash_existing_tokens, migrations.RunPython.noop),
    ]
