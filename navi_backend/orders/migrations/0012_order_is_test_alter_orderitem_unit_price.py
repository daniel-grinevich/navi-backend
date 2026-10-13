from decimal import Decimal

import django.core.validators
from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0011_alter_machineerrorlog_created_by_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="is_test",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AlterField(
            model_name="orderitem",
            name="unit_price",
            field=models.DecimalField(
                decimal_places=2,
                help_text="Price per unit in dollars (between $99999-$0.00)",
                max_digits=8,
                validators=[
                    django.core.validators.MaxValueValidator(Decimal("99999.99")),
                    django.core.validators.MinValueValidator(Decimal("0.00")),
                ],
                verbose_name="Unit Price",
            ),
        ),
    ]
