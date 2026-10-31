# Plan de Especificaciones Funcionales (SDD) - Mis Eventos

**Versión:** 1.2
**Fecha:** 30 de octubre de 2026
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

- **Alcance Backend:** registro de usuarios (rol Asistente por defecto), inicio de sesión, emisión de JWT y **hash** adaptativo de contraseñas con sal (bcrypt o argon2, R5.1).
- **Control de Acceso (RBAC):** matriz de permisos para `ADMIN`, `ORGANIZER` y `ATTENDEE` (R5.3, R6.1).
- **Reglas Críticas:** validación atómica en una única cadena de **dependencias** de FastAPI, todo o nada (R5.2). HTTP 401 para token ausente, inválido o expirado y HTTP 403 para usuario autenticado sin privilegios (R5.6). Gestión de perfiles exclusiva del Admin.
- **Alcance Frontend:** `useAuthStore`; interceptor de Axios (401 → limpiar sesión y redirigir a login; 403 → mantener sesión y mostrar aviso); guards de Vue Router; vistas de login, registro y perfil.
- **Preguntas abiertas:**
  - Cómo se crea el primer Admin (propuesta: desde variables de entorno al arrancar, sin secretos en el repo, R5.7).
  - Cómo se crea un Organizador (propuesta: solo por promoción de un Admin).
  - Campos del perfil (email, nombre, ¿otros?) y si existe desactivación de usuarios (`is_active`); si existe, R5.2 debe comprobarla.
  - Qué roles pueden inscribirse a eventos (la arquitectura §4 indica que el Organizador no ve "Inscribirse"; falta decidir el Admin).

### 1.2. Dominio: Gestión de Eventos y Catálogo (`specs/events/`)

Núcleo operativo para los organizadores y escaparate para los asistentes.

- **Alcance Backend:** CRUD de `Event` y máquina de estados `DRAFT` / `PUBLISHED` / `CANCELLED`; subida de imagen con conversión a WebP (Pillow) y volumen `media` servido por Nginx en `/api/media/` (arquitectura v1.1 §3.8).
- **Reglas Críticas:** búsqueda por nombre o parte del nombre acelerada con índice trigrama (`pg_trgm`); paginación según la convención de `platform`; caché de lectura en Redis, prescindible e invalidada en las escrituras (R4.4); el listado expone los cupos disponibles para que el frontend no los calcule (R2.5).
- **Alcance Frontend:** `useEventStore`; listado paginado y responsivo; `EventCard`; detalle de evento; formulario de creación/edición (`EventForm`); estados de carga; imágenes optimizadas (WebP, tamaños por dispositivo); lazy loading de los componentes pesados del dominio.
- **Preguntas abiertas:**
  - Tabla completa de transiciones de estado (¿`DRAFT → CANCELLED`?, ¿`PUBLISHED → DRAFT`?, ¿se edita un evento cancelado?).
  - Semántica de búsqueda: subcadena (`ILIKE` + índice GIN `gin_trgm_ops`, recomendado por el requisito "parte del nombre") o similitud difusa.
  - Visibilidad por rol (propuesta: Asistente y anónimo solo `PUBLISHED`; Organizador los suyos en cualquier estado; Admin todos).
  - Si el listado es público o requiere autenticación.
  - Qué ocurre al reducir la capacidad por debajo de los inscritos (propuesta: rechazar) y al eliminar un evento con inscripciones (borrado físico frente a forzar `CANCELLED`).
  - El evento solo tiene `date`: definir fin o duración del evento y la regla de contención de sus sesiones.
  - Contrato del endpoint de imágenes (ruta, códigos de error, tamaño máximo). El diseño base ya está fijado en la arquitectura v1.1 §3.8: conversión con Pillow a 3 variantes WebP, volumen `media`, `Event.image_key` y entrega por Nginx en `/api/media/`.

### 1.3. Dominio: Programación de Sesiones (`specs/sessions/`)

Itinerario interno de cada evento, incluidos los eventos en `DRAFT` para que el organizador lo prepare antes de publicar.

- **Alcance Backend:** `Session` vinculada (uno a muchos) a un `Event`; ponente, horario (`start_time`, `end_time`) y capacidad propia.
- **Reglas Críticas:** validación de `start_time < end_time` en el schema; validación de **no solapamiento** entre sesiones del mismo evento en la lógica de negocio, porque requiere consultar la base de datos; solo el Organizador dueño del evento (o el Admin) gestiona sus sesiones.
- **Alcance Frontend:** línea de tiempo de sesiones en el detalle del evento, construida con Tailwind sin librerías de calendario (R4.3); formulario de sesión visible solo para quien puede gestionarla.
- **Preguntas abiertas:**
  - Borde del solapamiento (propuesta: intervalos semiabiertos `[start, end)`, sesiones consecutivas válidas).
  - Si `session.capacity` debe ser ≤ `event.total_capacity`.
  - Si se pueden crear o editar sesiones de eventos `CANCELLED`.

