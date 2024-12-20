from django.db import models
from django.utils.text import slugify
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
    STATUS_CHOICES = (
        ("A", "Active"),
        ("I", "Inactive"),
    )
    name = models.CharField(max_length=50, blank=False, unique=True)
    slug = models.SlugField(unique=True, blank=False)
    price = models.DecimalField(decimal_places=2, max_digits=8)
    description = models.CharField(max_length=100)
    body = models.TextField(blank=False)
    status = models.CharField(
        max_length=1,
        choices=STATUS_CHOICES,
        default="A",
    )
    image = models.ImageField(upload_to="option_images/", blank=True, null=True)

    class Meta:
        ordering = ['name']
        
    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Product(UpdateRecordModel):
    STATUS_CHOICES = (
        ("A", "Active"),
        ("I", "Inactive"),
    )
    name = models.CharField(max_length=50, blank=False, unique=True)
    slug = models.SlugField(unique=True, blank=False)
    price = models.DecimalField(decimal_places=2, max_digits=8)
    description = models.CharField(max_length=100)
    body = models.TextField(blank=False)
    status = models.CharField(
        max_length=1,
        choices=STATUS_CHOICES,
        default="A",
    )
    image = models.ImageField(upload_to="product_images/")

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class OptionSet(UpdateRecordModel):
    name = models.CharField(max_length=50, blank=False, unique=True)
    products = models.ManyToManyField(
        Product,
        related_name="option_sets"
    )
    options = models.ManyToManyField(
        Option,
        related_name="option_sets"
    )

    def __str__(self):
        return self.name
    

# def save(self, *args, **kwargs):
#         if not self.slug or self.name != self._state.fields_cache.get('name'):
#             self.slug = slugify(self.name)
#         super().save(*args, **kwargs)