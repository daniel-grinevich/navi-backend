from decimal import Decimal

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from imagekit.models import ProcessedImageField
from imagekit.processors import ResizeToFill

from navi_backend.users.models import User


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


class Option(UpdateRecordModel):
    class Status(models.TextChoices):
        ACTIVE = "A", _("Active")
        INACTIVE = "I", _("Inactive")
        DRAFT = "D", _("Draft")
        ARCHIVED = "R", _("Archived")

    name = models.CharField(
        _("Name"),
        max_length=50,
        unique=True,
        db_index=True,
        help_text=_("Unqiue name of option"),
    )
    slug = models.SlugField(
        _("Slug"),
        unique=True,
        max_length=70,
        db_index=True,
        help_text=_("URL-friendly version of name"),
    )
    price = models.DecimalField(
        _("Price"),
        decimal_places=2,
        max_digits=8,
        validators=[
            MaxValueValidator(Decimal(99999.99)),
            MinValueValidator(Decimal(0.01)),
        ],
        help_text=_("Price of option in dollars (between $99999-$0)"),
    )
    description = models.CharField(
        _("Description"),
        max_length=100,
        help_text=_("Short description of option"),
    )
    body = models.TextField(
        _("Body"),
        help_text=_("Detailed descriptionof option"),
    )
    status = models.CharField(
        _("Status"),
        max_length=1,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
        help_text=_("Option availability"),
    )
    selected_count = models.PositiveIntegerField(
        _("Selected count"),
        default=0,
        editable=False,
        help_text=_("Count of how many times option was chosen"),
    )
    version = models.PositiveIntegerField(
        _("Version"),
        default=1,
        editable=False,
        help_text=_("Internal version tracking"),
    )
    is_deleted = models.BooleanField(
        _("deleted"),
        default=False,
        help_text=_("soft delete flag"),
    )
    deleted_at = models.DateTimeField(
        _("deleted at"),
        null=True,
        blank=True,
    )
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
        ordering = ["name"]
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["slug"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.name} (v{self.version})"

    def clean(self):
        if self.price and self.price < 0:
            raise ValidationError(_("Price cannot be negative"))

        if self.is_deleted and self.status == self.Status.ACTIVE:
            raise ValidationError(_("Option cannot be active and deleted"))

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)

        if not self._state.adding:
            self.version += 1

        self.full_clean()
        super().save(*args, **kwargs)
        self.invalidate_cache()

    def delete(self, using=None, keep_parents=False):
        self.invalidate_cache()
        super().delete(using, keep_parents)

    def get_cache_key(self):
        return f"option:{self.name}:v{self.version}"

    def invalidate_keys(self):
        cache_keys = [
            self.get_cache_keys(),
            f"{self.get_cache_keys():price}",
            f"option:slug:{self.slug}",
        ]
        cache.delete_many(cache_keys)

    @property
    def cached_price(self):
        cache_key = f"{self.get_cache_key()}:price"
        cached_value = cache.get(cache_key)
        if cached_value is None:
            cached_value = self.price
            cache.set(cache_key, cached_value, timeout=3600)
        return cached_value

    @property
    def is_active(self):
        return self.status == self.Status.ACTIVE and not self.is_deleted

    def activate(self):
        if self.is_deleted:
            raise ValidationError(_("Cannot activate deleted record"))
        self.status = self.Status.ACTIVE
        self.save(update_fields=["status", "updated_at", "version"])

    def archive(self):
        self.status = self.Status.ARCHIVED
        self.save(update_fields=["updated_at", "version", "status"])

    def soft_delete(self, user_ip=None, user_agent=None):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.status = self.Status.INACTIVE
        self.last_modified_ip = user_ip
        self.last_modified_user_agent = user_agent
        self.save(
            updated_fields=[
                "is_deleted",
                "deleted_at",
                "status",
                "last_modified",
                "last_modified_user_agent",
                "updated_at",
                "version",
            ],
        )

    def restore(self):
        if not self.is_deleted:
            ValidationError(_("Can only restore deleted records"))
        self.is_deleted = False
        self.deleted_at = None
        self.status = self.Status.INACTIVE
        self.save(
            updated_fields=[
                "is_deleted",
                "deleted_at",
                "status",
                "updated_at",
                "version",
            ],
        )

    def incremented_selected_count(self):
        self.__class__.objects.filter(pk=self.pk).update(
            selected_count=models.F("selected_count") + 1,
        )

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("option_detail", kwargs={"slug": self.slug})

    @classmethod
    def get_active_options(cls):
        return cls.objects.filter(
            status=cls.Status.ACTIVE,
            is_deleted=False,
        ).select_related("created_by")


