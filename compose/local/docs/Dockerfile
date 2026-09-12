# define an alias for the specific python version used in this file.
# Matches the project's requires-python (== 3.14.*) so the uv lock resolves.
FROM docker.io/python:3.14-slim-bookworm AS python


# Python build stage
FROM python AS python-build-stage

ENV PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install --no-install-recommends -y \
  # dependencies for building Python packages
  build-essential \
  # psycopg dependencies
  libpq-dev \
  # cleaning up unused files
  && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
  && rm -rf /var/lib/apt/lists/*

# uv is the single source of truth for dependencies (pyproject.toml + uv.lock).
RUN pip install --no-cache-dir uv

# Docs need the full set including the dev group (sphinx). Export from the lock
# and build wheels.
COPY pyproject.toml uv.lock /
RUN uv export --frozen --no-emit-project --no-hashes -o /requirements.txt \
  && pip wheel --no-cache-dir --wheel-dir /usr/src/app/wheels -r /requirements.txt \
  && rm -f /requirements.txt /pyproject.toml /uv.lock


# Python 'run' stage
FROM python AS python-run-stage

ARG BUILD_ENVIRONMENT
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install --no-install-recommends -y \
  # To run the Makefile
  make \
  # psycopg dependencies
  libpq-dev \
  # Translations dependencies
  gettext \
  # Uncomment below lines to enable Sphinx output to latex and pdf
  # texlive-latex-recommended \
  # texlive-fonts-recommended \
  # texlive-latex-extra \
  # latexmk \
  # cleaning up unused files
  && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
  && rm -rf /var/lib/apt/lists/*

# copy python dependency wheels from python-build-stage
COPY --from=python-build-stage /usr/src/app/wheels /wheels

# use wheels to install python dependencies
RUN pip install --no-cache /wheels/* \
  && rm -rf /wheels

COPY ./compose/local/docs/start /start-docs
RUN sed -i 's/\r$//g' /start-docs
RUN chmod +x /start-docs

WORKDIR /docs
