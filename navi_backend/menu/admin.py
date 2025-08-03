from django.contrib import admin

from .models import Category
from .models import Customization
from .models import CustomizationGroup
from .models import Ingredient
from .models import MenuItem
from .models import MenuItemIngredient

admin.site.register(CustomizationGroup)
admin.site.register(Customization)
admin.site.register(Category)
admin.site.register(MenuItem)
admin.site.register(Ingredient)
admin.site.register(MenuItemIngredient)
