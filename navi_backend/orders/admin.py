from django.contrib import admin
from .models import (
    MenuItem,
    Order,
    OrderItem,
    OrderCustomization,
    Category,
    PaymentType,
    Port,
    CustomizationGroup,
)

# Register your models here.
admin.site.register(MenuItem)
admin.site.register(Order)
admin.site.register(OrderItem)
admin.site.register(OrderCustomization)
admin.site.register(Category)
admin.site.register(PaymentType)
admin.site.register(Port)
admin.site.register(CustomizationGroup)