### 1.4. Dominio: Inscripciones y Capacidad (`specs/registrations/`)

Motor transaccional de la plataforma, susceptible a errores de concurrencia.

- **Alcance Backend:** `Registration` que vincula usuarios con eventos y, opcionalmente, con sesiones; consulta "mis inscripciones".
- **Reglas Críticas:** inscripción atómica: comprobación de capacidad e inserción en la misma transacción con bloqueo (R5.4), probada contra PostgreSQL (R3.6); unicidad (un usuario no se inscribe dos veces al mismo ítem); un usuario solo ve sus propias inscripciones (R5.8); toda inscripción invalida la caché de eventos afectada (R4.4).
- **Alcance Frontend:** vista "Mis inscripciones" en el perfil; botón de inscripción deshabilitado cuando la API informa cero cupos; feedback de éxito y error.
- **Preguntas abiertas:**
  - Modelo evento/sesión: ¿inscribirse a una sesión exige estar inscrito al evento?, ¿`session_id` es opcional?, ¿la unicidad se modela con índices parciales?
  - Solo se admiten inscripciones a eventos `PUBLISHED` (propuesta: sí).
  - Anulación de inscripciones: dentro o fuera de alcance.
  - Efecto de cancelar un evento sobre sus inscripciones.

### 1.5. Dominio: Entrega (`specs/delivery/`)

Checklist de cierre con los entregables de la prueba técnica que no pertenecen a un dominio funcional.

- README de `backend/` y de `frontend/` (configurar, ejecutar, probar).
- Documentación de la estructura del frontend (componentes, rutas, stores).
- Reportes de cobertura de backend y frontend.
- Verificación de la documentación OpenAPI.
- `docker compose up` levanta todo el sistema desde cero con `.env.example`.

---

## 2. Matriz Jerárquica y Orden de Ejecución

Las specs se **aprueban e implementan en este orden** en el backend, porque cada dominio es prerrequisito de las pruebas del siguiente. El frontend del dominio N puede avanzar en paralelo al backend del dominio N+1 en cuanto el contrato OpenAPI de N esté congelado (R2.4).

Principios transversales que aplican a **todas** las specs: R2 (aislamiento), R3.1–R3.3 (TDD), R5.5 (validación de entrada y schemas de salida), R5.7 (secretos), R6 (idioma).

| Orden | Directorio             | Dominio                        | Dependencias                 | Principios específicos                                                                        | Bonus cubiertos                                     | Decisiones bloqueantes                                                   |
| :---: | :--------------------- | :----------------------------- | :--------------------------- | :-------------------------------------------------------------------------------------------- | :-------------------------------------------------- | :----------------------------------------------------------------------- |
| **0** | `specs/platform/`      | Plataforma                     | _(Ninguna)_                  | R2.1, R2.2, R3.6, R3.9, R5.7, R6 (422 en español)                                             | Minificación, lazy loading de rutas                 | — (resueltas en la arquitectura v1.1: UV, PostgreSQL en tests, TypeScript ligero) |
| **1** | `specs/auth/`          | Autenticación, RBAC y Perfiles | `platform`                   | R5.1, R5.2, R5.3, R5.6, R5.8, R5.9                                                            | Roles, permisos por rol, gestión de perfiles        | Estrategia de JWT (token único o access + refresh)                       |
| **2** | `specs/events/`        | Eventos y Catálogo             | `auth`                       | R3.6 (`pg_trgm`), R4.4 (caché Redis), R2.5 (cupos desde la API)                               | Imágenes WebP, lazy loading de componentes, caching | — (diseño de imágenes resuelto en la arquitectura v1.1 §3.8)             |
| **3** | `specs/sessions/`      | Programación de Sesiones       | `events`                     | R3.4 (solapamiento), R5.3 (propiedad del evento)                                              | —                                                   | —                                                                        |
| **4** | `specs/registrations/` | Inscripciones y Capacidad      | `auth`, `events`, `sessions` | R3.4 (límites y concurrencia), R3.6 (bloqueos en PostgreSQL), R5.4, R5.8, R4.4 (invalidación) | —                                                   | —                                                                        |
| **5** | `specs/delivery/`      | Entrega                        | Todos                        | R3.9 (cobertura)                                                                              | —                                                   | —                                                                        |

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
|   0   | `platform`      | Implementada           | 1.0     | 2026-10-31           |
|   1   | `auth`          | Pendiente de redacción | —       | —                    |
|   2   | `events`        | Pendiente de redacción | —       | —                    |
|   3   | `sessions`      | Pendiente de redacción | —       | —                    |
|   4   | `registrations` | Pendiente de redacción | —       | —                    |
|   5   | `delivery`      | Pendiente de redacción | —       | —                    |
