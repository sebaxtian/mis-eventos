# Plan técnico: Plataforma Base (`platform`)

| Campo                  | Valor                        |
| ---------------------- | ---------------------------- |
| **ID del dominio**     | `PLAT`                       |
| **Spec de referencia** | `specs/platform/spec.md` v1.0 |
| **Fecha**              | 2026-10-31                   |

> Este plan describe **cómo** se implementa `specs/platform/spec.md`. No añade comportamiento: si algo no está en `spec.md`, primero se agrega allí (R1.1, R1.5). Identificadores en inglés (Principio 6).

## 1. Modelo de datos y migraciones

En el dominio `platform` no se crean tablas de negocio (se introducen en `auth`, `events`, `sessions` y `registrations`), pero sí se inicializa la infraestructura de persistencia y migraciones:

| Objeto PostgreSQL     | Detalle                                                   | Propósito                                                                  |
| --------------------- | --------------------------------------------------------- | -------------------------------------------------------------------------- |
| Base `mis_eventos`    | Base de datos principal del contenedor `db`               | Ejecución normal de la API                                                 |
| Base `mis_eventos_test` | Base de datos de pruebas en el mismo contenedor `db`    | Ejecución de `pytest` contra PostgreSQL real sin tocar datos de desarrollo |
| Extensión `pg_trgm`   | `CREATE EXTENSION IF NOT EXISTS pg_trgm;`                 | Búsqueda por subcadena/trigrama en `events` (R3.6)                         |
| Tabla `alembic_version` | Gestionada automáticamente por Alembic                  | Control de versión del esquema                                             |

- **Configuración de Alembic:**
  - `backend/alembic.ini` y `backend/migrations/env.py` leen `settings.database_url` e importan `SQLModel.metadata`.
  - Migración inicial `backend/migrations/versions/0001_enable_pg_trgm.py`:
    - `upgrade()`: ejecuta `op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")`.
    - `downgrade()`: ejecuta `op.execute("DROP EXTENSION IF EXISTS pg_trgm;")`.
- **Inicialización del contenedor `db`:**
  - Un script SQL en `infra/postgres/init-test-db.sql` montado en `/docker-entrypoint-initdb.d/` crea la base de datos `mis_eventos_test` y habilita `pg_trgm` si no existe, además de que la fixture de sesión de `pytest` garantiza su existencia y aplica el esquema antes de correr los tests.

## 2. Infraestructura y contenedores (`docker-compose.yml` e `infra/`)

- **Servicios en `docker-compose.yml`:**
  1. `gateway` (`nginx:1.27-alpine`):
     - Único puerto publicado al host: `${GATEWAY_PORT:-8080}:80` (R2.1).
     - Monta `infra/nginx/default.conf` en `/etc/nginx/conf.d/default.conf:ro` y el volumen `media` en `/var/www/media:ro`.
     - Reglas de enrutamiento:
       - `location /api/media/` → `alias /var/www/media/;` (solo lectura, con `Cache-Control "public, max-age=31536000, immutable"`).
       - `location /api/` → `proxy_pass http://api:8000/api/;` conservando `Host`, `X-Real-IP`, `X-Forwarded-For` y `X-Forwarded-Proto`.
       - `location /` → `proxy_pass http://web:80/;`.
       - `client_max_body_size 10M;`.
  2. `web` (build de `frontend/Dockerfile`):
     - Etapa 1 (`node:22-alpine`): `npm ci` + `npm run build` (`vue-tsc -b && vite build`).
     - Etapa 2 (`nginx:1.27-alpine`): copia `dist/` a `/usr/share/nginx/html` y configuración SPA (`try_files $uri $uri/ /index.html;`) con compresión `gzip`.
  3. `api` (build de `backend/Dockerfile`):
     - Imagen base `python:3.14-slim` (R4.1).
     - Instala `uv` y sincroniza dependencias desde `pyproject.toml` y `uv.lock` (`uv sync --frozen`).
     - Monta el volumen `media` en `/app/media` con permisos de lectura/escritura.
     - Comando de arranque: ejecuta `uv run alembic upgrade head && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`.
     - `healthcheck`: consulta `http://localhost:8000/api/health`.
  4. `db` (`postgres:17-alpine`):
     - Persistencia en volumen `pg_data` y script `infra/postgres/init-test-db.sql`.
     - `healthcheck` con `pg_isready`.
  5. `redis` (`redis:7-alpine`):
     - Caché de lectura prescindible (R4.4).
