.PHONY: up down logs migrate revision test test-back test-front lint

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f api

migrate:
	docker compose exec api alembic upgrade head

# Usage : make revision m="ajoute la table X"
revision:
	docker compose exec api alembic revision --autogenerate -m "$(m)"

test: test-back test-front

test-back:
	cd backend && pytest

test-front:
	cd frontend && npm run test

lint:
	cd backend && ruff check . && mypy app
	cd frontend && npx tsc -b
