from django.contrib import admin

from .models import EspressoMachine
from .models import MachineType
from .models import NaviPort
from .models import RaspberryPi


@admin.register(RaspberryPi)
class RaspberryPiAdmin(admin.ModelAdmin):
    list_display = ("name", "mac_address", "is_connected", "is_online", "last_seen")
    readonly_fields = ("last_seen", "device_token")

    @admin.display(boolean=True, description="Online")
    def is_online(self, obj):
        return obj.is_online


admin.site.register(NaviPort)
admin.site.register(EspressoMachine)
admin.site.register(MachineType)
