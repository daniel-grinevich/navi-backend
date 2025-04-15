from .base import *
from .base import DATABASES
from .base import INSTALLED_APPS
from .base import REDIS_URL
from .base import env

DEBUG = True

# Read secret key from file
try:
    with open(env("DJANGO_SECRET_KEY_FILE")) as f:
        SECRET_KEY = f.read().strip()
except Exception:
    SECRET_KEY = "temporary-build-only-key"

# Only allow host from traefik.
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[""])


DATABASES["default"]["CONN_MAX_AGE"] = env.int("CONN_MAX_AGE", default=60)

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "IGNORE_EXCEPTIONS": True,
        },
    },
}

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Navi Backend API (Staging)",
    "DESCRIPTION": "Staging environment API documentation",
    "VERSION": "1.0.0",
    # Allow authenticated users to view docs in staging
    "SERVE_PERMISSIONS": ["rest_framework.permissions.IsAuthenticated"],
    "SCHEMA_PATH_PREFIX": "/api/",
    # Additional settings for staging
    "SWAGGER_UI_SETTINGS": {
        "deepLinking": True,
        "persistAuthorization": True,
        "displayOperationId": True,
    },
    "COMPONENT_SPLIT_REQUEST": True,
    "SORT_OPERATIONS": False,
}

ADMIN_URL = env("DJANGO_ADMIN_URL")

INSTALLED_APPS += ["anymail"]

EMAIL_BACKEND = "anymail.backends.mailgun.EmailBackend"
ANYMAIL = {
    "MAILGUN_API_KEY": env("MAILGUN_API_KEY"),
    "MAILGUN_SENDER_DOMAIN": env("MAILGUN_DOMAIN"),
    "MAILGUN_API_URL": env("MAILGUN_API_URL", default="https://api.mailgun.net/v3"),
}
