from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0006_alter_invoice_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="payment",
            name="subtotal",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AddField(
            model_name="payment",
            name="tax_amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AddField(
            model_name="payment",
            name="total_amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AddField(
            model_name="payment",
            name="stripe_tax_calculation_id",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="payment",
            name="stripe_tax_transaction_id",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
    ]
