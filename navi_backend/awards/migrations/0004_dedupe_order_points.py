from django.db import migrations
from django.db.models import Count
from django.db.models import F
from django.db.models.functions import Greatest


def dedupe_order_points(apps, schema_editor):
    """Keep one ORDER ledger entry per order before it becomes unique (0005).

    The old ``.exists()`` idempotency check could race on retried tasks. Any
    duplicate grant is removed and its points and order count are taken back
    off the account, so balances match the ledger again.
    """
    PointsTransaction = apps.get_model("awards", "PointsTransaction")
    UserLoyalty = apps.get_model("awards", "UserLoyalty")

    duplicated_order_ids = (
        PointsTransaction.objects.filter(reason="order", order__isnull=False)
        .order_by()
        .values("order")
        .annotate(entries=Count("id"))
        .filter(entries__gt=1)
        .values_list("order", flat=True)
    )
    for order_id in list(duplicated_order_ids):
        entries = list(
            PointsTransaction.objects.filter(reason="order", order_id=order_id).order_by(
                "created_at"
            )
        )
        for extra in entries[1:]:
            UserLoyalty.objects.filter(user_id=extra.user_id).update(
                balance_points=Greatest(F("balance_points") - extra.points, 0),
                lifetime_points=Greatest(F("lifetime_points") - extra.points, 0),
                orders_completed=Greatest(F("orders_completed") - 1, 0),
            )
            extra.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("awards", "0003_alter_award_threshold_awardlevel_useraward_level_and_more"),
    ]

    operations = [
        migrations.RunPython(dedupe_order_points, migrations.RunPython.noop),
    ]
