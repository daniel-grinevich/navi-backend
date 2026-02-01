import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from navi_backend.core.helpers.geo_cache import send_geo_request
from navi_backend.users.models import User


class UUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class AddressModel(models.Model):
    address_line_1 = models.CharField(
        _("Address line 1"), max_length=255, blank=True, unique=False
    )
    address_line_2 = models.CharField(
        _("Address line 2"), max_length=255, blank=True, unique=False
    )
    address_line_3 = models.CharField(
        _("Address line 3"), max_length=255, blank=True, unique=False
    )
    city = models.CharField(_("City"), max_length=255, unique=False, blank=True)
    state_or_region = models.CharField(
        _("State or region"), max_length=255, blank=True, unique=False
    )
    postal_code = models.CharField(
        _("Postal code"), max_length=255, blank=True, unique=False
    )
    country = models.CharField(
        _("Country"),
        max_length=2,
        blank=True,
        default="US",
        help_text="ISO 3166-1 alpha-2 country code",
    )

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self.latitude or not self.longitude:
            err = "longitude and latitude must be defined for address model"
            raise NotImplementedError(err)

        if self.address_line_1 and self.city and self.postal_code:
            super().save(*args, **kwargs)
            return

        response = send_geo_request(self.latitude, self.longitude)
        address_info = response.get("address", {})

        if not address_info:
            err = "address_info is empty."
            raise ValueError(err)

        road = address_info.get("road", "")
        address_parts = road.split(",") if road else []

        for index, part in enumerate(address_parts):
            str_part = part.strip()

            if index == 0:
                house_number = address_info.get("house_number", "")
                self.address_line_1 = f"{house_number} {str_part}".strip()
            elif index == 1:
                self.address_line_2 = str_part
            elif not self.address_line_3:
                self.address_line_3 = str_part
            else:
                self.address_line_3 += f", {str_part}"

        self.city = address_info.get("city", "")
        self.state_or_region = address_info.get("state", "")
        self.postal_code = address_info.get("postcode", "")
        if not self.country:
            self.country = address_info.get("country_code", "US").upper()

        super().save(*args, **kwargs)


class NamedModel(models.Model):
    name = models.CharField(
        _("Name"),
        max_length=200,
        unique=True,
        db_index=True,
        help_text=_("Unique name"),
    )

    class Meta:
        abstract = True

    def __str__(self):
        return self.name


class SlugifiedModel(models.Model):
    slug = models.SlugField(
        _("Slug"),
        unique=True,
        max_length=200,
        db_index=True,
        help_text=_("URL-friendly version of name"),
    )

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self.slug:
            try:
                self.slug = slugify(self.name)
            except (AttributeError, TypeError):
                self.slug = slugify(str(uuid.uuid4())[:8])
        self.full_clean()
        return super().save(*args, **kwargs)


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


class AuditModel(UpdateRecordModel):
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
        blank=True,
        default="",
        editable=False,
    )

    class Meta:
        abstract = True

    @property
    def is_active(self):
        return self.status == self.Status.ACTIVE and not self.is_deleted

    def activate(self):
        if self.is_deleted:
            raise ValidationError(_("Cannot activate deleted menuitem."))
        self.status = self.Status.ACTIVE
        self.save(update_fields=["status", "updated_at"])

    def archive(self):
        self.status = self.Status.ARCHIVED
        self.save(update_fields=["status", "updated_at"])

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
            ]
        )

    def restore(self):
        if not self.is_deleted:
            raise ValidationError(_("Cannot restore non-deleted menuitem."))
        self.is_deleted = False
        self.deleted_at = None
        self.save(
            update_fields=[
                "is_deleted",
                "deleted_at",
                "updated_at",
            ]
        )

    def clean(self):
        if self.is_deleted and self.status == self.Status.ACTIVE:
            raise ValidationError({"status": _("Deleted menuitem cannot be active.")})
