makemigrations:
	docker compose -f docker-compose.local.yml run --rm django python manage.py makemigrations
migrate:
	docker compose -f docker-compose.local.yml run --rm django python manage.py migrate
superuser:
	docker compose -f docker-compose.local.yml run --rm django python manage.py createsuperuser
build:
	docker compose -f docker-compose.local.yml build
up:
	docker compose -f docker-compose.local.yml up
down:
	docker compose -f docker-compose.local.yml down
testorders:
	docker compose -f docker-compose.local.yml run django pytest -rP navi_backend/orders
