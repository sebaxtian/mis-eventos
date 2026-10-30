# AGENTS.md

## Estado del repo

- Repo en fase de especificación: `README.md` en la raíz, `specs/` con índice y plantillas, y `backend/`, `frontend/` e `infra/` solo con `.gitkeep` (sin specs de dominio redactadas todavía). No hay manifests, scripts, CI ni comandos verificables aún. No inventes comandos; cuando se agreguen `pyproject.toml`, `package.json` o `docker-compose.yml`, actualiza este archivo con los comandos reales.
- Fuentes de verdad actuales (en español):
  - `docs/prueba_tecnica_desarrollador_fullstack.md` — requisitos de la prueba técnica (Tusdatos.co, plazo 5 días).
  - `docs/Analisis-Arquitectonico-Funcional-Plataforma-Mis-Eventos.md` — arquitectura v1.0 elegida.

## Metodología

- `docs/constitution.md` contiene los principios innegociables del proyecto y prevalece sobre las specs, la arquitectura y el código. Léelo antes de escribir specs o código; recoge además el flujo TDD obligatorio, el alcance de los bonus y las reglas de idioma.
- Spec-Driven Development (SDD): las especificaciones van en `specs/` y preceden a la implementación. Revisa/actualiza la spec relevante antes de codificar una feature.
- `specs/README.md` es el índice: orden de dominios (`platform` → `auth` → `events` → `sessions` → `registrations` → `delivery`), dependencias, decisiones bloqueantes y estado de cada spec.
- Antes de implementar: identifica el dominio en curso y comprueba que su `spec.md` esté en estado _Aprobada_. Solo el usuario aprueba specs; nunca cambies ese estado por tu cuenta.
- Cada dominio usa `specs/<dominio>/spec.md` (qué), `plan.md` (cómo) y `tasks.md` (tareas TDD), copiados de `specs/_template/`. Criterios de aceptación en notación EARS con IDs `<DOM>-AC-NN`; cada test lleva ese ID en su nombre.
- Docs y commits en español; commits estilo Conventional Commits (`chore: ...`, `feat: ...`).

## Stack decidido (no cambiar sin actualizar la spec)

- Backend (`backend/`): Python **3.14** (imagen `python:3.14-slim`), FastAPI + SQLModel/SQLAlchemy, PostgreSQL, Alembic, gestor de dependencias UV o Poetry, pytest con reporte de cobertura XML. JWT + RBAC con roles Admin / Organizador / Asistente.
- Frontend (`frontend/`): Vue 3 (Composition API, `<script setup>`), Vue Router con guards, Pinia (`useAuthStore`, `useEventStore`), Axios con interceptor 401/403 → limpiar store y redirigir a login, Tailwind CSS, Vitest.
- Infra (`infra/` + `docker-compose.yml`): Nginx como gateway único (`/` → web, `/api` → backend; evita CORS), Postgres con volumen, Redis para cachear listados paginados. Las migraciones Alembic deben ejecutarse al iniciar el contenedor de la API.

## Reglas de negocio que es fácil romper

- Inscripción debe validar capacidad de forma atómica (`registrations < capacity`) — usar bloqueo/transacción, no check-then-insert ingenuo.
- Sesiones de un mismo evento no pueden solaparse en horario.
- Estados de evento: Borrador, Publicado, Cancelado.
- Búsqueda por nombre parcial usa índices trigrama (`pg_trgm`, solo PostgreSQL): tests con SQLite en memoria no cubrirán eso; preferir Postgres en contenedor para tests de búsqueda.

## Entregables obligatorios (de la prueba)

- README separado en `backend/` y `frontend/` (configurar, ejecutar, probar).
- Dockerfile para backend y frontend, docker-compose que orqueste todo, variables de entorno (`.env` está ignorado; versionar un `.env.example`).
- Swagger/OpenAPI, documentación de estructura del frontend, tests unitarios + cobertura en ambos lados.

## Notas

- La sección "Puesta en marcha" de `README.md` está marcada como pendiente: complétala con los comandos reales cuando existan `docker-compose.yml` y los READMEs de `backend/` y `frontend/`.
- `MEMORY.md` es la bitácora viva (decisiones tomadas/pendientes, progreso, tropiezos). Léelo al iniciar sesión y actualízalo al terminar cada tarea; no dupliques aquí lo que ya esté allí.
- `.opencode/` está en `.gitignore` (config local del agente, no se versiona).
- No guardes nunca datos sensibles (claves, tokens, datos personales), tanto en `AGENTS.md` como en `MEMORY.md`.