- **Variables de entorno en `.env.example`:**
  - Se conservan **intactas** las 4 variables existentes de los servidores MCP (`CONTEXT7_API_KEY`, `GITHUB_PERSONAL_ACCESS_TOKEN`, `BROWSER_PATH`, `DEV_DATABASE_URI`).
  - Se añaden sin secretos reales: `GATEWAY_PORT=8080`, `POSTGRES_USER=postgres`, `POSTGRES_PASSWORD=postgres`, `POSTGRES_DB=mis_eventos`, `POSTGRES_TEST_DB=mis_eventos_test`, `DATABASE_URL=postgresql+psycopg://postgres:postgres@db:5432/mis_eventos`, `TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@db:5432/mis_eventos_test`, `REDIS_URL=redis://redis:6379/0`, `MEDIA_ROOT=/app/media`, `JWT_SECRET_KEY=change-me-in-production-min-32-chars`.
  - En `docker-compose.yml` todas las variables usan valores por defecto seguros (`${VAR:-default}`) para que ningún agente necesite leer ni editar `.env`.

## 3. Backend (`backend/`)

### 3.1 Estructura de carpetas por dominio

```text
backend/
├── Dockerfile
├── README.md
├── alembic.ini
├── pyproject.toml
├── uv.lock
├── migrations/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       └── 0001_enable_pg_trgm.py
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py          # Settings (pydantic-settings)
│   │   ├── database.py        # Engine SQLAlchemy/SQLModel y dependencia get_session
│   │   ├── cache.py           # Cliente Redis prescindible (R4.4)
│   │   ├── exceptions.py      # Manejadores HTTP y normalizador 422 en español (PLAT-BR-04)
│   │   ├── pagination.py      # PaginationParams y PaginatedResponse[T] (PLAT-BR-05)
│   │   ├── datetime_utils.py  # Normalización y serialización UTC (PLAT-BR-06)
│   │   └── health.py          # Router GET /api/health (PLAT-BR-02)
│   ├── auth/                  # Esqueleto para Dominio 1
│   ├── users/                 # Esqueleto para Dominio 1
│   ├── events/                # Esqueleto para Dominio 2
│   ├── sessions/              # Esqueleto para Dominio 3
│   └── registrations/         # Esqueleto para Dominio 4
└── tests/
    ├── conftest.py            # Fixtures PostgreSQL (SAVEPOINT + rollback y TRUNCATE)
    └── test_platform.py       # Tests TDD PLAT-AC-01 a PLAT-AC-12
```

### 3.2 Componentes clave del núcleo (`app/core/`)

- **Routers y endpoints (`app/main.py` y `app/core/health.py`):**
  - FastAPI configurado con `title="Mis Eventos API"`, `openapi_url="/api/openapi.json"` y `docs_url="/api/docs"`.
  - Sin `CORSMiddleware` (R2.2).
  - `GET /api/health`: ejecuta ` session.exec(text("SELECT 1"))` contra PostgreSQL y `cache_client.ping()` contra Redis. Si PostgreSQL responde, devuelve `200 OK` con `{"status": "ok", "database": "ok", "redis": "ok" | "degraded"}`. Si PostgreSQL lanza excepción, devuelve `503` con `{"detail": "Servicio de base de datos no disponible"}`.
