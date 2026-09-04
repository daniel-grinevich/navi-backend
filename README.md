# Navi Backend

Django 5.2 / DRF backend for [navitascoffee.com](https://navitascoffee.com) — orders, menu, payments, users, devices, and notifications for the Navi coffee platform. Python 3.14, Postgres, Redis, Celery; Cookiecutter-Django layout.

**New here (human or AI agent)? Start with [AGENTS.md](AGENTS.md)** — conventions, layout, and the deploy pipeline in one page.

## Local development

Everything runs in Docker Compose via the `Makefile`:

```sh
make up-d          # start the stack (Django, Postgres, Redis, Celery, mailpit, …)
make migrate       # apply DB migrations
make test          # full pytest suite
make lint          # ruff check --fix + ruff format
make shell         # Django shell
```

Create an admin user: `docker compose -f docker-compose.local.yml run --rm django python manage.py createsuperuser`

## Branches

- `development` — default target for feature/fix PRs
- `master` — protected release branch (CI/CD config changes go here directly)

## Releases & deployment

Deploys are GitOps via the [rainbow-road](https://github.com/daniel-grinevich/rainbow-road) repo (kustomize + ArgoCD on k3s):

1. Merge to `master`, push a semver tag (`git tag v1.2.3 && git push origin v1.2.3`)
2. GitHub Actions builds the image, pushes it to GHCR, and bumps the tag in rainbow-road
3. Staging auto-syncs; **production waits for a manual Sync click in the ArgoCD UI**
4. Every sync runs `manage.py migrate` as a PreSync Job before the app pods roll

Watch the build in the GitHub Actions tab and the rollout in ArgoCD.

## Quality gates

Ruff (lint + format), mypy (`django-stubs`), pytest (`--reuse-db`), pre-commit hooks, Trivy/TruffleHog scans in CI. Run `make lint` and `make test` before pushing.
