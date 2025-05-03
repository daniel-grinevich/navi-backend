from django.db import models

from navi_backend.core.models import NamedModel, SlugifiedModel, AuditModel


class Payment(AuditModel):
    STATUS_CHOICES = [
        ("requires_capture", "Requires Capture"),
        ("succeeded", "Succeeded"),
        ("canceled", "Canceled"),
        ("failed", "Failed"),
    ]

    stripe_payment_intent_id = models.CharField(max_length=255, unique=True)
    amount_received = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency = models.CharField(max_length=10, default="usd")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)

    def __str__(self):
        return f"Payment {self.stripe_payment_intent_id} - {self.status}"
