# AGENTS.md

## Estado del repo

- Fase: **implementación incremental** mediante SDD. Los Dominios 0 (`platform`, v1.0), 1 (`auth`, v1.0), 2 (`events`, v1.0), 3 (`sessions`, v0.2) y 4 (`registrations`, v0.1) están implementados y validados; el producto completo **no** está terminado.
- Dominio 0 (`platform`): infraestructura ejecutable, esqueleto de backend y frontend, y suites TDD. Validado con 18 criterios `PLAT-AC`, `pytest` contra PostgreSQL (12/12, cobertura 85 %), `Vitest` (6/6, cobertura 88.75 %), `vue-tsc`, build de Vite y `docker compose` con el gateway en `http://localhost:8080`. Los detalles viven en `specs/platform/` y en `MEMORY.md`.
- Dominio 1 (`auth`): registro, login con JWT HS256, hash argon2id, RBAC (`ADMIN`/`ORGANIZER`/`ATTENDEE`), perfil propio y gestión de perfiles por el `ADMIN`, con 12 reglas `AUTH-BR`, 31 criterios `AUTH-AC` y 48 tareas TDD. Validado en su cierre con `pytest` 43/43 (cobertura 94 %), `Vitest` 19/19 (cobertura 89.17 %), `vue-tsc`, build de Vite, migración `0002_create_users (head)` y gateway Nginx. Los detalles viven en `specs/auth/` y en `MEMORY.md`.
- Dominio 2 (`events`): CRUD de eventos con estados (`DRAFT`/`PUBLISHED`/`CANCELLED`), visibilidad por rol, búsqueda trigrama, capacidad calculada en backend, imágenes WebP en 3 variantes y caché Redis por `scope`, con 10 reglas `EVT-BR`, 30 criterios `EVT-AC` y 35 tareas TDD. Validado en su cierre con `pytest` 69/69 (cobertura 96 %), `Vitest` 45/45 (cobertura 92.65 %), `vue-tsc`, build de Vite, migración `0003_create_events (head)`, E2E en el gateway y contrato OpenAPI con códigos de error declarados. Los detalles viven en `specs/events/` y en `MEMORY.md`.
- Dominio 3 (`sessions`, v0.2): agenda del evento con ventana UTC (sin cruce de medianoche), no solapamiento semiabierto `[start,end)` serializado con `SELECT ... FOR UPDATE` sobre `events` (también en `DELETE`), capacidad por sesión ≤ `event.total_capacity`, visibilidad por rol, timeline y formulario en el detalle, con 12 reglas `SES-BR`, 30 criterios `SES-AC` y 41 tareas TDD (`B1..B28`, `F1..F7`, `V1..V6`). Validado en su cierre con `pytest` 98/98 (cobertura 97 %), `Vitest` 54/54 (cobertura 94.28 %), `vue-tsc`, build de Vite con `SessionForm` en chunk diferido, migración `0004_create_sessions (head)`, E2E en el gateway y contrato OpenAPI sin `400`. Los detalles viven en `specs/sessions/` y en `MEMORY.md`.
- Dominio 4 (`registrations`, v0.1): inscripción atómica al evento y a sesiones opcionales con `SELECT ... FOR UPDATE` (orden `events` → `sessions`), capacidad por persona y por sesión, unicidad activa con reactivación, cancelación lógica idempotente con cascada evento → sesiones, «Mis inscripciones», listado por evento sin datos personales y caché de `/me`, con 14 reglas `REG-BR`, 38 criterios `REG-AC` y 47 tareas TDD (`B1..B34`, `F1..F7`, `V1..V6`). Validado en su cierre con `pytest` 134/134 (cobertura 97 %), `Vitest` 62/62 (cobertura 95.19 %), `vue-tsc`, build de Vite con `EventRegistrationsList` en chunk diferido, migración `0005_create_registrations (head)`, E2E en el gateway y contrato OpenAPI sin `400`. Los detalles viven en `specs/registrations/` y en `MEMORY.md`.
- Implementación real ya existente:
  - `backend/`: FastAPI sobre Python 3.14 con UV (`pyproject.toml` + `uv.lock`), Alembic (`0005_create_registrations`), `pg_trgm`, salud con Redis prescindible, paginación y errores en español; autenticación JWT, argon2id, RBAC, perfiles, administración de usuarios, CRUD de eventos con imágenes WebP y caché Redis, y CRUD de sesiones con agenda UTC, no solapamiento serializado y capacidad por sesión; e inscripciones atómicas con capacidad, reactivación y cancelación con cascada.
  - `frontend/`: Vue 3 + TypeScript ligero + Vite (`package.json` + `package-lock.json`), Vue Router, Pinia, Axios, Tailwind y componentes base con Vitest; `useAuthStore` con `sessionStorage`, guards y vistas de login, registro, perfil y administración de usuarios; `useEventStore`, catálogo, detalle, formulario de evento y `EventCard`/`EventForm` con lazy loading; `useSessionStore`, línea de tiempo de sesiones en el detalle y `SessionForm` con lazy loading; `useRegistrationStore`, «Mis inscripciones» en el perfil, acciones de inscripción en el detalle y listado de asistentes del evento con lazy loading.
  - `infra/`: `docker-compose.yml` con `gateway`, `web`, `api`, `db`, `redis` y volumen `media`; `infra/nginx/default.conf` e `infra/postgres/init-test-db.sql`; Dockerfiles en `backend/` y `frontend/`.
