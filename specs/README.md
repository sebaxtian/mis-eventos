# Plan de Especificaciones Funcionales (SDD) - Mis Eventos

**Versión:** 1.9
**Fecha:** 1 de noviembre de 2026
**Estado:** Vigente
**Metodología:** Spec-Driven Development (SDD)

Este documento es el índice de `specs/`: define los dominios funcionales, su orden, sus dependencias y su estado. Está subordinado a `docs/constitution.md` (Principio 1): el código se subordina a las specs, y cada dominio se especifica, se prueba (TDD) y se implementa siguiendo el flujo de la constitución.

## 0. Cómo se trabaja cada dominio

Cada dominio vive en `specs/<dominio>/` con tres artefactos creados a partir de `specs/_template/` (R1.7):

| Artefacto  | Contenido                                                                                                       | Idioma                              |
| ---------- | --------------------------------------------------------------------------------------------------------------- | ----------------------------------- |
| `spec.md`  | **Qué**: reglas `<DOM>-BR-NN`, contrato de API, criterios `<DOM>-AC-NN` en EARS, casos límite, fuera de alcance | Español                             |
| `plan.md`  | **Cómo**: modelos, migraciones, índices, transacciones, caché, librerías de soporte, impacto en el frontend     | Español (identificadores en inglés) |
| `tasks.md` | Tareas TDD ordenadas: criterio cubierto → test en rojo → implementación                                         | Español (nombres de test en inglés) |

Flujo obligatorio por dominio (constitución, "Flujo de trabajo y Definition of Done"):

1. **Spec aprobada**: `spec.md`, `plan.md` y `tasks.md` redactados; decisiones bloqueantes resueltas; el usuario la marca como _Aprobada_.
2. **Rojo**: test que falla por la aserción esperada.
3. **Verde**: implementación mínima.
4. **Refactor**: la suite sigue en verde.
5. **Contrato**: OpenAPI y frontend alineados.
6. **Registro**: entrada en `MEMORY.md` y actualización de la tabla de estado (sección 5).

Ciclo de vida de una spec (R1.8): `Borrador → Aprobada → En implementación → Implementada`.

**Prefijos de ID por dominio:** `PLAT` (platform), `AUTH` (auth), `EVT` (events), `SES` (sessions), `REG` (registrations), `DLV` (delivery).

## 1. Desglose de Dominios Funcionales

Las "Preguntas abiertas" de cada dominio se resuelven al redactar su `spec.md`; no se responden en el código (R1.6).

### 1.0. Dominio: Plataforma (`specs/platform/`)

Base técnica transversal de la que dependen todos los demás dominios.

- **Alcance Infra:** `docker-compose.yml` con Nginx, web, API, PostgreSQL y Redis; Nginx como único punto de entrada (`/` → web, `/api` → API); `.env.example` sin valores reales; migraciones Alembic al iniciar el contenedor de la API; healthcheck de la API.
- **Alcance Backend:** proyecto gestionado con UV (`pyproject.toml` + `uv.lock`); esqueleto FastAPI con OpenAPI; formato único de error con `detail` en español, incluido el 422 de validación de FastAPI; convención de paginación común a todos los listados; fechas almacenadas en UTC; extensión `pg_trgm` habilitada; base de pruebas con pytest contra PostgreSQL (R3.6) y reporte de cobertura.
- **Alcance Frontend:** proyecto Vue 3 con Vite y TypeScript ligero (`<script setup lang="ts">`, `vue-tsc` en el build); Vue Router con lazy loading de rutas; Pinia; cliente Axios con base relativa `/api`; Tailwind CSS; componentes base (`BaseInput`, `BaseButton`, spinner/skeleton, feedback de acciones); build de producción minificado; Vitest con cobertura.
- **Preguntas abiertas:** _(Resueltas en `specs/platform/spec.md` §8: paginación `page`/`size` 1-indexed con sobre `{ items, total, page, size, pages }`; cuerpo de error `{"detail": "..."}` en español más lista `errors` por campo en `422`; base de pruebas `mis_eventos_test` en PostgreSQL con `SAVEPOINT` + `TRUNCATE`; contrato `GET /api/health` con Redis prescindible)._

