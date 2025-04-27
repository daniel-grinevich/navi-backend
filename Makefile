ENV ?= local

COMPOSE_LOCAL = docker-compose.local.yml
COMPOSE_STAGE = docker-compose.staging.yml
COMPOSE_PROD = docker-compose.production.yml

ifeq ($(ENV),local)
  COMPOSE_FILE = $(COMPOSE_LOCAL)
else ifeq ($(ENV),stage)
  COMPOSE_FILE = $(COMPOSE_STAGE)
else ifeq ($(ENV),prod)
  COMPOSE_FILE = $(COMPOSE_PROD)
else
  $(error Invalid environment: $(ENV). Use 'local', 'stage', or 'prod')
endif

DC = docker compose -f $(COMPOSE_FILE)
DC_RUN = $(DC) run --rm django
DC_EXEC = $(DC) exec django

.PHONY: help build up down shell logs ps clean test coverage nuke

help:
	@echo "Available commands:"
	@echo "  make [command]         - Run command with local environment (default)"
	@echo "  make ENV=dev [command] - Run command with development environment"
	@echo "  make ENV=prod [command] - Run command with production environment"
	@echo ""
	@echo "Commands:"
	@echo "  build         - Build containers"
	@echo "  up            - Start containers"
	@echo "  down          - Stop containers"
	@echo "  restart       - Restart containers"
	@echo "  shell         - Open Django shell"
	@echo "  logs          - View logs"
	@echo "  ps            - List running containers"
	@echo "  makemigrations - Create new migrations"
	@echo "  migrate       - Apply migrations"
	@echo "  superuser     - Create superuser"
	@echo "  test          - Run all tests"
	@echo "  testorders    - Test orders app only"
	@echo "  coverage      - Run test coverage"
	@echo "  opencoverage  - Open coverage report"
	@echo "  clean         - Remove stopped containers"
	@echo "  nuke          - ⚠️ Remove ALL Docker resources"

env:
	@echo "Current environment: $(ENV) (using $(COMPOSE_FILE))"

build-d:
	$(DC) up -d --build

build:
	$(DC) build

up:
	$(DC) up

up-d:
	$(DC) up -d

down:
	$(DC) down

restart: down up

shell:
	$(DC_RUN) python manage.py shell

logs:
	$(DC) logs -f

ps:
	$(DC) ps

makemigrations:
	$(DC_RUN) python manage.py makemigrations

migrate:
	$(DC_RUN) python manage.py migrate

makemigrations-auth:
	$(DC_RUN) python manage.py makemigrations allauth

makemigrations-sites:
	$(DC_RUN) python manage.py makemigrations sites

migrate-auth:
	$(DC_RUN) python manage.py migrate allauth

migrate-sites:
	$(DC_RUN) python manage.py migrate sites

superuser:
	$(DC_RUN) python manage.py createsuperuser

# Testing commands
test:
	$(DC_RUN) pytest

testorders:
	$(DC_RUN) pytest -rP navi_backend/orders

coverage:
	$(DC_RUN) coverage run -m pytest
	$(DC_RUN) coverage html

pg_console:
	$(DC_RUN) exec postgres psql -U MYnQlJTGLdbbMmypXIyQcvLGzFqpuVBD -d navi_backend

opencoverage:
	open htmlcov/index.html

clean:
	docker container prune -f
	docker image prune -f

merge_dev:
	python env_merger/merge_staging_dotenvs_in_dotenvs.py

merge_prod:
	python env_merger/merge_production_dotenvs_in_dotenv.py

nuke:
	@echo "⚠️ WARNING: This will remove ALL Docker containers, images, and volumes!"
	@read -p "Are you sure? [y/N]: " confirm && [ "$${confirm:-N}" = "y" ]
	-docker stop $$(docker ps -a -q) 2>/dev/null || true
	docker system prune -a --volumes -f
