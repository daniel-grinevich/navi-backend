from django.conf import settings
from django.contrib import admin
from django.contrib import messages

from .models import DeviceEvent
from .models import EspressoMachine
from .models import MachineType
from .models import NaviPort
from .models import RaspberryPi
from .services import fleet


@admin.register(RaspberryPi)
class RaspberryPiAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "mac_address",
        "is_connected",
        "is_online",
        "last_seen",
        "is_simulated",
    )
    list_filter = ("is_connected", "is_simulated")
    search_fields = ("name", "mac_address", "location")
    readonly_fields = ("last_seen", "firmware_version")
    actions = ("rotate_device_token",)

    @admin.display(boolean=True, description="Online")
    def is_online(self, obj):
        return obj.is_online

    def save_model(self, request, obj, form, change):
        token = obj.issue_token() if not obj.token_hash else None
        super().save_model(request, obj, form, change)
        if token:
            self.message_user(
                request,
                f"Device token for {obj.name} (shown only once): {token}",
                level=messages.WARNING,
            )

    @admin.action(description="Rotate device token (shows the new token once)")
    def rotate_device_token(self, request, queryset):
        for pi in queryset:
            token = fleet.rotate_token(pi, actor=request.user)
            self.message_user(
                request, f"New token for {pi.name}: {token}", level=messages.WARNING
            )


@admin.register(DeviceEvent)
class DeviceEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "raspberry_pi", "type", "message")
    list_filter = ("type",)
    list_select_related = ("raspberry_pi",)
    search_fields = ("raspberry_pi__name", "message")
    readonly_fields = (
        "raspberry_pi",
        "type",
        "message",
        "payload",
        "actor",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


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
