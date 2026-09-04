# CLAUDE.md

Guidance for AI agents (and humans) working in this repository. Keep it short, keep it current — delete rules that stop being true.

## What this is

`navi-backend` — a Django 5.2 / Django REST Framework project (Cookiecutter-Django layout) running on Python 3.14, Postgres, Redis, and Celery. Runs in Docker Compose. Apps live under `navi_backend/` (e.g. `orders`, `payments`, `menu`, `users`, `devices`, `notifications`).

## Git & merge requests

- **This repo (backend): open merge/pull requests against `development`** for most work (features, fixes, refactors).
- **`master` is the protected release branch.** Don't target it for regular feature work — but **CI/CD changes (GitHub Actions, pipeline config) go straight to `master`.**
- **Frontend repo: MRs target `production`.** (Noted here so agents working across both repos don't mix them up.)
- Branch off the appropriate base; never commit directly to `master`.
- Only commit or push when the user asks.

## Releases & deployment

Staging and production run on k3s, deployed via GitOps (kustomize + ArgoCD) from the
[`rainbow-road`](https://github.com/daniel-grinevich/rainbow-road) repo (`navi/` directory).
The docker-compose files are for local dev only.

Release flow (semantic versioning):

1. Merge to `master`, then push a tag: `git tag vX.Y.Z && git push origin vX.Y.Z`.
2. `deploy-production.yml` builds the image from the tagged commit, pushes
   `ghcr.io/daniel-grinevich/navi-backend:X.Y.Z`, and commits the new tag into
   `rainbow-road/navi/production/kustomization.yaml`.
3. ArgoCD (`navi-production` app) sees the change but **does not auto-sync** —
   a human reviews the diff in the ArgoCD UI and clicks **Sync** to release.
4. On sync, a **PreSync migrate Job** (`navi/base/migrate-job.yaml` in rainbow-road) runs
   `manage.py migrate` before any deployment rolls. If migrations fail, the deploy stops.

Staging (`navi-staging` app) auto-syncs from the `staging-latest` image tag — no button.

Gotchas learned the hard way:

- New Python deps that need system libraries (e.g. WeasyPrint → pango/glib) must be added
  to `compose/production/django/Dockerfile`, or workers crash-loop at import time.
- Production settings live in `config/settings/production.py`; if a setting exists in
  `staging.py` but not there (CORS, cookie flags), prod silently misbehaves.
- The k8s cluster is reachable via `ssh dandelion@servero1` + `sudo kubectl`
  (namespaces `navi-production` / `navi-staging`).

## Running things (Docker)

Everything runs through the `Makefile`, which wraps `docker compose`. Default env is `local`.

- `make up` / `make up-d` — start the stack
- `make migrate` / `make makemigrations` — DB migrations
- `make test` — run the full pytest suite
- `make testorders` — run just the `orders` app tests
- `make coverage` — coverage run + HTML report
- `make lint` — `ruff check --fix` then `ruff format`
- `make shell` — Django shell

Prefix with `ENV=stage` / `ENV=prod` to target other compose files.

## Code layout & where things go

Each app is layered. Follow the existing split (see `navi_backend/orders/` as the reference example):

- `models.py` — data + model-level invariants. Keep query logic in `managers.py`.
- `managers.py` — custom QuerySets/Managers; put reusable queries here, not in views.
- `services/` — business logic / use-cases (e.g. `create_order_service.py`). Multi-step operations that touch several models go here.
- `api/` — DRF layer: `serializers.py`, `views.py`, `permissions.py`. Keep these thin.
- `tasks.py` — Celery tasks. `consumers.py` — Django Channels websocket consumers.
- `tests/` — pytest tests (use `factory-boy` factories, not hand-built fixtures).

**Views/serializers stay thin; business logic lives in `services/` and `managers/`.** Don't put multi-model orchestration or transaction logic in a view.

## Auth (do not weaken these)

JWTs live in HttpOnly cookies (`navi_backend/core/authentication.py` +
`navi_backend/users/jwt.py`): 5-min access / 7-day refresh, rotation with blacklist,
CSRF enforced on cookie auth. Auth endpoints are rate-limited via DRF
`ScopedRateThrottle` (`throttle_scope` on the views, rates in `base.py`) backed by the
default cache (Redis in prod). Guest accounts can only be claimed/upgraded by the
guest's own authenticated session — never by knowing the email alone.

## Style & design principles

- **Prefer composition over inheritance.** Avoid deep class hierarchies and long MRO/mixin chains — compose small helpers/services instead.
- **Avoid deep nesting.** Use early returns / guard clauses to keep functions flat; if you're past ~3 levels of indentation, extract a function.
- **Fat models/services, thin views** (the classic Django guidance). Query logic → managers; use-case logic → services.
- Keep functions small and single-purpose. Prefer explicit, readable code over clever code.
- Wrap multi-write operations in `transaction.atomic()`.
- Match the style of surrounding code (naming, imports, comment density).

## Use the platform / data layer

We already run Celery, Redis, and Postgres — reach for them instead of reinventing their job in app code. Use judgement; this is a default, not a mandate for *everything*.

- **Slow or non-critical work → Celery task** (`tasks.py`), not inline in a request/view. Emails, PDF generation, webhooks, third-party API calls, anything the user doesn't need to block on.
- **Repeated/expensive reads → cache them in Redis** (`django-redis`) with a sensible TTL, rather than recomputing every call.
- **Push work down to the database** when it belongs there: filtering/aggregation in querysets (`managers.py`), `select_related`/`prefetch_related` to avoid N+1, DB constraints/uniqueness for invariants, `F()`/atomic updates instead of read-modify-write in Python.
- **Scheduled/recurring work → celery-beat**, not ad-hoc timing logic.
- Rule of thumb: if the framework, queue, cache, or DB already does it well, use that — reserve custom Python for the actual business logic.

## Tooling & quality gates

- **Ruff** is the linter + formatter (config in `pyproject.toml`, `target-version = py314`). Run `make lint` before pushing.
- **mypy** with `django-stubs` / `djangorestframework-stubs` — keep type hints on new code; migrations are exempt.
- **pytest** with `pytest-django` (`--reuse-db`); `asyncio_mode = auto` for async tests. Add tests for new behavior.
- **pre-commit** hooks exist — `make pre-commit` runs them across all files.
- **djLint** for Django templates.

## Good references

Cookiecutter-Django conventions apply throughout — https://cookiecutter-django.readthedocs.io/
For broader Django patterns worth following: the HackSoft *Django Styleguide* (service/selector layering) — https://github.com/HackSoftware/Django-Styleguide
