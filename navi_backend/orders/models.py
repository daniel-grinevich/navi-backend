from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from navi_backend.core.models import AuditModel
from navi_backend.core.models import SlugifiedModel
from navi_backend.devices.models import NaviPort
from navi_backend.menu.models import Customization
from navi_backend.menu.models import MenuItem
from navi_backend.payments.models import Payment
from navi_backend.users.models import User


class Status(models.TextChoices):
    ORDERED = "O", _("Ordered")
    SENT = "S", _("Sent")
    COMPLETED = "D", _("Completed")
    CANCELLED = "C", _("Cancelled")


class Order(
    SlugifiedModel,
    AuditModel,
):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    navi_port = models.ForeignKey(
        NaviPort, on_delete=models.SET_NULL, null=True, blank=True
    )
    payment = models.OneToOneField(
        Payment,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    cart_token = models.CharField(max_length=255, blank=False, null=False)
    status = models.CharField(
        _("Order Status"),
        max_length=1,
        choices=Status.choices,
        default=Status.ORDERED,
        db_index=True,
        help_text=_("Order status"),
    )

    def __str__(self):
        return f"{self.user} (v{self.created_at})"

    @property
    def price(self):
        total = Decimal("0.00")
        if self.pk:
            for item in self.items.all():
                total += item.price
        return total

    def clean(self):
        if self.price and self.price < 0:
            raise ValidationError({"price": _("Price cannot be negative.")})

    def save(self, *args, **kwargs):
        return super().save(*args, **kwargs)


class OrderItem(
    SlugifiedModel,
    AuditModel,
):
    menu_item = models.ForeignKey(MenuItem, on_delete=models.SET_NULL, null=True)
    order = models.ForeignKey(
        Order, on_delete=models.SET_NULL, null=True, related_name="items"
    )
    quantity = models.IntegerField(
        default=1,
        validators=[
            MaxValueValidator(100),
            MinValueValidator(1),
        ],
    )
    unit_price = models.DecimalField(
        _("Unit Price"),
        decimal_places=2,
        max_digits=8,
        validators=[
            MaxValueValidator(Decimal("99999.99")),
            MinValueValidator(Decimal("0.01")),
        ],
        help_text=_("Price per unit in dollars (between $99999-$0.01)"),
    )

    def __str__(self):
        return f"{self.order} {self.menu_item}"

    def save(self, *args, **kwargs):
        if not self.order:
            msg = "Can't save an order item without a parent order."
            raise ValidationError(msg)
        if self.order.order_status != "O":
            msg = (
                "You can't update order items if the order is not in "
                "'Ordered' status."
            )
            raise ValidationError(msg)

        # Set unit price from menu item if not already set
        if not self.unit_price:
            self.unit_price = self.menu_item.price

        return super().save(*args, **kwargs)

    @property
    def price(self):
        item_price = self.unit_price * self.quantity
        customizations_price = sum(
            customization.price for customization in self.customizations.all()
        )
        return item_price + customizations_price


class OrderCustomization(
    SlugifiedModel,
    AuditModel,
):
    order_item = models.ForeignKey(
        OrderItem, on_delete=models.SET_NULL, null=True, related_name="customizations"
    )
    customization = models.ForeignKey(
        Customization, on_delete=models.SET_NULL, null=True
    )
    quantity = models.IntegerField(
        default=1,
        validators=[
            MaxValueValidator(100),
            MinValueValidator(1),
        ],
    )
    unit_price = models.DecimalField(
        _("Unit Price"),
        decimal_places=2,
        max_digits=8,
        validators=[
            MaxValueValidator(Decimal("99999.99")),
            MinValueValidator(Decimal("0.01")),
        ],
        help_text=_("Price per unit in dollars (between $99999-$0.01)"),
    )

    @property
    def price(self):
        return self.quantity * self.unit_price

    def __str__(self):
        return f"{self.order_item} {self.customization}"

    def save(self, *args, **kwargs):
        if self.order_item:
            order_item = OrderItem.objects.get(pk=self.order_item.pk)
            if order_item.order.order_status != "O":
                msg = (
                    "You cannot update order customizations if the order is not in "
                    "'Ordered' status."
                )
                raise ValidationError(msg)
        return super().save(*args, **kwargs)
