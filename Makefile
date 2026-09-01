.DEFAULT_GOAL := setup

setup:
	uv sync --project apps/backend --all-groups
	pnpm install
	pre-commit install

install: setup

dev:
	docker compose up --build

down:
	docker compose down

restart: down dev

logs:
	docker compose logs -f

backend-shell:
	docker compose exec backend sh

django-shell:
	docker compose exec backend uv run python manage.py shell

migrate:
	docker compose exec backend uv run python manage.py migrate

makemigrations:
	docker compose exec backend uv run python manage.py makemigrations

createsuperuser:
	docker compose exec backend uv run python manage.py createsuperuser

test:
	uv run --project apps/backend pytest apps/backend/tests
	pnpm --filter admin-web test

lint:
	uv run --project apps/backend ruff check apps/backend
	pnpm --filter admin-web lint

format:
	uv run --project apps/backend ruff format apps/backend
	pnpm --filter admin-web format

typecheck:
	uv run --directory apps/backend mypy .
	pnpm --filter admin-web typecheck

clean:
	docker compose down --volumes --remove-orphans
