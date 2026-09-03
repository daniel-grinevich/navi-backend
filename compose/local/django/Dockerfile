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

# uv is the single source of truth for dependencies (pyproject.toml + uv.lock).
RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
# Local image includes the dev group (pytest, ruff, debugpy, ...).
RUN --mount=type=cache,target=/root/.cache/uv \
    uv export --frozen --no-emit-project --no-hashes -o requirements.txt \
    && uv pip install --system -r requirements.txt

# --- Runner stage ---
FROM python AS runner
ARG APP_HOME=/app

WORKDIR ${APP_HOME}

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install --no-install-recommends -y \
  libpq5 \
  libpango-1.0-0 \
  libpangocairo-1.0-0 \
  libgdk-pixbuf2.0-0 \
  libffi-dev \
  shared-mime-info \
  fonts-liberation \
  && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.14/site-packages/ /usr/local/lib/python3.14/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# Scripts + app code
 COPY ./compose/production/django/entrypoint /entrypoint
 COPY ./compose/local/django/start /start
 COPY ./compose/local/django/celery/worker/start /start-celeryworker
 COPY ./compose/local/django/celery/beat/start /start-celerybeat
 COPY ./compose/local/django/celery/flower/start /start-flower
 RUN sed -i 's/\r$//g' /entrypoint /start /start-celeryworker /start-celerybeat /start-flower \
     && chmod +x /entrypoint /start /start-celeryworker /start-celerybeat /start-flower

COPY . ${APP_HOME}

ENTRYPOINT ["/entrypoint"]
