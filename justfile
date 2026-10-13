# Navi backend task runner. Wraps docker compose.
# Override the environment with:  just ENV=stage <recipe>   (local | stage | prod)

ENV := "local"

compose_file := if ENV == "local" { "docker-compose.local.yml" } \
    else if ENV == "stage" { "docker-compose.staging.yml" } \
    else if ENV == "prod" { "docker-compose.production.yml" } \
    else { error("Invalid environment: " + ENV + ". Use 'local', 'stage', or 'prod'") }

dc := "docker compose -f " + compose_file
dc_run := dc + " run --rm django"

# List available recipes (default when you run `just`)
default:
    @just --list --unsorted

# Show the current environment and compose file
env:
    @echo "Current environment: {{ENV}} (using {{compose_file}})"

# Build containers
build:
    {{dc}} build

# Build containers and start detached
build-d:
    {{dc}} up -d --build

# Start containers
up:
    {{dc}} up

# Start containers detached
up-d:
    {{dc}} up -d

# Stop containers
down:
    {{dc}} down

# Restart containers
restart: down up

# Open Django shell
shell:
    {{dc_run}} python manage.py shell

# View logs
logs:
    {{dc}} logs -f

# List running containers
ps:
    {{dc}} ps

# Create new migrations
makemigrations:
    {{dc_run}} python manage.py makemigrations

# Apply migrations
migrate:
    {{dc_run}} python manage.py migrate

# Create allauth migrations
makemigrations-auth:
    {{dc_run}} python manage.py makemigrations allauth

# Create sites migrations
makemigrations-sites:
    {{dc_run}} python manage.py makemigrations sites

# Apply allauth migrations
migrate-auth:
    {{dc_run}} python manage.py migrate allauth

# Apply sites migrations
migrate-sites:
    {{dc_run}} python manage.py migrate sites

# Create a superuser
superuser:
    {{dc_run}} python manage.py createsuperuser

# Lint and format with ruff
lint:
    {{dc_run}} ruff check --fix
    {{dc_run}} ruff format

# Run pre-commit across all files
pre-commit:
    pre-commit run --all-files

# Enable VS Code debugging
debug:
    {{dc}} stop django
    DEBUGPY_ENABLED=1 {{dc}} up -d django

# Enable debugging and wait for the debugger to attach
debug-wait:
    {{dc}} stop django
    DEBUGPY_ENABLED=1 DEBUGPY_WAIT=1 {{dc}} up -d django

# End-to-end sim: backend + a navi-pi container, registered and wired up.
# Needs the navi-pi repo: NAVI_PI_PATH=/path/to/navi-pi just sim (default ../navi-pi)
sim:
    #!/usr/bin/env bash
    set -euo pipefail
    # Migrate before `up` so django's own startup migrate is a no-op (no race).
    {{dc_run}} python manage.py migrate --noinput
    {{dc}} up -d django celery_worker mailpit
    # Each registration rotates the sim's token (only hashes are stored).
    eval "$({{dc}} run --rm -T django python manage.py register_sim_pi --env | tr -d '\r' | grep '^NAVI_')"
    NAVI_DEVICE_TOKEN="$NAVI_DEVICE_TOKEN" {{dc}} --profile sim up -d --build --no-deps --force-recreate pi
    url() { echo "http://localhost:$({{dc}} port "$1" "$2" | awk -F: '{print $NF}')"; }
    api="$(url django 8000)"
    echo
    echo "Simulator running:"
    echo "  Pi queue UI:    $(url pi 9000)"
    echo "  Django admin:   $api/admin/   (no staff login yet? just superuser)"
    echo "  Device events:  $api/api/admin/devices/$NAVI_SIM_PI_ID/events/"
    echo "  Fleet API:      $api/api/admin/devices/"
    echo
    echo "Queue a test order:  just sim-order   (then paste the QR token into the Pi UI)"

# Queue a $0 test order on the sim Pi and print its QR token
sim-order:
    {{dc_run}} python manage.py register_sim_pi --test-order

# Stop the sim Pi container
sim-down:
    {{dc}} --profile sim stop pi

# Run all tests
test:
    {{dc_run}} pytest

# Run the orders app tests only
testorders:
    {{dc_run}} pytest -rP navi_backend/orders

# Run test coverage and build the HTML report
coverage:
    {{dc_run}} coverage run -m pytest
    {{dc_run}} coverage html

# Open the coverage report
opencoverage:
    open htmlcov/index.html

# Open a psql console
pg_console:
    {{dc}} exec postgres psql -U MYnQlJTGLdbbMmypXIyQcvLGzFqpuVBD -d navi_backend

# Seed the database with random data
seed_random:
    {{dc_run}} python manage.py seed_random

# Merge staging dotenvs
merge_stage_env:
    python env_merger/merge_staging_dotenvs_in_dotenvs.py

# Merge production dotenvs
merge_prod_env:
    python env_merger/merge_production_dotenvs_in_dotenv.py

# Remove stopped containers and dangling images
clean:
    docker container prune -f
    docker image prune -f

# ⚠️ Remove ALL Docker containers, images, and volumes
nuke:
    @echo "⚠️ WARNING: This will remove ALL Docker containers, images, and volumes!"
    @read -p "Are you sure? [y/N]: " confirm && [ "${confirm:-N}" = "y" ]
    -docker stop $(docker ps -a -q) 2>/dev/null || true
    docker system prune -a --volumes -f