### 1.1. Dominio: Autenticación, RBAC y Perfiles (`specs/auth/`)

Determina la identidad y los límites de acceso de cada actor.

- **Alcance Backend:** registro de usuarios (rol Asistente por defecto), inicio de sesión, emisión de JWT y **hash** adaptativo de contraseñas con sal **argon2id** (R5.1).
- **Control de Acceso (RBAC):** matriz de permisos para `ADMIN`, `ORGANIZER` y `ATTENDEE` (R5.3, R6.1).
- **Reglas Críticas:** validación atómica en una única cadena de **dependencias** de FastAPI, todo o nada (R5.2). HTTP 401 para token ausente, inválido o expirado y HTTP 403 para usuario autenticado sin privilegios (R5.6). Gestión de perfiles exclusiva del Admin.
- **Alcance Frontend:** `useAuthStore`; interceptor de Axios (401 → limpiar sesión y redirigir a login; 403 → mantener sesión y mostrar aviso); guards de Vue Router; vistas de login, registro y perfil.
- **Preguntas abiertas:** _(Resueltas en `specs/auth/spec.md` §12: JWT único HS256 de 480 min; bootstrap por entorno; promoción solo por `ADMIN`; perfil mínimo con `is_active`; solo `ATTENDEE` se inscribe; `sessionStorage`; contrato JSON con argon2id.)_

### 1.2. Dominio: Gestión de Eventos y Catálogo (`specs/events/`)

Núcleo operativo para los organizadores y escaparate para los asistentes.

- **Alcance Backend:** CRUD de `Event` y máquina de estados `DRAFT` / `PUBLISHED` / `CANCELLED`; subida de imagen con conversión a WebP (Pillow) y volumen `media` servido por Nginx en `/api/media/` (arquitectura v1.1 §3.8).
- **Reglas Críticas:** búsqueda por nombre o parte del nombre acelerada con índice trigrama (`pg_trgm`); paginación según la convención de `platform`; caché de lectura en Redis, prescindible e invalidada en las escrituras (R4.4); el listado expone los cupos disponibles para que el frontend no los calcule (R2.5).
- **Alcance Frontend:** `useEventStore`; listado paginado y responsivo; `EventCard`; detalle de evento; formulario de creación/edición (`EventForm`); estados de carga; imágenes optimizadas (WebP, tamaños por dispositivo); lazy loading de los componentes pesados del dominio.
- **Preguntas abiertas:** _(Resueltas en `specs/events/spec.md` §12: visibilidad pública de `PUBLISHED` con Bearer opcional y `mine=true` para organizadores/admin; propiedad con `organizer_id` preservado al editar por `ADMIN`; máquina de estados con `CANCELLED` terminal e inmutable y rechazo `409` en `PUBLISHED → DRAFT`; cupos `total_capacity`, `registered_count` y `available_capacity` desde el backend; un único `date: UTCDateTime`; búsqueda `ILIKE` + índice GIN `gin_trgm_ops`; borrado físico `204` solo con `registered_count == 0`; subida WebP `POST /api/events/{id}/image` hasta 5 MB con 3 variantes `400w`/`800w`/`1200w` sin EXIF ni upscaling; caché Redis por `scope` con TTL 60s e invalidación `events:`)._

### 1.3. Dominio: Programación de Sesiones (`specs/sessions/`)

Itinerario interno de cada evento, incluidos los eventos en `DRAFT` para que el organizador lo prepare antes de publicar.

