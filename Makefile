.PHONY: install install-web lint fmt typecheck test test-web build-web api web dev compose-up compose-config

UV ?= uv
PNPM ?= pnpm

install:
	$(UV) sync --extra dev

install-web:
	$(PNPM) install

fmt:
	$(UV) run ruff format services/api

lint:
	$(UV) run ruff check services/api
	$(UV) run ruff format --check services/api
	$(PNPM) lint

typecheck:
	$(UV) run pyright
	$(PNPM) typecheck

test:
	$(UV) run pytest

test-web:
	$(PNPM) test

build-web:
	$(PNPM) build

api:
	$(UV) run rockyroad-api

web:
	$(PNPM) dev

dev:
	./scripts/dev

compose-config:
	docker-compose config >/dev/null 2>&1 || docker compose config >/dev/null
	docker-compose --profile local config >/dev/null 2>&1 || docker compose --profile local config >/dev/null

compose-up:
	docker-compose up --build || docker compose up --build
