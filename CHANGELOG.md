# Changelog

Todas las versiones relevantes de **Mis Eventos** se documentan en este archivo.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el versionado semántico. Las cifras de validación corresponden a la última corrida registrada en la fecha indicada.

## [1.0.0] - 2026-11-01

Primera entrega formal de la prueba técnica. El sistema queda empaquetado como un entorno reproducible con Docker Compose, con las suites de backend y frontend en verde, el contrato OpenAPI congelado y un recorrido E2E transversal verificado.

### Alcance entregado por dominio

- **`platform` v1.0** — Infraestructura ejecutable (Nginx como gateway único, PostgreSQL, Redis prescindible), esqueleto de backend y frontend, salud con degradación de Redis, paginación, errores en español, Swagger/OpenAPI y suites TDD con cobertura.
- **`auth` v1.0** — Registro, login con JWT HS256, hash argon2id, RBAC (`ADMIN` / `ORGANIZER` / `ATTENDEE`), perfil propio, administración de usuarios y siembra idempotente del primer administrador desde `BOOTSTRAP_ADMIN_*`.
- **`events` v1.0** — CRUD de eventos con estados `DRAFT` / `PUBLISHED` / `CANCELLED`, visibilidad por rol, búsqueda con índices trigrama, capacidad calculada en el backend, imágenes convertidas a WebP en tres variantes y caché Redis por `scope`.
- **`sessions` v1.0** — Agenda del evento con ventana UTC, no solapamiento semiabierto `[start, end)` serializado con bloqueo de fila, capacidad por sesión limitada por la del evento, visibilidad por rol, línea de tiempo y formulario en el detalle.
- **`registrations` v1.0** — Inscripción atómica al evento y a sesiones opcionales, control de cupo por persona y por sesión, unicidad activa con reactivación, cancelación lógica idempotente con cascada evento → sesiones, «Mis inscripciones» y listado de asistentes por evento sin datos personales.
- **`delivery` v1.1** — Cierre de versión `1.0.0`, entorno real generado y no versionado, validación reproducible y fechada, E2E transversal, revisión de seguridad y nota de release.

### Resultados de validación (2026-11-01)

- **Backend (`pytest` contra PostgreSQL en contenedor):** **134 passed**, 0 failed, sin `skip`/`xfail` injustificados. Cobertura total **97 %**. Reporte XML en `backend/coverage.xml`.
- **Frontend (`Vitest`):** **16 archivos**, **62 tests passed**. Cobertura **95.19 %** en sentencias y líneas, **86.39 %** en ramas y **94.35 %** en funciones.
- **Tipos (`vue-tsc --noEmit`):** sin errores (código de salida `0`).
- **Build de producción (`npm run build`):** **136 módulos** transformados, artefactos minificados y **cero** archivos `.map`. `EventForm`, `SessionForm` y `EventRegistrationsList` se emiten en chunks diferidos.
- **Migraciones (`alembic current`):** `0005_create_registrations (head)`, sin revisiones pendientes.
- **Stack desde cero (`docker compose down -v` + `docker compose up -d --build`):** los cinco servicios (`gateway`, `web`, `api`, `db`, `redis`) quedan operativos y `GET /api/health` responde `200` con `{"status": "ok", "database": "ok", "redis": "ok"}`.
- **Contrato OpenAPI:** `info.version = "1.0.0"`; sin cambios en rutas, operaciones, schemas ni códigos de error respecto al cierre de `registrations`.
- **Redis prescindible:** con `redis` detenido, `GET /api/health` responde `200` con `"redis": "degraded"` y las lecturas se sirven desde PostgreSQL; al reanudarlo vuelve a `"redis": "ok"`.
- **E2E transversal:** recorrido completo con `ADMIN`, `ORGANIZER` y `ATTENDEE` (evento → imagen WebP → publicación → sesión → inscripción → cupo agotado con `409` en español → cascada al cancelar), cerrado con limpieza total: `users = events = sessions = registrations = 0`, sin archivos media y `redis DBSIZE = 0`.

`pytest` emite dos advertencias no bloqueantes: una deprecación de `starlette.testclient` sobre `httpx` y un aviso de longitud de clave de PyJWT para SHA512. No afectan al resultado ni al algoritmo usado (HS256).

### Requisitos de entorno

- Docker y Docker Compose.
- Un archivo `.env` en la raíz. Si no existe, se parte de `.env.example`; si ya existe, se completan **solo** las claves de aplicación ausentes mediante _append_ idempotente, sin sobrescribir ni eliminar variables preexistentes.
- Variables obligatorias para el arranque completo: `POSTGRES_*`, `DATABASE_URL`, `TEST_DATABASE_URL`, `REDIS_URL`, `JWT_SECRET_KEY` (mínimo 32 caracteres, generado con CSPRNG) y, para sembrar el primer administrador, `BOOTSTRAP_ADMIN_EMAIL`, `BOOTSTRAP_ADMIN_PASSWORD` y `BOOTSTRAP_ADMIN_FULL_NAME`.
- El primer administrador se crea tras las migraciones de forma idempotente: si el email ya existe no se cambia su rol ni su contraseña. Una configuración parcial falla el arranque con un mensaje genérico en español.
- Con `APP_ENV=production`, el arranque rechaza el placeholder de `JWT_SECRET_KEY`.
- Acceso al gateway en `http://localhost:8080`; rutas verificables: `/`, `/api/health`, `/api/docs` y `/api/openapi.json`.

### Limitaciones conocidas

- **Entorno de desarrollo, no de producción:** los puertos `5432` (PostgreSQL) y `6379` (Redis) se publican para facilitar el desarrollo local; no hay cabeceras de seguridad adicionales en Nginx ni políticas `restart:` en Compose (`DLV-D4`).
- **Ventana UTC de sesiones:** una sesión debe quedar dentro del día UTC del evento y **no puede cruzar la medianoche**.
- **Sin despliegue en nube:** no se incluyen dominio, TLS, backups, monitorización, CI/CD ni publicación en un registry; la entrega es un entorno reproducible con Docker Compose.
- **Datos locales:** `docker compose down -v` elimina los volúmenes `pg_data` y `media`; úsese solo en entornos de verificación.
- **Entorno entregado detenido:** la entrega se valida y luego se limpia con `docker compose down -v` (volúmenes `pg_data` y `media` eliminados). El primer arranque del evaluador debe ser `docker compose up -d --build`; la base se crea desde cero, las migraciones se aplican y se siembra el primer `ADMIN`.

## Historial de versiones del proyecto

| Versión de release | Fecha      | Resumen                                                            |
| ------------------ | ---------- | ------------------------------------------------------------------ |
| `1.0.0`            | 2026-11-01 | Entrega formal de los seis dominios con validación completa y E2E. |