- **Alcance Backend:** `Session` vinculada (uno a muchos) a un `Event`; ponente, horario (`start_time`, `end_time`) y capacidad propia.
- **Reglas Críticas:** validación de `start_time < end_time` en el schema; validación de **no solapamiento** entre sesiones del mismo evento en la lógica de negocio, porque requiere consultar la base de datos; solo el Organizador dueño del evento (o el Admin) gestiona sus sesiones.
- **Alcance Frontend:** línea de tiempo de sesiones en el detalle del evento, construida con Tailwind sin librerías de calendario (R4.3); formulario de sesión visible solo para quien puede gestionarla.
- **Preguntas abiertas:** _(Resueltas en `specs/sessions/spec.md` §17–§18: intervalos semiabiertos `[start, end)` con consecutivas válidas y serialización por `SELECT ... FOR UPDATE` sobre el evento; `capacity` propia de sesión `1..100000` y ≤ `event.total_capacity` con cupos calculados por el backend; escrituras en `DRAFT`/`PUBLISHED` y `409` en `CANCELLED`; fechas UTC estrictas con rechazo de `naive`, ventana literal de `EVT-BR-05` sin cruce de medianoche, listado sin paginación, borrado físico `204` y frontend con timeline y formulario. Decisiones D1–D8 del 2026-10-31; Aprobada explícitamente por el usuario el 2026-10-31 (R1.8); implementación iniciada; enmienda v0.2 del 2026-11-01 con 30 criterios `SES-AC` (nuevos `SES-AC-29`, `404` en escrituras sobre sesión ajena/inexistente, y `SES-AC-30`, serialización de `DELETE` con `FOR UPDATE`), aprobada por el usuario el 2026-11-01; implementación TDD (`B1..B28`, `F1..F7`) y validación (`V1..V6`) completadas el 2026-11-01 con veredicto `¿pasa? sí` del `reviewer` (30/30 criterios `SES-AC`), spec `Implementada`.)_

### 1.4. Dominio: Inscripciones y Capacidad (`specs/registrations/`)

Motor transaccional de la plataforma, susceptible a errores de concurrencia.

- **Alcance Backend:** `Registration` que vincula usuarios con eventos y, opcionalmente, con sesiones; consulta "mis inscripciones".
- **Reglas Críticas:** inscripción atómica: comprobación de capacidad e inserción en la misma transacción con bloqueo (R5.4), probada contra PostgreSQL (R3.6); unicidad (un usuario no se inscribe dos veces al mismo ítem); un usuario solo ve sus propias inscripciones (R5.8); toda inscripción invalida la caché de eventos afectada (R4.4).
- **Alcance Frontend:** vista "Mis inscripciones" en el perfil; botón de inscripción deshabilitado cuando la API informa cero cupos; feedback de éxito y error.
- **Preguntas abiertas:** _(Resueltas en `specs/registrations/spec.md` §14: inscripción al evento obligatoria y a sesiones opcional con inscripción previa al evento; `session_id` nullable con índices únicos parciales y FKs `ON DELETE CASCADE` en `event_id`/`session_id` (`RESTRICT` solo en `user_id`); solo eventos `PUBLISHED` admiten inscripción y cancelar el evento no anula inscripciones; un cupo de evento por persona con cupo propio e independiente por sesión; anulación lógica sin plazo, idempotente y en cascada solo evento → sesiones; bloqueo `events` → `sessions` con `FOR UPDATE`; reactivación de filas `CANCELLED` con `200` revalidando capacidad y, en sesiones, la inscripción activa al evento; `/me` paginado con inscripciones al evento y a sesiones, listado por evento para organizador/`ADMIN` solo con inscripciones al evento y detalle; caché solo de `/me` por usuario con invalidación `registrations:` + `events:`; `RegistrationRead` sin datos personales del usuario. Decisiones D1–D14 aprobadas por el usuario el 2026-11-01 y D15–D16 derivadas; spec aprobada explícitamente por el usuario el 2026-11-01 ("Sí, apruebo"), implementación TDD (`B1..B34`, `F1..F7`) y validación (`V1..V6`) completadas el 2026-11-01 con veredicto `¿pasa? sí` del `reviewer` (38/38 criterios `REG-AC` y 14/14 reglas `REG-BR`): `Implementada` (v0.1).)_

### 1.5. Dominio: Entrega (`specs/delivery/`)

Cierre documental y de verificación final que empaqueta los cinco dominios anteriores como **release v1.0.0**. No añade funcionalidad: versiona, valida, asegura y documenta lo ya construido.

