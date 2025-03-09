from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.core.cache import cache
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from navi_backend.core.validators import (
    validate_image_size,
    validate_image_extension,
)
from imagekit.processors import ResizeToFit
from imagekit.models import ProcessedImageField
from decimal import Decimal
from navi_backend.users.models import User
from navi_backend.orders.managers import MenuItemManager


class AuditModel(models.Model):
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    last_modified_ip = models.GenericIPAddressField(
        _("last modified IP"),
        null=True,
        editable=False,
    )
    last_modified_user_agent = models.CharField(
        _("last modified user agent"),
        max_length=200,
        null=True,
        editable=False,
    )

    class Meta:
        abstract = True


class SlugifiedModel(models.Model):
    name = models.CharField(
        _("Name"),
        max_length=200,
        unique=True,
        db_index=True,
        help_text=_("Unique name"),
    )
    slug = models.SlugField(
        _("Slug"),
        unique=True,
        max_length=200,
        db_index=True,
        help_text=_("URL-friendly version of name"),
    )

    class Meta:
        abstract = True

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        return super().save(*args, **kwargs)


class StatusModel(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "A", _("Active")
        INACTIVE = "I", _("Inactive")
        DRAFT = "D", _("Draft")
        ARCHIVED = "R", _("Archived")

    status = models.CharField(
        _("Status"),
        max_length=1,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
        help_text=_("availability status"),
    )

    class Meta:
        abstract = True


class UpdateRecordModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_created",
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_updated",
    )

    class Meta:
        abstract = True


# Create your models here.
class Port(
    SlugifiedModel,
    StatusModel,
    UpdateRecordModel,
    AuditModel,
):
    name = models.CharField(max_length=200, null=True, blank=True)
    # eventually add location info
    slug = models.SlugField(unique=True, blank=False)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        return super().save(*args, **kwargs)


class PaymentType(
    SlugifiedModel,
    StatusModel,
    UpdateRecordModel,
    AuditModel,
):
    name = models.CharField(max_length=200, null=True, blank=True)
    slug = models.SlugField(unique=True, blank=False)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        return super().save(*args, **kwargs)


class Category(
    SlugifiedModel,
    StatusModel,
    UpdateRecordModel,
    AuditModel,
):

    name = models.CharField(max_length=200, null=True, blank=True)
    slug = models.SlugField(unique=True, blank=False)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        return super().save(*args, **kwargs)


