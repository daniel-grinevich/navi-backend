# Navi Backend

Django 5.2 / DRF backend for [navitascoffee.com](https://navitascoffee.com) — orders, menu, payments, users, devices, and notifications for the Navi coffee platform. Python 3.14, Postgres, Redis, Celery; Cookiecutter-Django layout.

**New here (human or AI agent)? Start with [AGENTS.md](AGENTS.md)** — conventions, layout, and the deploy pipeline in one page.

## Local development

Everything runs in Docker Compose via the `justfile` ([just](https://github.com/casey/just); `brew install just`). Run `just` to list all recipes.

```sh
just up-d          # start the stack (Django, Postgres, Redis, Celery, mailpit, …)
just migrate       # apply DB migrations
just test          # full pytest suite
just lint          # ruff check --fix + ruff format
just shell         # Django shell
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

### Staging

Staging deploys only from a `vX.Y.Z-staging*` tag on a commit already merged to `development`:

```bash
git fetch origin
git tag v1.4.0-staging origin/development && git push origin v1.4.0-staging
# re-deploy a fix for the same version: v1.4.0-staging.2, v1.4.0-staging.3, ...
```

`deploy-staging.yml` refuses tags whose commit isn't on `origin/development`, pushes the image as
`staging-latest`, `staging-<sha>` and the tag name, and bumps `navi/staging` in rainbow-road (auto-syncs).
Pushing to a branch never deploys. Staging tags don't match the production tag filter.

Watch the build in the GitHub Actions tab and the rollout in ArgoCD.

## Quality gates

Ruff (lint + format), mypy (`django-stubs`), pytest (`--reuse-db`), pre-commit hooks, Trivy/TruffleHog scans in CI. Run `just lint` and `just test` before pushing.
