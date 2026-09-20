import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

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

        super().save(*args, **kwargs)

        # The address is already populated (provided by the caller or a prior
        # geocode); nothing more to do.
        if self.address_line_1 and self.city and self.postal_code:
            return

        # Reverse-geocode in the background so the write path never blocks on the
        # external geocoder. Imported here to avoid a models <-> tasks import
        # cycle at module load.
        from navi_backend.core.tasks import populate_address_from_geo  # noqa: PLC0415

        transaction.on_commit(
            lambda: populate_address_from_geo.delay(
                self._meta.app_label,
                self._meta.model_name,
                self.pk,
            ),
        )


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
        _("status"),
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
