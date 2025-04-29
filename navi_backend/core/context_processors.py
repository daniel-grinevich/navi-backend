from django.conf import settings


def env_banner(request):
    return {"ENVIRONMENT_NAME": getattr(settings, "ENVIRONMENT_NAME", "")}
