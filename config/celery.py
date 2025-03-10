import os

from celery import Celery

# Set the default Django settings module
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

app = Celery("navi_backend")

# Using a string means the worker doesn't have to serialize
# the configuration object to child processes
app.config_from_object("django.conf:settings", namespace="CELERY")

# Load tasks from all registered Django app configs
app.autodiscover_tasks()
