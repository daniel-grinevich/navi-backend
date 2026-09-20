from django.apps import AppConfig


class MenuConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "navi_backend.menu"

    def ready(self):
        import navi_backend.menu.signals  # noqa: F401
