"""Celery signal handlers for log context propagation and worker logging.

Import-light on purpose: this module is imported from config/celery.py, which
loads in every Django process — no Django models here.
"""

import logging.config

from celery.signals import before_task_publish
from celery.signals import setup_logging
from celery.signals import task_postrun
from celery.signals import task_prerun
from django.conf import settings

from navi_backend.core.logging.context import clear_log_ctx
from navi_backend.core.logging.context import get_log_ctx
from navi_backend.core.logging.context import init_log_ctx
from navi_backend.core.logging.context import set_log_ctx_key


@before_task_publish.connect
def propagate_request_id(headers=None, **kwargs):
    """Carry the enqueuing request's id into the task message headers."""
    request_id = get_log_ctx().get("request_id")
    if request_id and headers is not None:
        headers["request_id"] = request_id


@task_prerun.connect
def bind_task_context(task_id=None, task=None, **kwargs):
    init_log_ctx()
    set_log_ctx_key("task_id", task_id)
    set_log_ctx_key("task_name", task.name if task else None)
    request_id = getattr(task.request, "request_id", None) if task else None
    if request_id:
        set_log_ctx_key("request_id", request_id)


@task_postrun.connect
def clear_task_context(**kwargs):
    clear_log_ctx()


@setup_logging.connect
def configure_worker_logging(**kwargs):
    """Apply Django's LOGGING config in the worker.

    Connecting this signal is also what stops Celery hijacking the root
    logger with its own format.
    """
    logging.config.dictConfig(settings.LOGGING)
