from django.db import models
from django.utils.text import slugify

from navi_backend.users.models import User


class UpdateRecordModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="created_users",
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="updated_users",
    )

    class Meta:
        abstract = True


class Product(UpdateRecordModel):
    ACTIVE = "A"
    INACTIVE = "I"
    STATUS_CHOICES = {
        ACTIVE: "active",
        INACTIVE: "inactive",
    }
    name = models.CharField(max_length=50, blank=False, unique=True)
    slug = models.SlugField(unique=True, blank=False)
    price = models.DecimalField(decimal_places=2, max_digits=8)
    description = models.CharField(max_length=100)
    body = models.TextField(blank=False)
    status = models.CharField(
        max_length=1,
        choices=STATUS_CHOICES,
        default=ACTIVE,
    )
    image = models.ImageField(upload_to="product_images/")

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        return super().save(*args, **kwargs)
