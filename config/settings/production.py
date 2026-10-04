from .base import *  # noqa: F403
from .base import DATABASES
from .base import LOGGING
from .base import REDIS_URL
from .base import S3_MEDIA_STORAGE
from .base import SIMPLE_JWT
from .base import SPECTACULAR_SETTINGS
from .base import env
from .sentry import init_sentry

# GENERAL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#secret-key
SECRET_KEY = env("DJANGO_SECRET_KEY")
# https://docs.djangoproject.com/en/dev/ref/settings/#allowed-hosts
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["navitascoffee.com"])

# Prometheus scrapes /metrics at the pod IP, so the Host header is that IP.
# POD_IP comes from the Downward API (rainbow-road navi/base/navi-api.yaml).
if POD_IP := env("POD_IP", default=""):
    ALLOWED_HOSTS.append(POD_IP)

# CORS / CSRF
# ------------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env.list(
    "DJANGO_CORS_ALLOWED_ORIGINS",
    default=["https://navitascoffee.com"],
)
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = env.list(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    default=["https://navitascoffee.com", "https://api.navitascoffee.com"],
)

# DATABASES
# ------------------------------------------------------------------------------
DATABASES["default"]["CONN_MAX_AGE"] = env.int("CONN_MAX_AGE", default=60)

# CACHES
# ------------------------------------------------------------------------------
CACHES = {
    "default": {
        # django_redis wrapped with Prometheus cache hit/miss metrics
        "BACKEND": "django_prometheus.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            # Mimicking memcache behavior.
            # https://github.com/jazzband/django-redis#memcached-exceptions-behavior
            "IGNORE_EXCEPTIONS": True,
        },
    },
}

# SECURITY
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#secure-proxy-ssl-header
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# https://docs.djangoproject.com/en/dev/ref/settings/#secure-ssl-redirect
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
# Prometheus scrapes /metrics over plain HTTP at the pod IP (TLS ends at
# Cloudflare), so redirecting it to https breaks the scrape.
SECURE_REDIRECT_EXEMPT = [r"^metrics$"]
# https://docs.djangoproject.com/en/dev/ref/settings/#session-cookie-secure
SESSION_COOKIE_SECURE = True
# https://docs.djangoproject.com/en/dev/ref/settings/#session-cookie-name
SESSION_COOKIE_NAME = "__Secure-sessionid"
# https://docs.djangoproject.com/en/dev/ref/settings/#csrf-cookie-secure
CSRF_COOKIE_SECURE = True
# https://docs.djangoproject.com/en/dev/ref/settings/#csrf-cookie-name
CSRF_COOKIE_NAME = "__Secure-csrftoken"
# Ensure the JWT access/refresh cookies get the Secure flag too — base.py
# defaults this to False for local HTTP dev.
SIMPLE_JWT["AUTH_COOKIE_SECURE"] = True
# https://docs.djangoproject.com/en/dev/topics/security/#ssl-https
# https://docs.djangoproject.com/en/dev/ref/settings/#secure-hsts-seconds
SECURE_HSTS_SECONDS = 518400
# https://docs.djangoproject.com/en/dev/ref/settings/#secure-hsts-include-subdomains
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool(
    "DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS",
    default=True,
)
# https://docs.djangoproject.com/en/dev/ref/settings/#secure-hsts-preload
SECURE_HSTS_PRELOAD = env.bool("DJANGO_SECURE_HSTS_PRELOAD", default=True)
# https://docs.djangoproject.com/en/dev/ref/middleware/#x-content-type-options-nosniff
SECURE_CONTENT_TYPE_NOSNIFF = env.bool(
    "DJANGO_SECURE_CONTENT_TYPE_NOSNIFF",
    default=True,
)

# STATIC & MEDIA
# ------------------------
STORAGES = {
    # User media/uploads -> Cloudflare R2 (private bucket, presigned URLs)
    "default": S3_MEDIA_STORAGE,
    # Static assets stay on WhiteNoise (served by the app)
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# EMAIL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#default-from-email
DEFAULT_FROM_EMAIL = env(
    "DJANGO_DEFAULT_FROM_EMAIL",
    default="Navi Backend <noreply@navitascoffee.com>",
)
# https://docs.djangoproject.com/en/dev/ref/settings/#server-email
SERVER_EMAIL = env("DJANGO_SERVER_EMAIL", default=DEFAULT_FROM_EMAIL)
# https://docs.djangoproject.com/en/dev/ref/settings/#email-subject-prefix
EMAIL_SUBJECT_PREFIX = env(
    "DJANGO_EMAIL_SUBJECT_PREFIX",
    default="[Navi Backend] ",
)
ACCOUNT_EMAIL_SUBJECT_PREFIX = EMAIL_SUBJECT_PREFIX

# ADMIN
# ------------------------------------------------------------------------------
# Django Admin URL regex.
ADMIN_URL = env("DJANGO_ADMIN_URL")

# EMAIL -> Brevo SMTP relay
# ------------------------------------------------------------------------------
# Uses Django's built-in SMTP backend (no Anymail). Same backend as staging's
# Mailpit — only host/port/creds differ. EMAIL_HOST_PASSWORD is the Brevo SMTP
# KEY (SMTP & API -> SMTP), NOT the API key.
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", default="smtp-relay.brevo.com")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_HOST_USER = env("EMAIL_HOST_USER")  # Brevo SMTP login
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")  # Brevo SMTP key


# LOGGING
# ------------------------------------------------------------------------------
ENVIRONMENT = "production"
# JSON lines to stdout, inherited from base. 500 emails to ADMINS are opt-in
# (they burned the Brevo free tier once); Sentry is the main error alerting.
# Only django.request (500s) mails -- never DisallowedHost, which is scanner noise.
if env.bool("DJANGO_ERROR_EMAILS", default=False):
    LOGGING = {
        **LOGGING,
        "handlers": {
            **LOGGING["handlers"],
            "mail_admins": {
                "level": "ERROR",
                "class": "django.utils.log.AdminEmailHandler",
            },
        },
        "loggers": {
            **LOGGING["loggers"],
            "django.request": {
                "handlers": ["mail_admins"],
                "level": "ERROR",
                "propagate": True,
            },
        },
    }

# django-rest-framework
# -------------------------------------------------------------------------------
# Tools that generate code samples can use SERVERS to point to the correct domain
SPECTACULAR_SETTINGS["SERVERS"] = [
    {"url": "https://navitascoffee.com", "description": "Production server"},
]

# Sentry
# ------------------------------------------------------------------------------
# No-op unless SENTRY_DSN is set.
SENTRY_DSN = env("SENTRY_DSN", default="")
if SENTRY_DSN:
    init_sentry(
        dsn=SENTRY_DSN,
        environment=ENVIRONMENT,
        release=env("SENTRY_RELEASE", default=""),
        traces_sample_rate=env.float("SENTRY_TRACES_SAMPLE_RATE", default=0.1),
    )

# Your stuff...
# ------------------------------------------------------------------------------