- **Manejadores de errores y normalización `422` (`app/core/exceptions.py`):**
  - Handler de `StarletteHTTPException`: traduce mensajes por defecto en inglés de Starlette (`"Not Found"` → `"Recurso no encontrado"`, `"Method Not Allowed"` → `"Método no permitido"`, `"Unauthorized"` → `"No autenticado o sesión expirada"`, `"Forbidden"` → `"No tienes permisos para realizar esta acción"`) y respeta cualquier `detail` ya escrito en español por los servicios/dependencias, garantizando siempre `{"detail": "<string en español>"}`.
  - Handler de `RequestValidationError` (`422`): traduce los tipos de error de Pydantic v2 (`missing`, `string_too_short`, `string_too_long`, `greater_than_equal`, `less_than_equal`, `int_parsing`, `value_error`, `json_invalid`, etc.) al español, construye `errors: [{"field": ..., "message": ...}]` y fija `detail` como un `string` en español (ej. `"Error de validación en los datos enviados: <primer_campo>: <mensaje>"` o `"El cuerpo de la petición no es un JSON válido"`).
  - Handler de `Exception` (`500`): registra el error en el logger interno (en inglés) y responde `500` con `{"detail": "Error interno del servidor"}` sin filtrar detalles internos (R5.8).
- **Paginación (`app/core/pagination.py`):**
  - `PaginationParams`: dependencia FastAPI con `page: int = Query(1, ge=1)` y `size: int = Query(10, ge=1, le=50)`, más propiedad `offset -> (page - 1) * size`.
  - `PaginatedResponse[T](BaseModel, Generic[T])`: campos `items: list[T]`, `total: int`, `page: int`, `size: int`, `pages: int`.
  - `build_paginated_response(items, total, params)`: calcula `pages = math.ceil(total / params.size) if total > 0 else 0`.
- **Fechas UTC (`app/core/datetime_utils.py`):**
  - `utc_now() -> datetime`: devuelve `datetime.now(timezone.utc)`.
  - `ensure_utc(value: datetime) -> datetime`: si `value.tzinfo is None`, le asigna `timezone.utc`; si tiene otro huso, lo convierte con `.astimezone(timezone.utc)`.
  - Tipo anotado `UTCDateTime` para modelos/schemas Pydantic que normaliza en validación y serializa en ISO 8601 con sufijo `Z`.
- **Caché Redis prescindible (`app/core/cache.py`):**
  - Clase `CacheClient` inicializada con `REDIS_URL` (`socket_connect_timeout=1`, `socket_timeout=1`).
  - Métodos `ping() -> bool`, `get(key: str) -> Any | None`, `set(key: str, value: Any, ttl_seconds: int = 60) -> bool` e `invalidate_prefix(prefix: str) -> bool`.
  - Todo método envuelve las llamadas a Redis en `try ... except RedisError:` registrando un `logger.warning(...)` y retornando `None`/`False` sin interrumpir el flujo (R4.4).

## 4. Frontend (`frontend/`)

### 4.1 Estructura de carpetas

```text
frontend/
├── Dockerfile
├── README.md
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
├── tailwind.config.js
├── postcss.config.js
└── src/
    ├── main.ts
    ├── App.vue
    ├── assets/
    │   └── main.css
    ├── types/
    │   └── api.ts             #PaginatedResponse<T>, ApiError, UserRole, HealthResponse
    ├── services/
    │   └── api.ts             # Instancia Axios baseURL '/api' + interceptor 401/403/4xx/5xx
    ├── stores/
    │   ├── auth.ts            # useAuthStore base (token, user, isAuthenticated, role, clearSession)
    │   └── notification.ts    # useNotificationStore (avisos en español)
    ├── router/
    │   └── index.ts           # Rutas lazy () => import(...) + guard beforeEach (PLAT-AC-16)
    ├── components/
    │   └── base/
    │       ├── BaseInput.vue
    │       ├── BaseButton.vue
    │       ├── BaseSpinner.vue
    │       ├── BaseSkeleton.vue
    │       └── BaseAlert.vue
    ├── views/
    │   ├── HomePlaceholderView.vue
    │   ├── LoginPlaceholderView.vue
    │   └── AdminPlaceholderView.vue
    └── __tests__/
        ├── api.interceptor.spec.ts
        ├── router.guards.spec.ts
        └── base.components.spec.ts
```

### 4.2 Decisiones de implementación en el cliente