- Documentación operativa existente: `backend/README.md` y `frontend/README.md` (requisitos, desarrollo, pruebas, cobertura, Alembic, build, estructura del frontend y dominios `events`, `sessions` y `registrations`).
- Dominios pendientes: `delivery`. El siguiente es `delivery`; **no se implementa hasta que su `spec.md`, `plan.md` y `tasks.md` estén redactados y aprobados por el usuario** (R1.8).
- Fuentes de verdad vigentes (en español, por orden de prevalencia):
  1. `docs/constitution.md` — principios innegociables; prevalece sobre specs, arquitectura y código.
  2. `docs/Analisis-Arquitectonico-Funcional-Plataforma-Mis-Eventos.md` — arquitectura v1.1.
  3. `docs/prueba_tecnica_desarrollador_fullstack.md` — requisitos de la prueba (Tusdatos.co, plazo 5 días).
  4. `specs/README.md` y `specs/<dominio>/` — índice, dependencias, estado y artefactos por dominio.
  5. `README.md`, `backend/README.md` y `frontend/README.md` — alcance y operación.
  6. `MEMORY.md` — bitácora viva (decisiones, progreso, tropiezos).

## Metodología

- `docs/constitution.md` contiene los principios innegociables del proyecto y prevalece sobre las specs, la arquitectura y el código. Léelo antes de escribir specs o código; recoge además el flujo TDD obligatorio, el alcance de los bonus y las reglas de idioma.
- Spec-Driven Development (SDD): las especificaciones van en `specs/` y preceden a la implementación. Revisa/actualiza la spec relevante antes de codificar una feature.
- `specs/README.md` es el índice: orden de dominios (`platform` → `auth` → `events` → `sessions` → `registrations` → `delivery`), dependencias, decisiones bloqueantes y estado de cada spec.
- Antes de implementar: identifica el dominio en curso y comprueba que su `spec.md` esté en estado _Aprobada_. Solo el usuario aprueba specs; nunca cambies ese estado por tu cuenta.
- Cada dominio usa `specs/<dominio>/spec.md` (qué), `plan.md` (cómo) y `tasks.md` (tareas TDD), copiados de `specs/_template/`. Criterios de aceptación en notación EARS con IDs `<DOM>-AC-NN`; cada test lleva ese ID en su nombre.
- Docs y commits en español; commits estilo Conventional Commits (`chore: ...`, `feat: ...`).

## Comandos del proyecto

