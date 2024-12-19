makemigrations:
	docker compose -f docker-compose.local.yml run --rm django python manage.py makemigrations
migrate:
	docker compose -f docker-compose.local.yml run --rm django python manage.py migrate
superuser:
	docker compose -f docker-compose.local.yml run --rm django python manage.py createsuperuser