class Product(UpdateRecordModel):
    class Status(models.TextChoices):
        ACTIVE = "A", _("Active")
        INACTIVE = "I", _("Inactive")
        DRAFT = "D", _("Draft")
        ARCHIVED = "R", _("Archived")

    name = models.CharField(
        _("Name"),
        max_length=50,
        unique=True,
        db_index=True,
        help_text=_("Unique name of the product"),
    )
    slug = models.SlugField(
        _("Slug"),
        unique=True,
        max_length=100,
        db_index=True,
        help_text=_("URL-friendly version of the name"),
    )
    price = models.DecimalField(
        decimal_places=2,
        max_digits=8,
        validators=[
            MinValueValidator(Decimal("0.01")),
            MaxValueValidator(Decimal("99999.99")),
        ],
        help_text=_("Product price in dollars max $99,999.99"),
    )
    description = models.CharField(
        _("Description"),
        max_length=100,
        help_text=_("Short description for product listings"),
    )
    body = models.TextField(
        _("Body"),
        help_text=_("Detailed product description"),
    )
    status = models.CharField(
        _("Status"),
        max_length=1,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
        help_text=_("Product availability status"),
    )
    image = ProcessedImageField(
        upload_to="fakeapi_product_images/%Y/%m/",
        processors=[ResizeToFill(800, 800)],
        format="JPEG",
        options={"quality": 90},
        blank=True,
        null=True,
    )
    is_featured = models.BooleanField(
        _("featured"),
        default=False,
        db_index=True,
    )
    view_count = models.PositiveIntegerField(
        _("View count"),
        default=0,
        editable=False,
        help_text=_("View count for product"),
    )
    version = models.PositiveIntegerField(
        _("Version"),
        default=1,
        editable=False,
        help_text=_("Internal version tracking"),
    )
    is_deleted = models.BooleanField(
        _("deleted"),
        default=False,
        help_text=_("Soft delete flag"),
    )
    deleted_at = models.DateTimeField(
        _("deleted at"),
        null=True,
        blank=True,
    )
    # Audit fields
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
        verbose_name = _("Product")
        verbose_name_plural = _("Products")
        ordering = ["name"]
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["price"]),
            models.Index(fields=["status"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["-view_count"]),
            models.Index(fields=["is_deleted"]),
            models.Index(fields=["is_featured", "status"]),
        ]
        permissions = [
            ("can_change_status", "Can change product status"),
            ("can_feature_product", "Can mark product as featured"),
            ("can_view_deleted", "Can view deleted products"),
        ]

    def __str__(self):
        return f"{self.name} (v{self.version})"

    def clean(self):
        if self.price and self.price < 0:
            raise ValidationError({"price": _("Price cannot be negative.")})

        if self.status == self.Status.ACTIVE and not self.image:
            raise ValidationError({"status": _("Active product must have an image.")})

        if self.is_deleted and self.status == self.Status.ACTIVE:
            raise ValidationError({"status": _("Deleted products cannot be active.")})

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)

        if not self._state.adding:
            self.version += 1

        self.full_clean()
        super().save(*args, **kwargs)
        self.invalidate_cache()

    def delete(self, using=None, keep_parents=False):
        self.invalidate_cache()
        return super().delete(using, keep_parents)

    def get_cache_key(self):
        return f"product:{self.id}:v{self.version}"

    def invalidate_cache(self):
        """Invalidate all cached data for this product."""
        cache_keys = [
            self.get_cache_key(),
            f"{self.get_cache_key()}:price",
            f"product:slug:{self.slug}",
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
        """Check if product is active."""
        return self.status == self.Status.ACTIVE and not self.is_deleted

    def activate(self):
        """Activate the product."""
        if self.is_deleted:
            raise ValidationError(_("Cannot activate deleted product."))
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
            ],
        )

    def restore(self):
        """Restore a soft-deleted product."""
        if not self.is_deleted:
            raise ValidationError(_("Cannot restore non-deleted product."))
        self.is_deleted = False
        self.deleted_at = None
        self.save(
            update_fields=[
                "is_deleted",
                "deleted_at",
                "updated_at",
                "version",
            ],
        )

    # View counting
    def increment_view_count(self):
        """Increment the view count safely using F() expressions."""
        self.__class__.objects.filter(pk=self.pk).update(
            view_count=models.F("view_count") + 1,
        )

    # URL methods
    def get_absolute_url(self):
        """Get the canonical URL for the product."""
        from django.urls import reverse

        return reverse("product-detail", kwargs={"slug": self.slug})

    @classmethod
    def get_active_products(cls):
        """Get all active, non-deleted products."""
        return cls.objects.filter(
            status=cls.Status.ACTIVE,
            is_deleted=False,
        ).select_related("created_by")

    @classmethod
    def get_featured_products(cls):
        """Get featured, active, non-deleted products."""
        return (
            cls.get_active_products()
            .filter(is_featured=True)
            .select_related("created_by")
        )


class ProductManager(models.Manager):
    def get_queryset(self):
        cache_key = self.get_cache_key() + "_active"
        data = cache.get(cache_key)
        if data:
            return data

        qs = super().get_queryset().filter(is_deleted=False)
        products = list(qs)
        cache.set(cache_key, products, timeout=60 * 5)
        return products

    def with_deleted(self):
        """Include deleted items when needed."""
        return super().get_queryset()

    def get_cache_key(self):
        return "product_manager"


class OptionSet(UpdateRecordModel):
    name = models.CharField(max_length=50, blank=False, unique=True)
    products = models.ManyToManyField(
        Product,
        related_name="option_sets",
    )
    options = models.ManyToManyField(
        Option,
        related_name="option_sets",
    )

    def __str__(self):
        return self.name