- **Rutas y Guards (`src/router/index.ts`):**
  - Rutas definidas con carga diferida (`component: () => import('@/views/...')`) para cumplir el bonus de lazy loading desde `platform`.
  - Guard `registerNavigationGuards(router)` que lee `to.meta.requiresAuth` y `to.meta.roles`:
    - Si `to.meta.requiresAuth && !authStore.isAuthenticated` → redirige a `{ name: 'login', query: { redirect: to.fullPath } }`.
    - Si `to.meta.roles` está definido y `!to.meta.roles.includes(authStore.role)` → muestra aviso en `useNotificationStore` (`"No tienes permisos para acceder a esta sección"`) y redirige a `{ name: 'home' }`.
- **Cliente Axios e interceptor (`src/services/api.ts`):**
  - `axios.create({ baseURL: '/api', headers: { 'Content-Type': 'application/json' } })`.
  - Interceptor de request: si `authStore.token` existe, añade `Authorization: Bearer ${authStore.token}`.
  - Interceptor de response (error):
    - `status === 401`: comprueba si `error.config?.url` corresponde al endpoint de login (`/auth/login`). Si **no** es login, ejecuta `authStore.clearSession()`, publica aviso `"Tu sesión ha expirado. Inicia sesión nuevamente."` y redirige a `/login` con `query.redirect`. Si **es** login, no redirige y propaga el `detail` devuelto por la API.
    - `status === 403`: **mantiene la sesión** en `useAuthStore` (R5.6) y publica aviso en español con `data?.detail || "No tienes permisos para realizar esta acción"`.
    - `status === 404 || status === 409 || status === 422`: extrae `data?.detail` (que gracias a `PLAT-BR-04` siempre es un `string` en español) y lo notifica.
    - `status >= 500` o sin `error.response`: publica `"No se pudo completar la operación. Inténtalo de nuevo más tarde."`.
- **Componentes base (`src/components/base/`):**
  - `BaseInput.vue`: `<script setup lang="ts">`, props tipadas (`modelValue`, `label`, `type`, `placeholder`, `error`, `id`, `required`, `disabled`), renderiza el mensaje `error` en español bajo el campo con atributos `aria-invalid` y `aria-describedby`.
  - `BaseButton.vue`: props (`type`, `variant`, `isLoading`, `disabled`), deshabilita el botón e incluye `BaseSpinner` cuando `isLoading` es `true`.
  - `BaseSpinner.vue` y `BaseSkeleton.vue`: indicadores visuales de carga reactivos.
  - `BaseAlert.vue`: muestra notificaciones (`success`, `error`, `warning`, `info`) en español con interpolación de texto plano (`{{ message }}`), nunca `v-html` (R5.9).
- **Build minificado (`vite.config.ts`):**
  - `build: { minify: 'esbuild', cssMinify: true, sourcemap: false }`.
  - Script `"build": "vue-tsc -b && vite build"`.

## 5. Librerías de soporte (R4.2)

Todas las librerías listadas implementan un componente del stack cerrado (R4.1) y se registran también en `MEMORY.md`:

| Librería                  | Lado     | Componente del stack al que sirve | Motivo                                                                                   |
| ------------------------- | -------- | --------------------------------- | ---------------------------------------------------------------------------------------- |
| `psycopg[binary]`         | Backend  | PostgreSQL / SQLAlchemy           | Driver moderno PostgreSQL v3 compatible con Python 3.14 y SQLAlchemy 2.x.                |
| `pydantic-settings`       | Backend  | FastAPI / Configuración           | Carga y validación tipada de variables de entorno (R5.7).                                |
| `redis`                   | Backend  | Redis                             | Cliente oficial de Redis en Python para la caché de lectura prescindible (R4.4).         |
| `httpx`                   | Backend  | pytest / FastAPI `TestClient`     | Requerido por `starlette.testclient.TestClient` para pruebas de integración HTTP.        |
| `pytest-cov`              | Backend  | pytest                            | Generación obligatoria del reporte de cobertura en XML (R3.9).                           |
| `@vitejs/plugin-vue`      | Frontend | Vue 3 + Vite                      | Compilación de Single-File Components (`.vue`) en Vite.                                  |
| `vue-tsc` + `typescript`  | Frontend | TypeScript ligero                 | Verificación estática de tipos en plantillas Vue y archivos `.ts` durante el build.      |
| `@vue/test-utils` + `jsdom` | Frontend | Vitest                          | Montaje y prueba unitaria de componentes Vue 3 y DOM simulado en Vitest.                 |
| `@vitest/coverage-v8`     | Frontend | Vitest                            | Generación del reporte de cobertura de pruebas en el frontend (R3.9).                    |
| `postcss` + `autoprefixer`| Frontend | Tailwind CSS                      | Procesamiento de directivas de Tailwind CSS en el pipeline de Vite.                      |

