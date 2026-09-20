from django.db import models

from navi_backend.core.models import AuditModel
from navi_backend.core.models import UpdateRecordModel
from navi_backend.core.models import UUIDModel
from navi_backend.devices.models import NaviPort


class Payment(UUIDModel, AuditModel):
    STATUS_CHOICES = [
        ("requires_setup", "Requires Setup"),
        ("ready", "Ready"),
        ("succeeded", "Succeeded"),
        ("canceled", "Canceled"),
        ("failed", "Failed"),
    ]

    # Card is saved at checkout via a SetupIntent; the actual charge (a
    # PaymentIntent confirmed off-session) only happens at pickup, so the
    # payment intent id is null until then.
    stripe_setup_intent_id = models.CharField(max_length=255, blank=True, default="")
    stripe_payment_method_id = models.CharField(max_length=255, blank=True, default="")
    stripe_payment_intent_id = models.CharField(
        max_length=255, unique=True, null=True, blank=True
    )
    amount_received = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency = models.CharField(max_length=10, default="usd")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    # Stripe Tax: the calculation is created when the pickup port is known (at
    # scan) and converted into a recorded tax transaction once the charge
    # succeeds.
    stripe_tax_calculation_id = models.CharField(max_length=255, blank=True, default="")
    stripe_tax_transaction_id = models.CharField(max_length=255, blank=True, default="")

    def __str__(self):
        ref = self.stripe_payment_intent_id or self.stripe_setup_intent_id
        return f"Payment {ref} - {self.status}"


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


class EffectiveTaxRate(UUIDModel):
    """The combined sales-tax rate for a NaviPort's jurisdiction, refreshed
    nightly from TaxJar. The scan-time charge reads the most recent rate rather
    than calling a tax API in the Pi's critical path.

    Rows are date-effective (one per port per day) so the rate applied to any
    past charge can be reconstructed for auditing. System-generated, so no
    audit user fields.
    """

    navi_port = models.ForeignKey(
        NaviPort, on_delete=models.CASCADE, related_name="tax_rates"
    )
    # Combined rate as a fraction, e.g. 0.1025 for 10.25%.
    rate = models.DecimalField(max_digits=6, decimal_places=4)
    effective_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        unique_together = ("navi_port", "effective_date")
        ordering = ["-effective_date"]

    def __str__(self):
        return f"{self.navi_port} @ {self.rate} ({self.effective_date})"

    @classmethod
    def current_rate(cls, navi_port, on_date):
        """Most recent rate in effect for a port on a given date, or None."""
        row = (
            cls.objects.filter(navi_port=navi_port, effective_date__lte=on_date)
            .order_by("-effective_date")
            .first()
        )
        return row.rate if row else None
