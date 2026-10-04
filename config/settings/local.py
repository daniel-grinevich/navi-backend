from .base import *  # noqa: F403
from .base import INSTALLED_APPS
from .base import LOGGING
from .base import MIDDLEWARE
from .base import REDIS_URL
from .base import S3_MEDIA_STORAGE
from .base import env

# GENERAL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#debug
DEBUG = True
# https://docs.djangoproject.com/en/dev/ref/settings/#secret-key
SECRET_KEY = env(
    "DJANGO_SECRET_KEY",
    default="z4pfSFJ7kk7q0lg2dOeRWmnyurCwGt4f0e4hBZMQ5yFby0pPDXEIxUMFcMI1LNw4",
)
# https://docs.djangoproject.com/en/dev/ref/settings/#allowed-hosts
ALLOWED_HOSTS = ["localhost", "0.0.0.0", "127.0.0.1", "django"]  # noqa: S104

# ADMIN URL
ADMIN_URL = env("DJANGO_ADMIN_URL")

# CACHES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#caches
# Redis, matching staging/production: LocMem is per-process, so with more
# than one worker (or Celery) cache invalidation and stampede locks silently
# stop being shared. The local stack already runs Redis.
CACHES = {
    "default": {
        # django_redis wrapped with Prometheus cache hit/miss metrics
        "BACKEND": "django_prometheus.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    },
}

# EMAIL -> Mailpit (docker-compose.local.yml)
# ------------------------------------------------------------------------------
# SMTP to the local Mailpit container (catches all mail, web UI at :8025), same
# backend as staging/production. Override DJANGO_EMAIL_BACKEND=...console... if
# you'd rather have emails printed to the runserver output instead.
# https://docs.djangoproject.com/en/dev/ref/settings/#email-backend
EMAIL_BACKEND = env(
    "DJANGO_EMAIL_BACKEND",
    default="django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_HOST = env("EMAIL_HOST", default="mailpit")
EMAIL_PORT = env.int("EMAIL_PORT", default=1025)
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=False)

# WhiteNoise
# ------------------------------------------------------------------------------
# http://whitenoise.evans.io/en/latest/django.html#using-whitenoise-in-development
INSTALLED_APPS = ["whitenoise.runserver_nostatic", *INSTALLED_APPS]


# django-debug-toolbar
# ------------------------------------------------------------------------------
# https://django-debug-toolbar.readthedocs.io/en/latest/installation.html#prerequisites
INSTALLED_APPS += ["debug_toolbar"]
# https://django-debug-toolbar.readthedocs.io/en/latest/installation.html#middleware
MIDDLEWARE += ["debug_toolbar.middleware.DebugToolbarMiddleware"]
# https://django-debug-toolbar.readthedocs.io/en/latest/configuration.html#debug-toolbar-config
DEBUG_TOOLBAR_CONFIG = {
    "DISABLE_PANELS": [
        "debug_toolbar.panels.redirects.RedirectsPanel",
        # Disable profiling panel due to an issue with Python 3.12:
        # https://github.com/jazzband/django-debug-toolbar/issues/1875
        "debug_toolbar.panels.profiling.ProfilingPanel",
    ],
    "SHOW_TEMPLATE_CONTEXT": True,
}
# https://django-debug-toolbar.readthedocs.io/en/latest/installation.html#internal-ips
INTERNAL_IPS = ["127.0.0.1", "10.0.2.2"]
if env("USE_DOCKER") == "yes":
    import socket

    hostname, _, ips = socket.gethostbyname_ex(socket.gethostname())
    INTERNAL_IPS += [".".join([*ip.split(".")[:-1], "1"]) for ip in ips]

# django-extensions
# ------------------------------------------------------------------------------
# https://django-extensions.readthedocs.io/en/latest/installation_instructions.html#configuration
INSTALLED_APPS += ["django_extensions"]


# Cors origins allow our local dev
CORS_ALLOW_CREDENTIALS = True

CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

CORS_ALLOW_METHODS = [
    "GET",
    "POST",
    "PUT",
    "PATCH",
    "DELETE",
    "OPTIONS",
]

# CORS_ALLOW_HEADERS comes from base.py (default_headers + X-Request-ID +
# Idempotency-Key)

# LOGGING
# ------------------------------------------------------------------------------
# Human-readable one-liners in dev; staging/production keep base's JSON lines.
LOGGING["handlers"]["console"]["formatter"] = "plain"  # type: ignore[index]

# STORAGES -> local MinIO (S3-compatible), matching staging/production
# ------------------------------------------------------------------------------
# Same backend + settings as base/staging/prod (private bucket, presigned URLs via
# base's AWS_QUERYSTRING_AUTH=True) — just pointed at the docker-compose MinIO with
# local defaults. Keeps dev/prod parity so signed-URL behavior is exercised locally.
AWS_ACCESS_KEY_ID = env("S3_ACCESS_KEY_ID", default="minioadmin")
AWS_SECRET_ACCESS_KEY = env("S3_SECRET_ACCESS_KEY", default="minioadmin")
AWS_STORAGE_BUCKET_NAME = env("S3_BUCKET_NAME", default="navi-local-media")
AWS_S3_ENDPOINT_URL = env("S3_ENDPOINT_URL", default="http://minio:9000")
AWS_S3_REGION_NAME = env("S3_REGION", default="us-east-1")
STORAGES = {
    "default": S3_MEDIA_STORAGE,
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}
