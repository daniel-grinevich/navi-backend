# --- Builder stage ---
FROM docker.io/python:3.14-slim-bookworm AS python

FROM python AS builder
ARG BUILD_ENVIRONMENT=local

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install --no-install-recommends -y \
  build-essential \
  libpq-dev

RUN pip install --upgrade pip

COPY ./requirements .
RUN pip install --no-cache-dir -r ${BUILD_ENVIRONMENT}.txt

# --- Runner stage ---
FROM python AS runner
ARG APP_HOME=/app

WORKDIR ${APP_HOME}

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install --no-install-recommends -y \
  libpq5 \
  && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.14/site-packages/ /usr/local/lib/python3.14/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# Scripts + app code
COPY ./compose/production/django/entrypoint /entrypoint
RUN sed -i 's/\r$//g' /entrypoint && chmod +x /entrypoint

COPY ./compose/local/django/start /start
RUN sed -i 's/\r$//g' /start && chmod +x /start

COPY ./compose/local/django/celery/worker/start /start-celeryworker
RUN sed -i 's/\r$//g' /start-celeryworker && chmod +x /start-celeryworker

COPY ./compose/local/django/celery/beat/start /start-celerybeat
RUN sed -i 's/\r$//g' /start-celerybeat && chmod +x /start-celerybeat

COPY ./compose/local/django/celery/flower/start /start-flower
RUN sed -i 's/\r$//g' /start-flower && chmod +x /start-flower

COPY . ${APP_HOME}

ENTRYPOINT ["/entrypoint"]
