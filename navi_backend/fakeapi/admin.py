from django.contrib import admin

from navi_backend.fakeapi.models import Option
from navi_backend.fakeapi.models import OptionSet
from navi_backend.fakeapi.models import Product

# Register your models here.
admin.site.register(Product)
admin.site.register(Option)
admin.site.register(OptionSet)
