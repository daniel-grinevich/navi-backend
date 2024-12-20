from django.contrib import admin

from navi_backend.fakeapi.models import Product, Option, OptionSet

# Register your models here.
admin.site.register(Product)
admin.site.register(Option)
admin.site.register(OptionSet)