- **Todo el sistema** (desde la raíz): `docker compose up -d --build`. Gateway único en `http://localhost:8080`; rutas verificables `/`, `/api/health`, `/api/docs` y `/api/openapi.json`. El contenedor `api` aplica `uv run alembic upgrade head` al iniciar (definido en `docker-compose.yml`).
- **Solo PostgreSQL y Redis** (desde la raíz): `docker compose up -d db redis`.
- **Backend** (desde `backend/`): `uv run pytest`, `uv run pytest --cov=app --cov-report=xml --cov-report=term-missing`, `uv run alembic current`, `uv run alembic history`. La suite corre siempre contra PostgreSQL en contenedor, nunca SQLite.
- **Frontend** (desde `frontend/`): `npm run dev`, `npm run test -- --run`, `npx vitest run --coverage`, `npx vue-tsc --noEmit`, `npm run build`. El script `pretest` de `package.json` instala dependencias si falta `node_modules`.
- Los comandos anteriores están documentados en `README.md` y en los READMEs de cada parte. No inventes comandos: si cambian los manifiestos, actualiza esta sección y el README correspondiente. "Documentado" no equivale a "revalidado": el estado de la última validación de `platform`, `auth`, `events`, `sessions` y `registrations` está en `MEMORY.md`.

## Stack decidido (no cambiar sin actualizar la spec)

- Backend (`backend/`): Python **3.14** (imagen `python:3.14-slim`), FastAPI + SQLModel/SQLAlchemy, PostgreSQL, Alembic, gestor de dependencias **UV** (`pyproject.toml` + `uv.lock` versionado; no Poetry), pytest **contra PostgreSQL en contenedor** con reporte de cobertura XML. JWT + RBAC con roles `ADMIN` / `ORGANIZER` / `ATTENDEE`. Imágenes de eventos convertidas a WebP con Pillow en el backend (3 variantes por ancho).
- Frontend (`frontend/`): Vue 3 (Composition API, `<script setup lang="ts">`) con **TypeScript ligero**, Vite, Vue Router con rutas lazy y guards (solo UX), Pinia (`useAuthStore`, `useEventStore`, `useSessionStore`, `useRegistrationStore`), Axios con `baseURL` `/api` e interceptor: **401 → limpiar sesión y redirigir a login; 403 → mantener sesión y mostrar aviso** (R5.6), Tailwind CSS, Vitest.
- Infra (`infra/` + `docker-compose.yml`): Nginx como gateway único (`/` → web, `/api` → backend; evita CORS; `/api/media/` servido por Nginx desde el volumen `media` en solo lectura), Postgres con volumen, Redis prescindible para cachear listados paginados. Las migraciones Alembic deben ejecutarse al iniciar el contenedor de la API.

## Reglas de negocio que es fácil romper

- Inscripción debe validar capacidad de forma atómica (`registrations < capacity`) — usar bloqueo/transacción, no check-then-insert ingenuo.
- Sesiones de un mismo evento no pueden solaparse en horario.
- Estados de evento: `DRAFT`, `PUBLISHED`, `CANCELLED` (se traducen solo en la UI).
- Búsqueda por nombre parcial usa índices trigrama (`pg_trgm`, solo PostgreSQL). Nunca usar SQLite en tests: toda la suite de pytest corre contra PostgreSQL en contenedor (R3.6).

## Entregables obligatorios (de la prueba)

- README separado en `backend/` y `frontend/` (configurar, ejecutar, probar).
- Dockerfile para backend y frontend, docker-compose que orqueste todo, variables de entorno (`.env` está ignorado; versionar un `.env.example`).
- Swagger/OpenAPI, documentación de estructura del frontend, tests unitarios + cobertura en ambos lados.
- `platform` cubre la infraestructura, los READMEs iniciales, OpenAPI y las suites con cobertura; `auth` añade registro, login, JWT, RBAC, perfiles y administración de usuarios; `events` añade CRUD de eventos, búsqueda, imágenes WebP, caché Redis y las vistas del catálogo; `sessions` añade agenda con ventana UTC, no solapamiento serializado, capacidad por sesión, timeline y formulario; `registrations` añade inscripciones atómicas al evento y a sesiones, reactivación, cancelación con cascada, «Mis inscripciones» y listado de asistentes por evento. El cierre formal de los entregables, la documentación final de estructura y los entregables de `delivery` se completan en sus dominios.

