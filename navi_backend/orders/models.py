from django.db import models
from django.utils.text import slugify

from users.models import User


# Create your models here.
class Category(models.Model):

    name = models.CharField(max_length=200, null=True, blank=True)
    slug = models.SlugField(unique=True, blank=False)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        return super().save(*args, **kwargs)


class MenuItem(models.Model):
    name = models.CharField(max_length=200, null=True, blank=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True)
    description = models.TextField(null=True, blank=True)
    price = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    image = models.ImageField(upload_to="product_images/")
    createdAt = models.DateTimeField(auto_now_add=True)
    slug = models.SlugField(unique=True, blank=False)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        return super().save(*args, **kwargs)


class Order(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    paymentMethod = models.CharField(max_length=200, null=True, blank=True)
    totalPrice = models.DecimalField(
        max_digits=7, decimal_places=2, null=True, blank=True
    )
    createdAt = models.DateTimeField(auto_now_add=True)
    slug = models.SlugField(unique=True, blank=False)

    def __str__(self):
        return str(self.createdAt)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        return super().save(*args, **kwargs)


class OrderItem(models.Model):
    menu_item = models.ForeignKey(MenuItem, on_delete=models.SET_NULL, null=True)
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True)
    name = models.CharField(max_length=200, null=True, blank=True)
    qty = models.IntegerField(null=True, blank=True, default=1)
    price = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    slug = models.SlugField(unique=True, blank=False)

    def __str__(self):
        return str(self.name)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        return super().save(*args, **kwargs)


class CustomizationType(models.Model):
    name = models.CharField(max_length=200, null=True, blank=True)
    slug = models.SlugField(unique=True, blank=False)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        return super().save(*args, **kwargs)


class Customization(models.Model):
    name = models.CharField(max_length=200, null=True, blank=True)
    order_item = models.ForeignKey(OrderItem, on_delete=models.SET_NULL, null=True)
    customization_type = models.ForeignKey(
        CustomizationType, on_delete=models.SET_NULL, null=True
    )
    qty = models.IntegerField(null=True, blank=True, default=0)
    slug = models.SlugField(unique=True, blank=False)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        return super().save(*args, **kwargs)
