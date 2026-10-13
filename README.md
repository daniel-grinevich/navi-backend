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

### End-to-end Pi simulator

Runs the backend plus a simulated NaviPort Raspberry Pi built from the
[navi-pi](../navi-pi) repo (`linux/arm64`; native on Apple Silicon, QEMU on x86),
registered and connected, so you can watch an order go scan → claim → brew → complete.

```sh
NAVI_PI_PATH=/path/to/navi-pi just sim   # NAVI_PI_PATH defaults to ../navi-pi
just sim-order                           # queue a $0 test order, prints its QR token
just sim-down                            # stop the Pi container
```

`just sim` migrates, starts Django + Celery, runs `register_sim_pi` (creates the
"Simulator Pi" + "Simulator NaviPort", issues a fresh device token), starts the
`pi` service (compose profile `sim`) with that token, and prints:

- **Pi queue UI** (default http://localhost:9002, `NAVI_PI_UI_PORT`): paste the QR
  token into the scan box to stand in for the camera; the Pi claims, "brews" for
  `NAVI_BREW_SECONDS`, and completes.
- **Django admin** (`/admin/`): log in as staff (`just superuser`) to browse the APIs below.
- **Device events** (`/api/admin/devices/<id>/events/`): connect, test_order,
  order_claimed, brew_completed, and so on, newest first.

Test orders can also come from the fleet API (`POST /api/admin/devices/<id>/test-order/`).
They are `is_test` orders at $0 with no payment: never charged, invoiced, or awarded.
Every `just sim` rotates the sim's token, because tokens are stored only as hashes.

### Device fleet API (staff only)

`/api/admin/devices/` lists, creates (the response includes `device_token`, shown
once), retrieves, and PATCHes devices (name, location, `enabled`, `navi_port_id`).
Per-device actions are `rotate-token/` (the old token is rejected at once and any
open websocket is closed), `test-order/`, and `events/?limit=`. Events older than
`DEVICE_EVENT_RETENTION_DAYS` (default 30) are purged nightly by celery-beat.
Pis may send `X-Firmware-Version` on requests and the websocket; it's recorded as
`firmware_version`.

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