class MenuItem(
    SlugifiedModel,
    StatusModel,
    UpdateRecordModel,
    AuditModel,
):
    price = models.DecimalField(
        _("Price"),
        decimal_places=2,
        max_digits=8,
        validators=[
            MaxValueValidator(Decimal(99999.99)),
            MinValueValidator(Decimal(0.01)),
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
    image = ProcessedImageField(
        verbose_name=_("Image"),
        upload_to="product_images/%Y/%m/",
        processors=[ResizeToFit(1200, 1200)],
        format="JPEG",
        options={"quality": 85},
        validators=[validate_image_size, validate_image_extension],
        help_text=_("Product image (max 5MB, JPEG/PNG)"),
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
    all_objects = MenuItemManager().with_deleted

    class Meta:
        verbose_name = _("MenuItem")
        verbose_name_plural = _("MenuItems")
        ordering = ["name"]
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["price"]),
            models.Index(fields=["status"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["-view_count"]),
            models.Index(fields=["-selected_count"]),
            models.Index(fields=["is_deleted"]),
            models.Index(fields=["is_featured", "status"]),
        ]
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

        if self.status == self.Status.ACTIVE and not self.image:
            raise ValidationError({"status": _("Active menuitem must have an image.")})

        if self.is_deleted and self.status == self.Status.ACTIVE:
            raise ValidationError({"status": _("Deleted menuitem cannot be active.")})

    def save(self, *args, **kwargs):
        if not self._state.adding:
            self.version += 1

        self.full_clean()
        super().save(*args, **kwargs)
        self.invalidate_cache()

    def delete(self, using=None, keep_parents=False):
        self.invalidate_cache()
        super().delete(using, keep_parents)

    def get_cache_key(self):
        return f"menuitem:{self.name}:v{self.version}"

    def invalidate_cache(self):
        """Invalidate all cached data for this product."""
        cache_keys = [
            self.get_cache_key(),
            f"{self.get_cache_key()}:price",
            f"menuitem:slug:{self.slug}",
        ]
        cache.delete_many(cache_keys)

    @property
    def cached_price(self):
        """Get cached price value."""
        cache_key = f"{self.get_cache_key()}:price"
        cached_value = cache.get(cache_key)
        if cached_value is None:
            cached_value = self.price
            cache.set(cache_key, cached_value, timeout=3600)
        return cached_value

    @property
    def is_active(self):
        """Check if menuitem is active."""
        return self.status == self.Status.ACTIVE and not self.is_deleted

    def activate(self):
        """Activate the product."""
        if self.is_deleted:
            raise ValidationError(_("Cannot activate deleted menuitem."))
        self.status = self.Status.ACTIVE
        self.save(update_fields=["status", "updated_at", "version"])

    def archive(self):
        self.status = self.Status.ARCHIVED
        self.save(update_fields=["status", "updated_at", "version"])

    def soft_delete(self, user_ip=None, user_agent=None):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.status = self.Status.INACTIVE
        self.last_modified_ip = user_ip
        self.last_modified_user_agent = user_agent
        self.save(
            update_fields=[
                "is_deleted",
                "deleted_at",
                "status",
                "last_modified_ip",
                "last_modified_user_agent",
                "updated_at",
                "version",
            ]
        )

    def restore(self):
        """Restore a soft-deleted product."""
        if not self.is_deleted:
            raise ValidationError(_("Cannot restore non-deleted menuitem."))
        self.is_deleted = False
        self.deleted_at = None
        self.save(
            update_fields=[
                "is_deleted",
                "deleted_at",
                "updated_at",
                "version",
            ]
        )

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
        from django.urls import reverse

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


class Order(
    SlugifiedModel,
    StatusModel,
    UpdateRecordModel,
    AuditModel,
):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    payment_type = models.ForeignKey(
        PaymentType, on_delete=models.SET_NULL, null=True, blank=True
    )
    port = models.ForeignKey(Port, on_delete=models.SET_NULL, null=True, blank=True)
    totalPrice = models.DecimalField(
        max_digits=7, decimal_places=2, null=True, blank=True
    )

    def __str__(self):
        return str(self.created_at)

    def save(self, *args, **kwargs):
        return super().save(*args, **kwargs)


class OrderItem(
    SlugifiedModel,
    StatusModel,
    UpdateRecordModel,
    AuditModel,
):
    menu_item = models.ForeignKey(MenuItem, on_delete=models.SET_NULL, null=True)
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True)
    name = models.CharField(max_length=200, null=True, blank=True)
    qty = models.IntegerField(null=True, blank=True, default=1)
    price = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)

    def __str__(self):
        return str(self.name)

    def save(self, *args, **kwargs):
        return super().save(*args, **kwargs)


class CustomizationGroup(
    SlugifiedModel,
    StatusModel,
    UpdateRecordModel,
    AuditModel,
):
    name = models.CharField(max_length=200, null=True, blank=True)
    category = models.ManyToManyField(Category)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        return super().save(*args, **kwargs)


class Customization(
    SlugifiedModel,
    StatusModel,
    UpdateRecordModel,
    AuditModel,
):
    name = models.CharField(max_length=200, null=True, blank=True)
    group = models.ForeignKey(CustomizationGroup, on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        return super().save(*args, **kwargs)


class OrderCustomization(
    SlugifiedModel,
    StatusModel,
    UpdateRecordModel,
    AuditModel,
):
    name = models.CharField(max_length=200, null=True, blank=True)
    order_item = models.ForeignKey(OrderItem, on_delete=models.SET_NULL, null=True)
    customization = models.ForeignKey(
        Customization, on_delete=models.SET_NULL, null=True
    )
    qty = models.IntegerField(null=True, blank=True, default=0)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        return super().save(*args, **kwargs)
