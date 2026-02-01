from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from navi_backend.core.models import AuditModel
from navi_backend.core.models import NamedModel
from navi_backend.core.models import SlugifiedModel
from navi_backend.core.models import UUIDModel
from navi_backend.menu.managers import MenuItemManager


class Category(
    UUIDModel,
    SlugifiedModel,
    NamedModel,
    AuditModel,
):
    def save(self, *args, **kwargs):
        return super().save(*args, **kwargs)


class MenuItem(
    UUIDModel,
    SlugifiedModel,
    NamedModel,
    AuditModel,
):
    price = models.DecimalField(
        _("Price"),
        decimal_places=2,
        max_digits=8,
        validators=[
            MaxValueValidator(Decimal("99999.99")),
            MinValueValidator(Decimal("0.01")),
        ],
        help_text=_("Price of option in dollars (between $99999-$0.01)"),
    )
    description = models.CharField(
        _("Description"),
        max_length=100,
        help_text=_("Short description of menuitem"),
    )
    body = models.TextField(
        _("Body"),
        help_text=_("Detailed menuitem description"),
    )
    view_count = models.PositiveIntegerField(
        _("View count"),
        default=0,
        editable=False,
        help_text=_("View count for product"),
    )
    selected_count = models.PositiveIntegerField(
        _("Selected count"),
        default=0,
        editable=False,
        help_text=_("Count of how many times this menu item was chosen"),
    )
    is_featured = models.BooleanField(
        _("featured"),
        default=False,
        db_index=True,
    )
    category = models.ForeignKey(
        Category,
        verbose_name=_("Category"),
        related_name="menu_items",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_index=True,
        help_text=_("Category this menu item belongs to"),
    )
    version = models.PositiveIntegerField(
        _("Version"),
        default=1,
        editable=False,
        help_text=_("Internal version tracking"),
    )

    objects = MenuItemManager()

    class Meta:
        verbose_name = _("MenuItem")
        verbose_name_plural = _("MenuItems")
        ordering = ["name"]
        permissions = [
            ("can_change_status", "Can change menuitem status"),
            ("can_feature_product", "Can mark menuitem as featured"),
            ("can_view_deleted", "Can view deleted menuitems"),
        ]

    def __str__(self):
        return f"{self.name} (v{self.version})"

    def clean(self):
        if self.price and self.price < 0:
            raise ValidationError({"price": _("Price cannot be negative.")})

        if self.is_deleted and self.status == self.Status.ACTIVE:
            raise ValidationError({"status": _("Deleted menuitem cannot be active.")})

    def save(self, *args, **kwargs):
        if not self._state.adding:
            self.version += 1

        super().save(*args, **kwargs)

    def increment_view_count(self):
        """Increment the view count safely using F() expressions."""
        self.__class__.objects.filter(pk=self.pk).update(
            view_count=models.F("view_count") + 1
        )

    def increment_selected_count(self):
        """Increment the view count safely using F() expressions."""
        self.__class__.objects.filter(pk=self.pk).update(
            selected_count=models.F("selected_count") + 1
        )

    def get_absolute_url(self):
        """Get the canonical URL for the menuitem."""
        return reverse("menuitem-detail", kwargs={"slug": self.slug})

    def get_related_items(self, limit=4):
        if not self.category:
            return MenuItem.objects.none()

        return MenuItem.objects.filter(
            category=self.category, status=self.Status.ACTIVE, is_deleted=False
        ).exclude(pk=self.pk)[:limit]

    def toggle_featured(self):
        self.is_featured = not self.is_featured
        self.save(update_fields=["is_featured", "updated_at", "version"])


class CustomizationGroup(
    UUIDModel,
    SlugifiedModel,
    NamedModel,
    AuditModel,
):
    category = models.ManyToManyField(Category)
    description = models.CharField(_("Description"), max_length=255, blank=True)
    display_order = models.PositiveIntegerField(_("Display Order"), default=0)
    is_required = models.BooleanField(_("Required"), default=False)
    allow_multiple = models.BooleanField(_("allow_multiple"), default=False)
    minimum_allowed = models.PositiveIntegerField(
        _("minimum allowed"), blank=True, null=True
    )
    maximum_allowed = models.PositiveIntegerField(
        _("maximum allowed"), blank=True, null=True
    )

    def __str__(self):
        return self.name

    def clean(self):
        if (
            self.minimum_allowed is not None
            and self.maximum_allowed is not None
            and self.minimum_allowed >= self.maximum_allowed
        ):
            error_message = _("Max allowed must be greater than min allowed.")
            raise ValidationError({"maximum_allowed": error_message})

    def save(self, *args, **kwargs):
        return super().save(*args, **kwargs)

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name = _("Customization Group")


class Customization(
    UUIDModel,
    SlugifiedModel,
    NamedModel,
    AuditModel,
):
    group = models.ForeignKey(CustomizationGroup, on_delete=models.SET_NULL, null=True)
    description = models.CharField(_("Description"), max_length=255, blank=True)
    display_order = models.PositiveIntegerField(_("Display Order"), default=0)
    price = models.DecimalField(
        _("Price"),
        decimal_places=2,
        max_digits=8,
        validators=[
            MaxValueValidator(Decimal("99999.99")),
            MinValueValidator(Decimal("0.01")),
        ],
        help_text=_("Price of customization in dollars (between $99999-$0.01)"),
    )

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        return super().save(*args, **kwargs)

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name = _("Customization")


class Ingredient(UUIDModel, NamedModel, SlugifiedModel, AuditModel):
    """Individual ingredient details."""

    description = models.TextField(blank=True)
    is_allergen = models.BooleanField(
        _("Allergen"),
        default=False,
        help_text=_("Check if this ingredient is a common allergen"),
    )

    def __str__(self):
        return self.name


class MenuItemIngredient(UUIDModel):
    """Through model to track ingredient quantities for menu items."""

    menu_item = models.ForeignKey(
        MenuItem,
        on_delete=models.CASCADE,
        related_name="menu_item_ingredients",
        help_text=_("Menu item this ingredient belongs to"),
    )
    ingredient = models.ForeignKey(
        Ingredient,
        on_delete=models.CASCADE,
        related_name="menu_item_ingredients",
        help_text=_("Ingredient used in this menu item"),
    )
    quantity = models.DecimalField(
        _("Amount"),
        max_digits=7,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text=_("Amount of ingredient required (e.g., grams, ounces)"),
    )
    unit = models.CharField(
        _("Unit"),
        max_length=50,
        help_text=_("Unit of measurement (e.g., g, oz, ml)"),
    )

    class Meta:
        unique_together = ["menu_item", "ingredient"]

    def __str__(self):
        return (
            f"{self.quantity} {self.unit} {self.ingredient.name} "
            f"in {self.menu_item.name}"
        )
