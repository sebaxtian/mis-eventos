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
│       ├── 0003_create_events.py
│       ├── 0004_create_sessions.py
│       └── 0005_create_registrations.py
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
│   ├── sessions/
│   │   ├── models.py
│   │   ├── schemas.py
│   │   ├── dependencies.py
│   │   ├── service.py
│   │   └── router.py
│   └── registrations/
│       ├── models.py
│       ├── schemas.py
│       ├── dependencies.py
│       ├── service.py
│       └── router.py
└── tests/
    ├── conftest.py
    ├── test_platform.py
    ├── test_auth.py
    ├── test_auth_openapi.py
    ├── test_bootstrap.py
    ├── test_users.py
    ├── test_events.py
    ├── test_sessions.py
    └── test_registrations.py
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

   La cabeza vigente tras el Dominio 4 es `0005_create_registrations`; el historial completo es `0001_enable_pg_trgm → 0002_create_users → 0003_create_events → 0004_create_sessions → 0005_create_registrations`.

3. Arrancar la API en local (opcional; el stack completo la levanta en el contenedor `api`):

   ```bash
   uv run uvicorn app.main:app --reload
   ```

## Primer administrador

El arranque de la API siembra el primer `ADMIN` a partir de las variables `BOOTSTRAP_ADMIN_EMAIL`, `BOOTSTRAP_ADMIN_PASSWORD` y `BOOTSTRAP_ADMIN_FULL_NAME`, después de aplicar las migraciones y de forma idempotente.

### Preparar el entorno

- Si **no** existe `.env`, cópialo desde `.env.example`.
- Si **ya** existe `.env`, **complétalo solo por append** con las claves de aplicación que falten, **sin sobrescribir ni eliminar** ninguna variable existente. Las variables de OpenCode/MCP (`CONTEXT7_API_KEY`, `GITHUB_PERSONAL_ACCESS_TOKEN`, `DEV_DATABASE_URI` y `BROWSER_PATH`) no se modifican nunca. Está prohibido ejecutar `cp .env.example .env` sobre un `.env` existente.
- Genera los secretos con un CSPRNG. Por ejemplo:

  ```bash
  python -c "import secrets; print(secrets.token_urlsafe(48))"   # JWT_SECRET_KEY (mínimo 32 caracteres)
  python -c "import secrets; print(secrets.token_urlsafe(24))"   # POSTGRES_PASSWORD (distinto de "postgres")
  ```

### Variables de bootstrap

| Variable | Uso |
| --- | --- |
| `BOOTSTRAP_ADMIN_EMAIL` | Email del primer administrador (sintético; no uses datos personales reales). |
| `BOOTSTRAP_ADMIN_PASSWORD` | Contraseña inicial del administrador. |
| `BOOTSTRAP_ADMIN_FULL_NAME` | Nombre visible del administrador. |

`BOOTSTRAP_ADMIN_EMAIL` y `BOOTSTRAP_ADMIN_PASSWORD` son obligatorios **juntos**: si solo se define uno de los dos, el arranque falla con un mensaje genérico en español que no expone la contraseña ni la clave.

### Comportamiento

- **Idempotencia:** si el email ya existe, el bootstrap no cambia su rol ni su contraseña; dos arranques consecutivos no duplican el `ADMIN`.
- **Producción:** con `APP_ENV=production` y el placeholder `change-me-in-production-min-32-chars`, el arranque falla; con una `JWT_SECRET_KEY` real de al menos 32 caracteres, arranca con normalidad.
- **Rotación de secretos:** cambia `JWT_SECRET_KEY` (invalida los tokens emitidos) y reinicia la API; el bootstrap no reescribe la contraseña de una cuenta ya existente, de modo que la contraseña del administrador se cambia por los mecanismos de la aplicación.
- **Datos locales:** `docker compose down -v` elimina los volúmenes `pg_data` y `media`; úsalo solo en entornos de verificación.

