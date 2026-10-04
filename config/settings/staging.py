from .base import *  # noqa: F403
from .base import DATABASES
from .base import REDIS_URL
from .base import S3_MEDIA_STORAGE
from .base import SIMPLE_JWT
from .base import env
from .sentry import init_sentry

DEBUG = True

# Stamped onto every log line (see StaticFieldsFilter); LOGGING is inherited
# from base, which reads this value.
ENVIRONMENT = "staging"

# Secret key comes from the environment (Infisical -> ESO -> envFrom at runtime).
# The throwaway default lets build/CI steps that import settings without the real
# secret (e.g. collectstatic) succeed; it is never used to serve real requests.
SECRET_KEY = env("DJANGO_SECRET_KEY", default="temporary-build-only-key")

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")

CORS_ALLOWED_ORIGINS = env.list("DJANGO_CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = "None"
CSRF_COOKIE_SAMESITE = "None"

# JWT auth cookies must match the cross-site posture above: SameSite=None
# requires Secure, and base.py defaults both to the local-dev values.
SIMPLE_JWT["AUTH_COOKIE_SECURE"] = True
SIMPLE_JWT["AUTH_COOKIE_SAMESITE"] = "None"

DATABASES["default"]["CONN_MAX_AGE"] = env.int("CONN_MAX_AGE", default=60)

CACHES = {
    "default": {
        # django_redis wrapped with Prometheus cache hit/miss metrics
        "BACKEND": "django_prometheus.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "IGNORE_EXCEPTIONS": True,
        },
    },
}

STORAGES = {
    # User media/uploads -> in-cluster MinIO (S3-compatible; R2 is prod-only)
    "default": S3_MEDIA_STORAGE,
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Navi Backend API (Staging)",
    "DESCRIPTION": "Staging environment API documentation",
    "VERSION": "1.0.0",
    "SERVE_PERMISSIONS": ["rest_framework.permissions.IsAuthenticated"],
    "SCHEMA_PATH_PREFIX": "/api/",
    "SWAGGER_UI_SETTINGS": {
        "deepLinking": True,
        "persistAuthorization": True,
        "displayOperationId": True,
    },
    "COMPONENT_SPLIT_REQUEST": True,
    "SORT_OPERATIONS": False,
}

ADMIN_URL = env("DJANGO_ADMIN_URL")

# EMAIL -> Mailpit (in-cluster SMTP catcher)
# ------------------------------------------------------------------------------
# Mailpit accepts all mail on :1025 (no auth/TLS) and shows it in its web UI, so
# staging never sends real email to customers. See rainbow-road/mailpit.
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", default="mailpit.mailpit.svc")
EMAIL_PORT = env.int("EMAIL_PORT", default=1025)
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=False)
DEFAULT_FROM_EMAIL = env(
    "DJANGO_DEFAULT_FROM_EMAIL",
    default="Navi Staging <noreply@staging.navitascoffee.com>",
)

ENVIRONMENT_NAME = "Staging"

# Sentry — no-op unless SENTRY_DSN is set. Tracing defaults off in staging to
# keep the free-tier quota for production.
SENTRY_DSN = env("SENTRY_DSN", default="")
if SENTRY_DSN:
    init_sentry(
        dsn=SENTRY_DSN,
        environment=ENVIRONMENT,
        release=env("SENTRY_RELEASE", default=""),
        traces_sample_rate=env.float("SENTRY_TRACES_SAMPLE_RATE", default=0.0),
    )