- **Alcance Versiones:** `1.0.0` coherente en `backend/pyproject.toml`, `backend/uv.lock`, `frontend/package.json`, `frontend/package-lock.json` y `info.version` del OpenAPI, más etiqueta anotada `v1.0.0`; lockfiles regenerados con `uv lock` y `npm version --no-git-tag-version`.
- **Alcance Entorno:** `.env` raíz **completado por append idempotente** sobre el archivo existente, sin sobrescribir ni eliminar claves previas (se preservan `CONTEXT7_API_KEY`, `GITHUB_PERSONAL_ACCESS_TOKEN`, `DEV_DATABASE_URI` y `BROWSER_PATH` de OpenCode/MCP), añadiendo solo las claves de aplicación ausentes con `POSTGRES_PASSWORD` real, `JWT_SECRET_KEY` de ≥32 caracteres por CSPRNG y `BOOTSTRAP_ADMIN_*`; ignorado por Git; rechazo del placeholder con `APP_ENV=production`; primer `ADMIN` idempotente y documentado en los READMEs.
- **Alcance Validación:** `pytest` con cobertura XML, `Vitest` con cobertura, `vue-tsc --noEmit`, build minificado sin source maps, `docker compose down -v && docker compose up -d --build`, `alembic current` en `0005_create_registrations (head)` y verificación de las rutas del gateway (`/`, `/api/health`, `/api/docs`, `/api/openapi.json`, `/api/media/`).
- **Alcance E2E:** un único recorrido transversal con `ADMIN` + `ORGANIZER` + `ATTENDEE` (evento → imagen WebP → publicación → sesión → inscripción → cupo agotado → cascada al cancelar → limpieza de datos, media y claves Redis).
- **Alcance Seguridad:** revisión final de secretos, `.env` ignorado, CORS cerrado, ausencia de `v-html`, source maps y datos personales, y Redis prescindible verificado en runtime.
- **Alcance Documentación:** estados a `Implementada`, retirada de las frases de trabajo en curso, cifras de cobertura fechadas y nota de release `v1.0.0`.
- **Decisiones resueltas (2026-11-01):** `DLV-D1` nota de release en `CHANGELOG.md` en la raíz con la sección `[1.0.0] - 2026-11-01`; `DLV-D2` R1.5 se satisface con checklist de comandos reproducibles, evidencia registrada y tests reutilizados; `DLV-D3` las seis specs de dominio se armonizan a `1.0` y `delivery` queda en `1.1` por la enmienda del `.env` aprobada después de su aprobación (R1.8), conservando el historial de enmiendas y su registro en documentación, memoria, commits y etiquetas; `DLV-D4` endurecimiento de infraestructura (puertos `5432`/`6379`, cabeceras de seguridad en Nginx y `restart:`) queda fuera de alcance y se declara como limitación del entorno de desarrollo en `CHANGELOG.md`. Sin decisiones bloqueantes (R1.8).
- **Aprobación y enmienda v1.1 (2026-11-01):** el usuario aprobó explícitamente la spec con la frase «Apruebo y autorizo iniciar (Recomendada). Marco la spec como Aprobada v1.0 en spec.md y specs/README.md §5, registro la aprobación y fecha en MEMORY.md, y la paso a En implementación para arrancar las tareas V1..V35 con el implementer.», condicionada a **no modificar ni eliminar** las variables ya presentes en el `.env` (claves de OpenCode/MCP). Antes de registrar la aprobación se enmendó la spec a **v1.1** (R1.4, R1.6): `DLV-BR-03`, `DLV-AC-05` y `DLV-AC-07` exigen un `.env` completado por **append idempotente** y la conservación de las claves previas. Transiciones `Borrador → Aprobada → En implementación` con la misma fecha; estado actual **`En implementación` (v1.1)**.
- **Validación de release (2026-11-01):** ejecutada por el `implementer` con `pytest` **134/134** (cobertura **96,97 %**, 97 % en el reporte `term`, `coverage.xml` regenerado), `Vitest` **62/62 en 16 archivos** (95,19 % sentencias/líneas, 86,39 % ramas, 94,35 % funciones), `vue-tsc --noEmit` sin errores, build de **136 módulos** sin `.map`, `alembic current` en `0005_create_registrations (head)`, stack desde cero con **5 servicios** operativos, contrato OpenAPI **idéntico al baseline salvo `info.version = "1.0.0"`**, Redis `degraded` con `/api/health` 200, E2E transversal con **409** por cupo agotado, cascada al cancelar y limpieza total (`users/events/sessions/registrations = 0`, `DBSIZE = 0`, media 0), y `.env` completado por append con huellas de las variables de OpenCode/MCP intactas.
- **Cierre del dominio (2026-11-01):** primera auditoría del `reviewer` con veredicto **`¿pasa? no`** por `DLV-AC-11`/`DLV-BR-05` (desde `backend/`, `pytest` daba 4 passed y 130 errors por autenticación de PostgreSQL al no existir `backend/.env`, y con el `.env` raíz inyectado fallaban 2 por `REDIS_URL` sin resolver desde el host). El usuario aprobó el enfoque **entorno local + documentación** sin tocar código ni specs cerradas: `backend/.env` local **ignorado por Git** con 7 claves (`DATABASE_URL`, `TEST_DATABASE_URL`, `REDIS_URL`, `APP_ENV`, `JWT_SECRET_KEY`, `JWT_EXPIRE_MINUTES`, `MEDIA_ROOT`) apuntando a `127.0.0.1`, sin variables de OpenCode/MCP ni `BOOTSTRAP_ADMIN_*`; `backend/Dockerfile` con rutas explícitas y `.env`/`.env.local` en `backend/.dockerignore`. Re-auditoría con el comando literal documentado: **134 passed**, 0 failed, cobertura `term` **97 %** (`coverage.xml` con `line-rate` 96,97 %, 1598/1648) y concurrencia `5 passed, 129 deselected`. Veredicto final **`¿pasa? sí`** (32/32 `DLV-AC`), con la etiqueta anotada `v1.0.0` (`V7`) pendiente sobre el commit de cierre.

