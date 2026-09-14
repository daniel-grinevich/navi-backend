from django.db import migrations
from django.utils import timezone


def start_expiry_clock_at_launch(apps, schema_editor):
    """Give existing accounts a full expiry window from the day this ships.

    Backfilling from old ledger entries would let the first nightly expiry run
    wipe the balances of long-idle customers with no warning.
    """
    UserLoyalty = apps.get_model("awards", "UserLoyalty")
    UserLoyalty.objects.filter(last_activity_at__isnull=True).update(
        last_activity_at=timezone.now()
    )


class Migration(migrations.Migration):
    dependencies = [
        ("awards", "0005_rewards_promotions_and_redemptions"),
    ]

    operations = [
        migrations.RunPython(start_expiry_clock_at_launch, migrations.RunPython.noop),
    ]