## Notas

- La "Puesta en marcha" de `README.md` ya documenta los comandos reales de Docker Compose, los requisitos locales y los endpoints del gateway. Mantenla sincronizada con `docker-compose.yml` y los READMEs de `backend/` y `frontend/`.
- Estado de validación: `MEMORY.md` distingue las validaciones runtime registradas al cierre de cada dominio de las comprobaciones que no se reejecutan en tareas documentales. Las cifras de `platform`, `auth`, `events`, `sessions` y `registrations` provienen de las validaciones históricas registradas; en la sesión del 2026-10-31 que saldó la deuda documental se reejecutaron `pytest` (69/69, 96 %), `Vitest` (45/45), `vue-tsc` y la reconstrucción de la API para verificar el contrato OpenAPI, y el cierre de `sessions` (2026-11-01) reejecutó `pytest` (98/98, 97 %), `Vitest` (54/54, 94.28 %), `vue-tsc`, el build y el E2E en el gateway, y el cierre de `registrations` (2026-11-01) reejecutó `pytest` (134/134, 97 %), `Vitest` (62/62, 95.19 %), `vue-tsc`, el build y el E2E en el gateway.
- `MEMORY.md` es la bitácora viva (decisiones tomadas/pendientes, progreso, tropiezos). Léelo al iniciar sesión y actualízalo al terminar cada tarea; no dupliques aquí lo que ya esté allí.
- `.opencode/agents/` contiene los agentes del flujo SDD y se versiona; el resto de `.opencode/` sigue ignorado como configuración local.
- `opencode.json` **sí se versiona**: es la configuración de agentes y servidores MCP, no contiene secretos y hace reproducible el entorno. **Nunca escribas tokens, claves ni contraseñas literales en `opencode.json`**: usa siempre `{env:VARIABLE}` (desde `.env`) o `{file:ruta}`. Si mueves la configuración a `.opencode/opencode.json` quedaría ignorada por Git; déjala en la raíz. Los servidores MCP lanzados con `npx` llevan versión fijada; actualízala de forma deliberada. `BROWSER_PATH` (ruta al binario de Chrome para `chrome-devtools-mcp`) es específico de cada máquina y solo vive en `.env`.
- No guardes nunca datos sensibles (claves, tokens, datos personales), tanto en `AGENTS.md` como en `MEMORY.md`.

## Arquitectura multiagente (OpenCode)

- `coordinator` orquesta los 7 pasos y es el único agente primario del flujo SDD; no edita ni ejecuta shell. Solo delega a `planner`, `implementer` y `reviewer`.
- `planner` redacta specs/planes/tareas en `specs/` y mantiene `MEMORY.md`; nunca aprueba una spec sin aprobación explícita del usuario.
- `implementer` solo comienza con una spec aprobada y trabaja con TDD. Sus permisos deniegan edición en `specs/**` excepto los `tasks.md` enumerados, `docs/**`, documentos normativos y configuración de agentes. Puede editar archivos de implementación y otros archivos permitidos por sus reglas; no debe modificar documentación/configuración fuera de la tarea asignada.
- `reviewer` no edita; su shell pide confirmación salvo una lista acotada de comandos de inspección y verificación. Valida los criterios EARS y el Definition of Done.
- Límites importantes: los permisos de edición de OpenCode son por archivo, no por fragmento; la regla de editar solo la columna de estado en `tasks.md` se refuerza con instrucciones y revisión. Shell no equivale a aislamiento de sistema operativo: los comandos no incluidos en listas permitidas deben pedir confirmación y no se aprueban sin revisar su alcance.
- Los nombres de herramientas MCP deben coincidir con `opencode.json` (`context7-mcp`, `postgres-mcp`, `chrome-devtools-mcp`, `github-mcp`). `postgres-mcp` se configura con `ALLOW_WRITES=0`; no se delegan herramientas de GitHub a los agentes SDD.
