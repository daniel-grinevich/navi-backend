from django.apps import AppConfig


class DevicesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "navi_backend.devices"

    def ready(self):
        import navi_backend.devices.signals  # noqa: F401
