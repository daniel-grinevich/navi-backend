from django.contrib import admin
from .models import (
    MenuItem,
    Order,
    OrderItem,
    OrderCustomization,
    Category,
    PaymentType,
    NaviPort,
    RasberryPi,
    MachineType,
    EspressoMachine,
    CustomizationGroup,
)

# Register your models here.
admin.site.register(MenuItem)
admin.site.register(Order)
admin.site.register(OrderItem)
admin.site.register(OrderCustomization)
admin.site.register(Category)
admin.site.register(PaymentType)
admin.site.register(NaviPort)
admin.site.register(EspressoMachine)
admin.site.register(RasberryPi)
admin.site.register(MachineType)
admin.site.register(CustomizationGroup)
