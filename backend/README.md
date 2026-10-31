# Mis Eventos — Backend API

API RESTful de la plataforma **Mis Eventos**, construida con **Python 3.14**, **FastAPI**, **SQLModel / SQLAlchemy**, **PostgreSQL (`pg_trgm`)**, **Alembic**, **Redis** (caché de lectura prescindible) y gestionada con **UV**.

## Requisitos

- Python 3.14
- [UV](https://docs.astral.sh/uv/)
- Docker y Docker Compose (para PostgreSQL y Redis en contenedor)

## Estructura del proyecto

```text
backend/
├── Dockerfile
├── alembic.ini
├── pyproject.toml
├── uv.lock
├── migrations/
│   ├── env.py
│   └── versions/
│       └── 0001_enable_pg_trgm.py
├── app/
│   ├── main.py
│   ├── core/
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── cache.py
│   │   ├── exceptions.py
│   │   ├── pagination.py
│   │   ├── datetime_utils.py
│   │   └── health.py
│   ├── auth/
│   ├── users/
│   ├── events/
│   ├── sessions/
│   └── registrations/
└── tests/
    ├── conftest.py
    └── test_platform.py
```

## Puesta en marcha en desarrollo

1. Levantar PostgreSQL y Redis en contenedor desde la raíz del repositorio:

   ```bash
   docker compose up -d db redis
   ```

2. Aplicar migraciones de Alembic desde `backend/`:

   ```bash
   uv run alembic current
   uv run alembic history
   ```

## Ejecución de pruebas y cobertura

Toda la suite de `pytest` se ejecuta exclusivamente contra PostgreSQL en contenedor (`mis_eventos_test`), nunca contra SQLite (R3.6):

```bash
uv run pytest
uv run pytest --cov=app --cov-report=xml --cov-report=term-missing
```

## Documentación OpenAPI

- Swagger UI: `/api/docs`
- Esquema OpenAPI JSON: `/api/openapi.json`
- Estado de salud: `GET /api/health`
