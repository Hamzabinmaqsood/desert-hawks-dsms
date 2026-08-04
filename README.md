# Desert Hawks DSMS

Enterprise security-management platform, organized as a modular monolith.

## Prerequisites

Python 3.13, [uv](https://docs.astral.sh/uv/), Node.js 22+, pnpm 10+, Docker Compose, and Git.

## Initial setup

```sh
cp .env.example .env
make setup
```

Review `.env` before use. Its values are explicitly for local development only.

## Start services

```sh
make dev
make migrate
make createsuperuser
```

The API is at `http://localhost:8000`, its OpenAPI docs at `/api/docs/`, and the admin web at `http://localhost:3000`.

## Checks

```sh
make test
make lint
make typecheck
```

## Architecture

`apps/backend` is the Django modular monolith. Domain code currently lives in `dsms/common`, `identity`, `organization`, and `audit`. `apps/admin-web` is the Next.js administrative interface. Shared packages and future application placeholders are kept separate. See [backend structure](docs/architecture/backend-structure.md) and [ADR 0001](docs/adr/0001-modular-monolith.md).

## Troubleshooting

If a container cannot connect, confirm `.env` exists and run `docker compose ps`. Rebuild after dependency changes with `docker compose up --build`. Reset local containers and volumes with `make clean` (this deletes local database data).