Consulta la nota de release en [CHANGELOG.md](../CHANGELOG.md).

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
| `GET`    | `/api/events/{event_id}/sessions` | Público (visibilidad filtrada por rol)    |
| `POST`   | `/api/events/{event_id}/sessions` | Dueño del evento o `ADMIN`                |
| `GET`    | `/api/events/{event_id}/sessions/{session_id}` | Público (visibilidad filtrada por rol) |
| `PATCH`  | `/api/events/{event_id}/sessions/{session_id}` | Dueño del evento o `ADMIN`    |
| `DELETE` | `/api/events/{event_id}/sessions/{session_id}` | Dueño del evento o `ADMIN`    |
| `POST`   | `/api/events/{event_id}/registrations` | `ATTENDEE`                                  |
| `POST`   | `/api/events/{event_id}/sessions/{session_id}/registrations` | `ATTENDEE`                  |
| `GET`    | `/api/registrations/me`         | Autenticado (solo las propias)              |
| `GET`    | `/api/events/{event_id}/registrations` | `ORGANIZER` dueño del evento o `ADMIN` |
| `GET`    | `/api/registrations/{id}`       | Dueño, organizador dueño o `ADMIN`          |
| `DELETE` | `/api/registrations/{id}`       | Dueño, organizador dueño o `ADMIN`          |

El contrato OpenAPI declara los códigos de error de cada operación (`400`, `401`, `403`, `404`, `409`, `413`, `422`, `503` cuando aplica) con su descripción en español. Las cinco operaciones de sesiones usan `201`/`200`/`204` en el camino feliz y declaran `401/403/404/409/422`; el dominio `sessions` no usa `400`. Las seis operaciones de `registrations` usan `201`/`200`/`204` en el camino feliz, declaran `401/403/404/409/422` y tampoco usan `400`.

## Imágenes de eventos

- Validación real con **Pillow** de JPEG, PNG y WebP; tamaño máximo **5 MB**.
- Limpieza de metadatos EXIF y orientación aplicada con `ImageOps.exif_transpose`.
- Tres variantes WebP por ancho (`400w`, `800w`, `1200w`) sin reescalar hacia arriba.
- Los archivos se guardan en `MEDIA_ROOT/events/` y se sirven en `/api/media/events/` a través de Nginx, con caché inmutable de un año.
- El directorio `/api/media/events/` **no es listable** (`autoindex off`): responde **403/404 según exista el directorio**; en ningún caso devuelve un índice de archivos.

## Sesiones

- **Ventana del evento:** `event.date <= start_time` y `end_time <= medianoche UTC siguiente` (interpretación literal de `EVT-BR-05`); no se permiten sesiones que crucen medianoche y el incumplimiento responde `409`.
- **No solapamiento:** intervalos semiabiertos `[start_time, end_time)` dentro del mismo evento. Toda escritura (`POST`, `PATCH`, `DELETE`) bloquea la fila del evento con `SELECT ... FOR UPDATE` antes de comprobar y escribir, de modo que las operaciones concurrentes del mismo evento se serializan.
- **Capacidad:** `capacity` propia de la sesión entre `1` y `100000` y nunca superior a `event.total_capacity`; `SessionRead` expone `registered_count` (hook `get_session_registered_count`, que cuenta las inscripciones `ACTIVE` reales de `registrations`) y `available_capacity` calculado en el backend.
- **Estados y borrado:** se puede escribir en eventos `DRAFT` y `PUBLISHED`; en `CANCELLED` cualquier escritura responde `409`. El borrado es físico (`204`) y responde `409` si hay asistentes inscritos.
- **Fechas:** entrada ISO 8601 con zona explícita (offset o `Z`), rechazo de fechas `naive` y serialización en UTC terminada en `Z`.

## Inscripciones

