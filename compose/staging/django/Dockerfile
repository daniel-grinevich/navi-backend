# --- Builder stage ---
FROM docker.io/python:3.14-slim-bookworm AS python

FROM python AS builder

ARG BUILD_ENVIRONMENT=staging

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.6.3 /uv /usr/local/bin/uv

RUN apt-get update && apt-get install --no-install-recommends -y \
  build-essential \
  libpq-dev

COPY ./requirements .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system -r ${BUILD_ENVIRONMENT}.txt

# --- Runner stage ---
FROM python AS runner
ARG APP_HOME=/app

WORKDIR ${APP_HOME}

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

RUN addgroup --system django \
    && adduser --system --ingroup django django

RUN apt-get update && apt-get install --no-install-recommends -y \
  libpq5 \
  gettext \
  wait-for-it \
  libpango-1.0-0 \
  libpangocairo-1.0-0 \
  libgdk-pixbuf2.0-0 \
  libffi-dev \
  shared-mime-info \
  fonts-liberation \
  && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
  && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.14/site-packages/ /usr/local/lib/python3.14/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# Scripts
COPY ./compose/staging/django/entrypoint /entrypoint
COPY ./compose/staging/django/start /start
COPY ./compose/staging/django/celery/worker/start /start-celeryworker
COPY ./compose/staging/django/celery/beat/start /start-celerybeat
COPY ./compose/staging/django/celery/flower/start /start-flower
RUN sed -i 's/\r$//g' /entrypoint /start /start-celeryworker /start-celerybeat /start-flower \
    && chmod +x /entrypoint /start /start-celeryworker /start-celerybeat /start-flower

COPY --chown=django:django . ${APP_HOME}
RUN chown -R django:django ${APP_HOME}

USER django

ENTRYPOINT ["/entrypoint"]