---

## 2. Matriz Jerárquica y Orden de Ejecución

Las specs se **aprueban e implementan en este orden** en el backend, porque cada dominio es prerrequisito de las pruebas del siguiente. El frontend del dominio N puede avanzar en paralelo al backend del dominio N+1 en cuanto el contrato OpenAPI de N esté congelado (R2.4).

Principios transversales que aplican a **todas** las specs: R2 (aislamiento), R3.1–R3.3 (TDD), R5.5 (validación de entrada y schemas de salida), R5.7 (secretos), R6 (idioma).

| Orden | Directorio             | Dominio                        | Dependencias                 | Principios específicos                                                                        | Bonus cubiertos                                     | Decisiones bloqueantes                                                   |
| :---: | :--------------------- | :----------------------------- | :--------------------------- | :-------------------------------------------------------------------------------------------- | :-------------------------------------------------- | :----------------------------------------------------------------------- |
| **0** | `specs/platform/`      | Plataforma                     | _(Ninguna)_                  | R2.1, R2.2, R3.6, R3.9, R5.7, R6 (422 en español)                                             | Minificación, lazy loading de rutas                 | — (resueltas en la arquitectura v1.1: UV, PostgreSQL en tests, TypeScript ligero) |
| **1** | `specs/auth/`          | Autenticación, RBAC y Perfiles | `platform`                   | R5.1, R5.2, R5.3, R5.6, R5.8, R5.9                                                            | Roles, permisos por rol, gestión de perfiles        | — (resueltas en `specs/auth/spec.md` §12)                                 |
| **2** | `specs/events/`        | Eventos y Catálogo             | `auth`                       | R3.6 (`pg_trgm`), R4.4 (caché Redis), R2.5 (cupos desde la API)                               | Imágenes WebP, lazy loading de componentes, caching | — (resueltas en `specs/events/spec.md` §12)                                      |
| **3** | `specs/sessions/`      | Programación de Sesiones       | `events`                     | R3.4 (solapamiento), R5.3 (propiedad del evento)                                              | —                                                   | Resueltas en `specs/sessions/spec.md` §17–§18                            |
| **4** | `specs/registrations/` | Inscripciones y Capacidad      | `auth`, `events`, `sessions` | R3.4 (límites y concurrencia), R3.6 (bloqueos en PostgreSQL), R5.4, R5.8, R4.4 (invalidación) | —                                                   | Resueltas en `specs/registrations/spec.md` §14 (D1–D14)                  |
| **5** | `specs/delivery/`      | Entrega                        | Todos                        | R3.9 (cobertura)                                                                              | —                                                   | Resueltas (DLV-D1–DLV-D4) en `specs/delivery/spec.md` §8                |

