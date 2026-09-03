import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('devices', '0009_raspberrypi_device_token'),
        ('orders', '0009_machineerrorlog'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='claimed_by',
            field=models.ForeignKey(blank=True, help_text='Raspberry Pi that currently holds this order.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='claimed_orders', to='devices.raspberrypi'),
        ),
        migrations.AddField(
            model_name='order',
            name='claimed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
