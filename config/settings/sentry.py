"""Shared Sentry initialization for staging and production settings."""

import logging

import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.redis import RedisIntegration


def init_sentry(
    *,
    dsn: str,
    environment: str,
    release: str = "",
    traces_sample_rate: float = 0.0,
) -> None:
    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=release or None,
        integrations=[
            DjangoIntegration(),
            CeleryIntegration(),
            RedisIntegration(),
            # Breadcrumbs from INFO logs; ERROR logs become Sentry events.
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
        traces_sample_rate=traces_sample_rate,
        # Auth lives in HttpOnly cookies — never ship cookies/PII to Sentry.
        send_default_pii=False,
    )
