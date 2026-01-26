from django.db import models

from navi_backend.core.models import AuditModel
from navi_backend.core.models import UpdateRecordModel
from navi_backend.core.models import UUIDModel


class Payment(UUIDModel, AuditModel):
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


class Invoice(UUIDModel, AuditModel, UpdateRecordModel):
    order = models.OneToOneField(
        "orders.Order", on_delete=models.PROTECT, related_name="invoice"
    )
    reference_number = models.PositiveIntegerField(editable=False, unique=True)
    pdf = models.FileField(upload_to="invoices/", null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.reference_number:
            last = self.__class__.last_reference_number()
            self.reference_number = last.reference_number + 1 if last else 1

        super().save(*args, **kwargs)

    @classmethod
    def last_reference_number(cls):
        return (
            cls.objects.only("reference_number").order_by("-reference_number").first()
        )

    def format_reference_number(self):
        return f"{self.reference_number:06d}"
