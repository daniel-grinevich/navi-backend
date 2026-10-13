from django.conf import settings
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


@admin.register(NaviPort)
class NaviPortAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "slug",
        "accepting_orders",
        "status_message",
        "is_online",
    )
    list_editable = ("accepting_orders", "status_message")
    list_filter = ("accepting_orders",)
    search_fields = ("name", "slug")
    readonly_fields = ("sticker_url",)

    @admin.display(boolean=True, description="Online")
    def is_online(self, obj):
        return obj.is_online

    @admin.display(description="Sticker URL")
    def sticker_url(self, obj):
        """What the QR sticker on this machine should encode."""
        if not obj.slug:
            return "-"
        return f"{settings.FRONTEND_URL.rstrip('/')}/p/{obj.slug}"


admin.site.register(EspressoMachine)
admin.site.register(MachineType)
