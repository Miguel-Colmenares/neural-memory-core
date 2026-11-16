.PHONY: help install db-upgrade api web test lint format up down logs backup

help:
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

install: ## Instalar dependencias de Python (entorno ya activado) y del panel web
	pip install -e ".[dev]"
	cd apps/web && npm ci

db-upgrade: ## Aplicar migraciones a la base configurada en NMC_DATABASE_URL
	alembic upgrade head

api: ## Arrancar la API en modo desarrollo (puerto 8000)
	uvicorn apps.api.main:app --reload --port 8000

web: ## Arrancar el panel web en modo desarrollo (puerto 3000)
	cd apps/web && npm run dev

test: ## Ejecutar todas las pruebas (requiere PostgreSQL con pgvector)
	pytest

lint: ## Validar el código
	ruff check .
	ruff format --check .
	cd apps/web && npm run lint && npm run typecheck

format: ## Formatear el código Python
	ruff check . --fix
	ruff format .

up: ## Levantar todo con Docker Compose
	docker compose up -d --build

down: ## Detener los contenedores (los datos se conservan)
	docker compose down

logs: ## Ver los registros
	docker compose logs -f --tail=100

backup: ## Crear un respaldo desde el contenedor de la API
	docker compose exec -u nmc api python scripts/manage.py backup
