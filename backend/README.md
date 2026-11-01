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
│       ├── 0001_enable_pg_trgm.py
│       ├── 0002_create_users.py
│       └── 0003_create_events.py
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
│   │   ├── models.py
│   │   ├── schemas.py
│   │   ├── dependencies.py
│   │   ├── images.py
│   │   ├── service.py
│   │   └── router.py
│   ├── sessions/          # reservado para el Dominio 3
│   └── registrations/     # reservado para el Dominio 4
└── tests/
    ├── conftest.py
    ├── test_platform.py
    ├── test_auth.py
    ├── test_auth_openapi.py
    ├── test_bootstrap.py
    ├── test_users.py
    └── test_events.py
```

## Puesta en marcha en desarrollo

1. Levantar PostgreSQL y Redis en contenedor desde la raíz del repositorio:

   ```bash
   docker compose up -d db redis
   ```

2. Aplicar migraciones de Alembic desde `backend/`:

   ```bash
   uv run alembic upgrade head
   uv run alembic current
   uv run alembic history
   ```

   La cabeza vigente tras el Dominio 2 es `0003_create_events`; el historial completo es `0001_enable_pg_trgm → 0002_create_users → 0003_create_events`.

3. Arrancar la API en local (opcional; el stack completo la levanta en el contenedor `api`):

   ```bash
   uv run uvicorn app.main:app --reload
   ```

## Endpoints principales

| Método   | Ruta                            | Acceso                                      |
| -------- | ------------------------------- | ------------------------------------------- |
| `GET`    | `/api/health`                   | Público                                     |
| `POST`   | `/api/auth/register`            | Público                                     |
| `POST`   | `/api/auth/login`               | Público                                     |
| `GET`    | `/api/auth/me`                  | Autenticado                                 |
| `PATCH`  | `/api/auth/me`                  | Autenticado                                 |
| `GET`    | `/api/users`                    | `ADMIN`                                     |
| `GET`    | `/api/users/{user_id}`          | `ADMIN`                                     |
| `PATCH`  | `/api/users/{user_id}`          | `ADMIN`                                     |
| `GET`    | `/api/events`                   | Público (visibilidad filtrada por rol)      |
| `POST`   | `/api/events`                   | `ORGANIZER` y `ADMIN`                       |
| `GET`    | `/api/events/{event_id}`        | Público (visibilidad filtrada por rol)      |
| `PATCH`  | `/api/events/{event_id}`        | Dueño del evento o `ADMIN`                  |
| `DELETE` | `/api/events/{event_id}`        | Dueño del evento o `ADMIN`                  |
| `POST`   | `/api/events/{event_id}/image`  | Dueño del evento o `ADMIN` (`multipart`)    |

El contrato OpenAPI declara los códigos de error de cada operación (`400`, `401`, `403`, `404`, `409`, `413`, `422`, `503` cuando aplica) con su descripción en español.

## Imágenes de eventos

- Validación real con **Pillow** de JPEG, PNG y WebP; tamaño máximo **5 MB**.
- Limpieza de metadatos EXIF y orientación aplicada con `ImageOps.exif_transpose`.
- Tres variantes WebP por ancho (`400w`, `800w`, `1200w`) sin reescalar hacia arriba.
- Los archivos se guardan en `MEDIA_ROOT/events/` y se sirven en `/api/media/events/` a través de Nginx, con caché inmutable de un año.

## Caché Redis

El listado y el detalle de eventos se cachean con el prefijo `events:` y TTL de 60 segundos, aislados por `scope` (`public`, `org:{id}`, `admin:{id}`). Cada escritura invalida el prefijo completo. La caché es **prescindible**: cualquier fallo o payload corrupto degrada de forma transparente a PostgreSQL (R4.4).

## Ejecución de pruebas y cobertura

Toda la suite de `pytest` se ejecuta exclusivamente contra PostgreSQL en contenedor (`mis_eventos_test`), nunca contra SQLite (R3.6):

```bash
uv run pytest
uv run pytest --cov=app --cov-report=xml --cov-report=term-missing
```

Última validación registrada del Dominio 2 (`events`, 2026-10-31): **69 passed**, 0 failed, cobertura total **96 %** con reporte XML en `backend/coverage.xml`. La cobertura de `app/events/` es 100 % salvo `dependencies.py` (91 %); `app/core/cache.py` queda al 100 %.

## Documentación OpenAPI

- Swagger UI: `/api/docs`
- Esquema OpenAPI JSON: `/api/openapi.json`
- Estado de salud: `GET /api/health`
