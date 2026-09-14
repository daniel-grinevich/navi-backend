from celery import Celery

app = Celery("navi_backend")

# Using a string means the worker doesn't have to serialize
# the configuration object to child processes
app.config_from_object("django.conf:settings", namespace="CELERY")

# Load tasks from all registered Django app configs
app.autodiscover_tasks()

# Registers signal handlers: request-id propagation into task headers and
# dictConfig-based worker logging (stops Celery hijacking the root logger)
from navi_backend.core.logging import celery as _celery_logging  # noqa: E402, F401
