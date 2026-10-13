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

test-tenant-integrity:
	@test -n "$(DSMS_TEST_DATABASE_NAME)" || (echo "DSMS_TEST_DATABASE_NAME is required"; exit 2)
	docker compose exec -T -e DJANGO_SETTINGS_MODULE=config.settings.test_postgresql -e DSMS_TEST_DATABASE_NAME="$(DSMS_TEST_DATABASE_NAME)" backend uv run pytest --no-cov tests/unit/test_tenant_integrity.py tests/unit/test_tenant_integrity_command.py tests/unit/test_tenant_integrity_coverage.py tests/integration/test_tenant_integrity_scanner.py tests/integration/test_tenant_integrity_manifest.py tests/integration/test_tenant_integrity_audit.py tests/api/test_saas1d_security.py

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