## 6. Estrategia de pruebas

### 6.1 Backend (`pytest` contra PostgreSQL en contenedor)

- **Prohibición de SQLite (R3.6):** `backend/tests/conftest.py` valida al inicio de la sesión que el dialecto del engine de pruebas sea `postgresql`.
- **Aislamiento entre tests (R3.7):**
  - Fixture `db_session` (por defecto para todos los tests de API/servicios): abre una conexión a `mis_eventos_test`, inicia una transacción externa y configura la sesión con `join_transaction_mode="create_savepoint"`. Al finalizar cada test, hace `rollback()` de la transacción externa, dejando cero datos residuales en milisegundos.
  - Fixture `db_truncate`: disponible para tests que requieren múltiples conexiones simultáneas haciendo `commit()` real (como la prueba de concurrencia del dominio `registrations`), ejecutando `TRUNCATE ... RESTART IDENTITY CASCADE` al finalizar.
- **Comandos verificables de Backend (compatibles con la allowlist de agentes):**
  - Ejecutar suite de tests: `uv run pytest`
  - Ejecutar suite con cobertura XML: `uv run pytest --cov=app --cov-report=xml --cov-report=term-missing`
  - Inspeccionar estado de migraciones: `uv run alembic current` y `uv run alembic history`

### 6.2 Frontend (`Vitest`)

- Pruebas unitarias en `frontend/src/__tests__/` para:
  - Interceptor Axios (`401` fuera de login limpia y redirige, `401` en login no redirige, `403` mantiene sesión y avisa, `404`/`409`/`422` muestra `detail` en español, `500`/red muestra mensaje genérico).
  - Guards de Vue Router (`meta.requiresAuth` y `meta.roles`) y carga diferida de rutas.
  - Componentes base (`BaseInput.vue`, `BaseButton.vue`, `BaseSpinner.vue`, `BaseSkeleton.vue`, `BaseAlert.vue`).
- **Comandos verificables de Frontend (compatibles con la allowlist de agentes):**
  - Ejecutar tests unitarios: `npm run test -- --run` (o `npx vitest run`)
  - Ejecutar cobertura: `npx vitest run --coverage`
  - Comprobar tipos TypeScript: `npx vue-tsc --noEmit`
  - Build de producción minificado: `npm run build`

### 6.3 Infraestructura (`Docker Compose`)

- **Comandos verificables:**
  - Levantar servicios: `docker compose up -d --build`
  - Verificar estado de contenedores: `docker compose ps`
  - Inspeccionar logs: `docker compose logs`

## 7. Riesgos y mitigaciones

- **Riesgo:** El contenedor `api` arranca antes de que PostgreSQL esté listo para recibir conexiones y falla `alembic upgrade head`.
  - **Mitigación:** En `docker-compose.yml`, `api` declara `depends_on: db: condition: service_healthy` con `pg_isready` configurado en `db`.
- **Riesgo:** `RequestValidationError` en Pydantic v2 devuelve listas de errores con mensajes en inglés y a veces incluye objetos no serializables en `ctx`.
  - **Mitigación:** El manejador en `app/core/exceptions.py` construye un diccionario nuevo solo con `field` (`str`) y `message` (`str` traducido al español) y sintetiza un `detail` de tipo `string` en español, evitando serializar `ctx` crudo.
- **Riesgo:** Caída de Redis durante `GET /api/health` o durante una consulta cacheada tumba la petición.
  - **Mitigación:** `CacheClient` usa timeouts de 1 segundo y captura cualquier excepción de `redis`, devolviendo estado degradado o `None` (R4.4).
