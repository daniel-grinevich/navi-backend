from celery import Celery
from django.conf import settings

app = Celery("navi_backend")

# Using a string means the worker doesn't have to serialize
# the configuration object to child processes
app.config_from_object("django.conf:settings", namespace="CELERY")

# Load tasks from all registered Django app configs
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)


@app.task
def divide(x, y):
    import time

    time.sleep(5)
    return x / y