---

## 3. Trazabilidad de requisitos

Cada requisito de `docs/prueba_tecnica_desarrollador_fullstack.md` tiene un dominio responsable.

| Requisito de la prueba técnica                                                  | Dominio                                                |
| ------------------------------------------------------------------------------- | ------------------------------------------------------ |
| CRUD de eventos, estados, validaciones de negocio                               | `events`                                               |
| Gestión de capacidad y registro                                                 | `events`, `registrations`                              |
| Búsqueda por nombre o parte del nombre                                          | `events`                                               |
| Registro de usuarios, login, protección de rutas                                | `auth`                                                 |
| Creación y gestión de sesiones, ponentes, validación de horarios, capacidad     | `sessions`                                             |
| Inscribirse a un evento con capacidad; ver mis eventos                          | `registrations`                                        |
| Bonus: roles, permisos por rol, gestión de perfiles por el Admin                | `auth`                                                 |
| Listado paginado, detalle con sesiones, formulario de evento                    | `events`, `sessions`                                   |
| Formularios de registro y login                                                 | `auth`                                                 |
| Rutas: lista, detalle, crear, login, registro, perfil                           | `platform` (router), `auth`, `events`, `registrations` |
| Manejador de estado (eventos y autenticación)                                   | `auth`, `events`                                       |
| Consumo del API y manejo de errores con mensajes al usuario                     | `platform` (cliente y formato de error), cada dominio  |
| Componentes reutilizables                                                       | `platform` (base), `events` (`EventCard`, `EventForm`) |
| Bonus: optimización de imágenes                                                 | `events`                                               |
| Bonus: lazy loading                                                             | `platform` (rutas), `events` (componentes)             |
| Bonus: minificación                                                             | `platform`                                             |
| Bonus: caching con Redis                                                        | `events`, `registrations` (invalidación)               |
| UI/UX: diseño usable, responsivo, loading states, feedback visual               | `platform` (base), cada dominio                        |
| Python 3.14, FastAPI, SQLModel, PostgreSQL, UV, Alembic, pytest, OpenAPI        | `platform`                                             |
| Docker, Docker Compose, variables de entorno                                    | `platform`                                             |
| READMEs, documentación del frontend, cobertura                                  | `delivery`                                             |

---

## 4. Plantillas

`specs/_template/` contiene `spec.md`, `plan.md` y `tasks.md`. Para iniciar un dominio se copian a `specs/<dominio>/` y se sustituye `<DOM>` por el prefijo del dominio.

## 5. Estado de las specs

| Orden | Dominio         | Estado                 | Versión | Última actualización |
| :---: | --------------- | ---------------------- | ------- | -------------------- |
|   0   | `platform`      | Implementada           | 1.0     | 2026-11-01           |
|   1   | `auth`          | Implementada           | 1.0     | 2026-11-01           |
|   2   | `events`        | Implementada           | 1.0     | 2026-11-01           |
|   3   | `sessions`      | Implementada           | 1.0     | 2026-11-01           |
|   4   | `registrations` | Implementada           | 1.0     | 2026-11-01           |
|   5   | `delivery`      | Implementada           | 1.1     | 2026-11-01           |
