from django.contrib import admin

from navi_backend.notifications.models import EmailLog
from navi_backend.notifications.models import NotificationSettings
from navi_backend.notifications.models import NotificationSettingsChange
from navi_backend.notifications.services.global_settings import diff_switches
from navi_backend.notifications.services.global_settings import record_change

admin.site.register(EmailLog)


@admin.register(NotificationSettings)
class NotificationSettingsAdmin(admin.ModelAdmin):
    fields = (
        "email_enabled",
        "sms_enabled",
        "order_updates_enabled",
        "marketing_enabled",
        "rewards_enabled",
        "updated_at",
        "updated_by",
    )
    readonly_fields = ("updated_at", "updated_by")
    list_display = (
        "__str__",
        "email_enabled",
        "sms_enabled",
        "order_updates_enabled",
        "marketing_enabled",
        "rewards_enabled",
        "updated_at",
        "updated_by",
    )

    def has_add_permission(self, request):
        # Singleton: only ever one row.
        return not NotificationSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        # Audit admin edits the same way as API edits.
        before = NotificationSettings.load()
        changes = diff_switches(before, obj)
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)
        if changes:
            record_change(
                actor=request.user,
                changes=changes,
                source=NotificationSettingsChange.Source.DJANGO_ADMIN,
            )


@admin.register(NotificationSettingsChange)
class NotificationSettingsChangeAdmin(admin.ModelAdmin):
    list_display = ("changed_at", "changed_by", "source", "changes")
    list_filter = ("source",)
    readonly_fields = ("changed_at", "changed_by", "source", "changes")

    # Append-only audit trail.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