- **Unidad:** la inscripción al evento es obligatoria (una fila `ACTIVE` por asistente, `session_id NULL`) y la inscripción a cada sesión es opcional, con cupo propio e independiente del cupo del evento.
- **Capacidad atómica:** toda escritura bloquea primero `events` y después `sessions` con `SELECT ... FOR UPDATE`, dentro de la misma transacción; el límite exacto se acepta (`201`) y superarlo responde `409` con mensajes en español.
- **Integridad:** índices únicos parciales por `(user_id, event_id)` y `(user_id, session_id)` para filas `ACTIVE`; `user_id` es `ON DELETE RESTRICT` y `event_id`/`session_id` son `ON DELETE CASCADE`.
- **Estados y reactivación:** solo los eventos `PUBLISHED` admiten altas; una fila `CANCELLED` se reactiva con el mismo `POST` (`200`) revalidando estado y capacidad. La reactivación de sesión exige además una inscripción `ACTIVE` al evento (`409 "Debes inscribirte primero al evento"`).
- **Cancelación:** `DELETE` lógico e idempotente (`204`), sin plazo; al cancelar la inscripción al evento se cancelan en la misma transacción las inscripciones `ACTIVE` del usuario a sesiones de ese evento. Cancelar una inscripción a sesión no toca la del evento.
- **Consultas:** `/api/registrations/me` (paginado, filtros `status`/`event_id`, orden `created_at DESC, id DESC`), listado por evento solo con inscripciones al evento (una por asistente) y detalle por identificador. `RegistrationRead` expone `user_id` y resúmenes de evento/sesión, nunca `full_name`, `email` ni `password_hash`.
- **Caché:** solo se cachea `/api/registrations/me` con claves `registrations:me:{user_id}:...` y TTL de 60 s; cada alta, reactivación o cancelación invalida `registrations:me:{user_id}:` y `events:`. El listado por evento no se cachea.
- **Contadores:** `EventRead.registered_count` y `SessionRead.registered_count` cuentan filas `ACTIVE` reales mediante los hooks existentes, sin cambiar su firma.

## Caché Redis

El listado y el detalle de eventos se cachean con el prefijo `events:` y TTL de 60 segundos, aislados por `scope` (`public`, `org:{id}`, `admin:{id}`). Cada escritura de eventos **o de sesiones** invalida el prefijo completo. Las escrituras de `registrations` invalidan `registrations:me:{user_id}:` y `events:`; solo se cachea `/api/registrations/me`, nunca el listado por evento ni el detalle. La caché es **prescindible**: cualquier fallo o payload corrupto degrada de forma transparente a PostgreSQL (R4.4).

## Ejecución de pruebas y cobertura

Toda la suite de `pytest` se ejecuta exclusivamente contra PostgreSQL en contenedor (`mis_eventos_test`), nunca contra SQLite (R3.6):

```bash
uv run pytest
uv run pytest --cov=app --cov-report=xml --cov-report=term-missing
```

### Entorno local de pruebas (`backend/.env`)

- `docker compose` lee el `.env` **raíz** y usa los hosts internos `db` y `redis`.
- Para ejecutar `pytest` **desde `backend/`**, `app/core/config.py` lee `backend/.env`. Si no existe, crea uno local con las **mismas credenciales** que el `.env` raíz pero con `DATABASE_URL` y `TEST_DATABASE_URL` apuntando a `127.0.0.1` (puertos publicados) y `REDIS_URL=redis://127.0.0.1:6379/0`.
- `backend/.env` es **local, ignorado por Git** (la regla `.env` de `.gitignore` cubre cualquier nivel) y **no** debe versionarse ni compartirse; se regenera a mano cuando roten las credenciales del `.env` raíz.
- No incluye variables de OpenCode/MCP (`CONTEXT7_API_KEY`, `GITHUB_PERSONAL_ACCESS_TOKEN`, `DEV_DATABASE_URI`, `BROWSER_PATH`) ni `BOOTSTRAP_ADMIN_*`.
- **No** sobrescribas el `.env` raíz para esto: el stack de Docker Compose debe seguir leyendo sus hosts internos.

### Validación de release v1.0.0 (2026-11-01)

- **`pytest`:** **134 passed**, 0 failed, sin `skip`/`xfail` injustificados.
- **Cobertura:** **96,97 %** total (el reporte `term-missing` muestra 97 %), con reporte XML regenerado en `backend/coverage.xml`.
- **Migración aplicada:** `0005_create_registrations (head)`.
- Detalle del alcance y de la validación completa en [CHANGELOG.md](../CHANGELOG.md).

## Documentación OpenAPI

- Swagger UI: `/api/docs`
- Esquema OpenAPI JSON: `/api/openapi.json`
- Estado de salud: `GET /api/health`
