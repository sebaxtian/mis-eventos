# Plan técnico: Inscripciones y Capacidad (`registrations`)

| Campo                  | Valor                                 |
| ---------------------- | ------------------------------------- |
| **ID del dominio**     | `REG`                                 |
| **Spec de referencia** | `specs/registrations/spec.md` v1.0    |
| **Plan de referencia** | `specs/registrations/plan.md`         |
| **Fecha**              | 2026-11-01                            |

> Este plan describe **cómo** se implementará `specs/registrations/spec.md`. No añade comportamiento: si algo no está en `spec.md`, primero se agrega allí (R1.1, R1.5). Identificadores en inglés (Principio 6). Nada de este plan se ejecuta hasta que la spec esté _Aprobada_ (R1.8).

## 1. Modelo `Registration` y tabla `registrations`

Se define en `backend/app/registrations/models.py` con `SQLModel` (`table=True`).

| Columna      | Tipo SQL                   | Nullabilidad | `PK` / `FK` / `CHECK` / `DEFAULT`                                                                     |
| ------------ | -------------------------- | ------------ | ------------------------------------------------------------------------------------------------------- |
| `id`         | `INTEGER` (identity)       | `NOT NULL`   | `PRIMARY KEY`, autoincremental.                                                                          |
| `user_id`    | `INTEGER`                  | `NOT NULL`   | `FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT` (`fk_registrations_user_id_users`).       |
| `event_id`   | `INTEGER`                  | `NOT NULL`   | `FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE` (`fk_registrations_event_id_events`).    |
| `session_id` | `INTEGER`                  | `NULL`       | `FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE` (`fk_registrations_session_id_sessions`). |
| `status`     | `VARCHAR(20)`              | `NOT NULL`   | `CHECK (status IN ('ACTIVE','CANCELLED'))` (`ck_registrations_status`); `server_default 'ACTIVE'`.        |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | `NOT NULL`   | `DEFAULT now()`; asignado también con `utc_now()` desde la aplicación.                                    |
| `updated_at` | `TIMESTAMP WITH TIME ZONE` | `NOT NULL`   | `DEFAULT now()`; actualizado por la aplicación en reactivación y cancelación.                             |

```python
class RegistrationStatus(str, Enum):
    ACTIVE = "ACTIVE"
    CANCELLED = "CANCELLED"
```

Convenciones:

- `user_id` y `event_id` son inmutables; se toman del token y de la ruta, nunca del cuerpo.
- `session_id` es `NULL` para la inscripción al evento y no nulo para la de sesión.
- La pertenencia `session.event_id == registration.event_id` se valida en el servicio: un `CHECK` de PostgreSQL no puede consultar otra tabla y se descarta un trigger (R4.5).
- `updated_at` se actualiza con `utc_now()` al reactivar y al cancelar; `created_at` no cambia nunca.

## 2. Restricciones e índices

### 2.1. Restricciones

| Constraint                          | Definición                                                     | Motivo                                                        |
| ----------------------------------- | -------------------------------------------------------------- | ------------------------------------------------------------- |
| `ck_registrations_status`           | `status IN ('ACTIVE','CANCELLED')`                              | Refuerza `REG-BR-01` ante escrituras fuera de la API.          |
| `fk_registrations_user_id_users`    | `user_id → users.id ON DELETE RESTRICT`                         | Integridad: un usuario con inscripciones no se borra.          |
| `fk_registrations_event_id_events`  | `event_id → events.id ON DELETE CASCADE`                        | Borrar un evento sin inscritos activos elimina sus inscripciones por cascada (`EVT-BR-07`). |
| `fk_registrations_session_id_sessions` | `session_id → sessions.id ON DELETE CASCADE`                 | Borrar una sesión sin inscritos activos elimina sus inscripciones por cascada (`SES-BR-11`). |

### 2.2. Índices únicos parciales (red de seguridad de `REG-BR-06`)

```sql
CREATE UNIQUE INDEX uq_registrations_active_event
    ON registrations (user_id, event_id)
    WHERE status = 'ACTIVE' AND session_id IS NULL;

CREATE UNIQUE INDEX uq_registrations_active_session
    ON registrations (user_id, session_id)
    WHERE status = 'ACTIVE' AND session_id IS NOT NULL;
```

En SQLModel se declaran con `Index(..., unique=True, postgresql_where=text("..."))`. La violación de unicidad se captura en el servicio (`IntegrityError` → `rollback` → `409` de duplicado), nunca se propaga como `500`.

### 2.3. Índices de consulta

| Índice                                      | Columnas                        | Uso                                                              |
| ------------------------------------------- | ------------------------------- | ---------------------------------------------------------------- |
| `ix_registrations_event_id_status`          | `(event_id, status)`            | Conteo del evento, listado por evento y filtro `status`.          |
| `ix_registrations_session_id_status`        | `(session_id, status)`          | Conteo por sesión y cascada de cancelación.                       |
| `ix_registrations_user_id_status_created_at` | `(user_id, status, created_at)` | `/me` con orden `created_at DESC, id DESC` y filtro `status`.      |

No se crean índices trigrama ni GIN: no hay búsqueda de texto en este dominio.

## 3. Migración Alembic

- **Archivo:** `backend/migrations/versions/0005_create_registrations.py`.
- `revision = "0005_create_registrations"`, `down_revision = "0004_create_sessions"`.
- **`upgrade()`:**
  1. `op.create_table("registrations", ...)` con las columnas de §1, `PrimaryKeyConstraint("id")`, las tres `ForeignKeyConstraint` con sus nombres y `ondelete` (`RESTRICT` para `user_id`, `CASCADE` para `event_id` y `session_id`), y `CheckConstraint` de estado.
  2. `op.create_index("uq_registrations_active_event", "registrations", ["user_id", "event_id"], unique=True, postgresql_where=sa.text("status = 'ACTIVE' AND session_id IS NULL"))`.
  3. `op.create_index("uq_registrations_active_session", "registrations", ["user_id", "session_id"], unique=True, postgresql_where=sa.text("status = 'ACTIVE' AND session_id IS NOT NULL"))`.
  4. Los tres índices de consulta de §2.3.
- **`downgrade()`:** elimina los índices en orden inverso y después la tabla.
- **Registro del modelo:** añadir `from app.registrations import models  # noqa: F401` en `backend/migrations/env.py` para que `SQLModel.metadata` y el `TRUNCATE` de `tests/conftest.py` incluyan `registrations`.
- **Router:** registrar `app.registrations.router.router` en `backend/app/main.py`.
- **Configuración:** no se añaden variables de entorno; el TTL de la caché de `/me` reutiliza `settings.cache_events_ttl_seconds` (60 s).

## 4. Schemas (`backend/app/registrations/schemas.py`)

1. **`RegistrationEventSummary`:** `id`, `title`, `date` (`UTCDateTime`), `status` (`EventStatus`). Sin cupos.
2. **`RegistrationSessionSummary`:** `id`, `title`, `speaker`, `start_time`, `end_time` (`UTCDateTime`).
3. **`RegistrationRead`:** `id`, `user_id`, `event_id`, `session_id`, `status` (`RegistrationStatus`), `event`, `session`, `created_at`, `updated_at` (`UTCDateTime`). **Nunca** `full_name`, `email` ni `password_hash` (R5.5, R5.8).
4. **`RegistrationListRead`:** reutiliza `PaginatedResponse[RegistrationRead]` de `app/core/pagination.py` (sobre `{ items, total, page, size, pages }`).
5. **`RegistrationListParams(PaginationParams)`:** `page`, `size`, `status: RegistrationStatus | None`, `event_id: int | None` (`Query(ge=1)`) para `/me`; y una variante `EventRegistrationListParams` sin `event_id` para el listado por evento. Un `status` fuera del enum cae en `422` con el mensaje traducido de `core/exceptions.py`.
6. **`RegistrationCreate`:** no se define; los `POST` no reciben cuerpo (spec §5.4). Los routers declaran la firma sin parámetro de body.

## 5. Servicio (`backend/app/registrations/service.py`)

### 5.1. Constantes de mensajes (español, comparadas literalmente en los tests)

```python
EVENT_NOT_FOUND_DETAIL = "Evento no encontrado"
SESSION_NOT_FOUND_DETAIL = "Sesión no encontrada"
REGISTRATION_NOT_FOUND_DETAIL = "Inscripción no encontrada"
EVENT_FULL_DETAIL = "No hay cupos disponibles para este evento"
SESSION_FULL_DETAIL = "No hay cupos disponibles para esta sesión"
ALREADY_REGISTERED_EVENT_DETAIL = "Ya estás inscrito en este evento"
ALREADY_REGISTERED_SESSION_DETAIL = "Ya estás inscrito en esta sesión"
EVENT_REGISTRATION_REQUIRED_DETAIL = "Debes inscribirte primero al evento"
```

### 5.2. Funciones de conteo (sustituyen los hooks)

```python
def count_active_event_registrations(db: DBSession, event_id: int) -> int:
    return int(db.exec(
        select(func.count()).select_from(Registration).where(
            Registration.event_id == event_id,
            Registration.session_id.is_(None),
            Registration.status == RegistrationStatus.ACTIVE.value,
        )
    ).one())

def count_active_session_registrations(db: DBSession, session_id: int) -> int:
    return int(db.exec(
        select(func.count()).select_from(Registration).where(
            Registration.session_id == session_id,
            Registration.status == RegistrationStatus.ACTIVE.value,
        )
    ).one())
```

**Sustitución de hooks sin cambiar la firma:**

- `backend/app/events/service.py::get_registered_count(session, event_id)` conserva nombre, parámetros y tipo de retorno; su cuerpo pasa a `return count_active_event_registrations(session, event_id)` importando `count_active_event_registrations` de `app.registrations.service`.
- `backend/app/sessions/service.py::get_session_registered_count(session, session_id)` igual, delegando en `count_active_session_registrations`.
- Se mantiene el `import` a nivel de módulo solo de `app.registrations.models` en el caso de los conteos inline; para evitar cualquier ciclo, los servicios de `events`/`sessions` importan las funciones de conteo de `app.registrations.service`, y `app.registrations.service` importa únicamente `app.events.models`, `app.sessions.models` y `app.users.models` (nunca `app.events.service` ni `app.sessions.service`).
- Los tests existentes que hacen `monkeypatch.setattr("app.events.service.get_registered_count", ...)` siguen funcionando porque la referencia se resuelve en el módulo de `events`.

### 5.3. Bloqueos y transacción

```python
def _lock_event(db: DBSession, event_id: int) -> Event:
    event = db.exec(
        select(Event).where(Event.id == event_id).with_for_update()
        .execution_options(populate_existing=True)
    ).first()
    if event is None:
        raise HTTPException(404, EVENT_NOT_FOUND_DETAIL)
    return event

def _lock_session(db: DBSession, event_id: int, session_id: int) -> Session:
    row = db.exec(
        select(Session).where(Session.id == session_id, Session.event_id == event_id)
        .with_for_update().execution_options(populate_existing=True)
    ).first()
    if row is None:
        raise HTTPException(404, SESSION_NOT_FOUND_DETAIL)
    return row
```

Orden obligatorio: `_lock_event` **siempre primero**; `_lock_session` solo después, y únicamente en las operaciones de sesión. El `DELETE` de una inscripción al evento bloquea solo `events` (la cascada únicamente reduce contadores).

### 5.4. Alta al evento (`create_event_registration`)

1. `event = _lock_event(db, event_id)`.
2. Si `EventStatus(event.status) != PUBLISHED` → `404 "Evento no encontrado"`.
3. Buscar fila existente: `WHERE user_id = :uid AND event_id = :eid AND session_id IS NULL`.
4. Si existe y `status == ACTIVE` → `409 "Ya estás inscrito en este evento"`.
5. `count = count_active_event_registrations(db, event_id)`; si `count >= event.total_capacity` → `409 "No hay cupos disponibles para este evento"`.
6. Si existe y `status == CANCELLED`: `row.status = ACTIVE`, `row.updated_at = utc_now()`, `commit`, respuesta `200`.
7. Si no existe: `Registration(user_id=..., event_id=..., session_id=None, status=ACTIVE, created_at=now, updated_at=now)`, `commit`, respuesta `201`.
8. `except IntegrityError` (índice único parcial) → `rollback` → `409` de duplicado correspondiente.
9. `except HTTPException` → `rollback` y propagar.
10. Tras `commit`: invalidar `registrations:me:{user_id}:` y `events:`.

### 5.5. Alta a sesión (`create_session_registration`)

1. `event = _lock_event(db, event_id)`.
2. Si el evento no está `PUBLISHED` → `404 "Evento no encontrado"`.
3. `session_row = _lock_session(db, event_id, session_id)`; si no existe o es de otro evento → `404 "Sesión no encontrada"`.
4. Inscripción al evento: `WHERE user_id = :uid AND event_id = :eid AND session_id IS NULL AND status = 'ACTIVE'`; si no hay → `409 "Debes inscribirte primero al evento"`.
5. Fila existente de sesión: `WHERE user_id = :uid AND session_id = :sid`.
6. Si existe y `ACTIVE` → `409 "Ya estás inscrito en esta sesión"`.
7. `count = count_active_session_registrations(db, session_id)`; si `count >= session_row.capacity` → `409 "No hay cupos disponibles para esta sesión"`.
8. Reactivar (`200`) o crear (`201`) con `event_id` de la ruta y `session_id` de la ruta. La reactivación reutiliza la comprobación del paso 4, de modo que una fila `CANCELLED` de sesión **no** se reactiva si el usuario ya no tiene inscripción `ACTIVE` al evento (paso 4 → `409`).
9. No se recalcula ni se modifica el contador del evento: el cupo del evento ya lo ocupa la inscripción al evento (D2).
10. Invalidación de caché igual que en §5.4.

### 5.6. Cancelación (`cancel_registration`)

1. Resolver la fila visible para el actor (§7.3); si no existe o no es visible → `404 "Inscripción no encontrada"`.
2. `_lock_event(db, row.event_id)`; si `row.session_id is not None`, `_lock_session(db, row.event_id, row.session_id)`.
3. Si `row.status == CANCELLED` → `commit`/`rollback` sin cambios y respuesta `204` (idempotencia).
4. `row.status = CANCELLED`, `row.updated_at = utc_now()`.
5. Si `row.session_id is None` (inscripción al evento): `UPDATE registrations SET status='CANCELLED', updated_at=now WHERE user_id = :uid AND event_id = :eid AND session_id IS NOT NULL AND status = 'ACTIVE'` (cascada de D12, en la misma transacción). Si `row.session_id` **no** es `NULL` (inscripción a sesión), no se ejecuta ninguna otra actualización: la inscripción al evento y las demás sesiones quedan intactas y solo se libera el cupo de esa sesión.
6. `commit` y `204`.
7. Invalidar `registrations:me:{row.user_id}:` y `events:`.

### 5.7. Consultas

- `list_my_registrations(db, actor, params)`: `WHERE user_id = actor.id` + filtros opcionales; `ORDER BY created_at DESC, id DESC`; `count` y página con `offset`/`limit`; DTOs con resúmenes de evento y sesión (una consulta por página con `selectinload` implícito mediante `JOIN` explícito o `db.get` en lote; se elige la opción más simple: `session.exec(select(Registration, Event, Session).join(...))`).
- `list_event_registrations(db, event, params)`: `WHERE event_id = event.id AND session_id IS NULL` + filtro `status`; mismo orden y sobre paginado; `total` cuenta solo inscripciones al evento (una por asistente), nunca filas de sesión.
- `get_registration_read(db, registration)`: construye el DTO con `event` y `session`.
- `to_registration_read(registration, event, session_row)` es la única fábrica del DTO.

### 5.8. Borrado del padre y cascada (D15)

- No se implementa ninguna función de purga ni se modifica `app/events/service.py::delete_event` ni `app/sessions/service.py::delete_session`.
- Las FKs `event_id`/`session_id` son `ON DELETE CASCADE`: al borrar físicamente un evento o una sesión sin inscripciones `ACTIVE` (los guards `EVT-BR-07`/`SES-BR-11` ya lo garantizan), PostgreSQL elimina sus inscripciones —incluido el histórico `CANCELLED`— dentro de la misma transacción del `DELETE`.
- El contrato observable de `events`/`sessions` no cambia (`204` sin inscripciones activas, `409` con ellas) y `registrations` no depende de sus servicios; solo comparte el modelo para los conteos.
- Efecto lateral aceptado: al borrar un evento desaparecen también las inscripciones a sus sesiones por la cascada en dos niveles (evento → sesión → inscripción), sin dejar huérfanas.

## 6. Autorización (`backend/app/registrations/dependencies.py`)

1. **`require_attendee = require_roles(UserRole.ATTENDEE)`:** `401` sin token válido (con `WWW-Authenticate: Bearer`), `403` para `ORGANIZER` y `ADMIN` (`AUTH-BR-12`).
2. **`get_owned_event_for_organizer`:** `require_roles(UserRole.ORGANIZER, UserRole.ADMIN)` + `Path(ge=1)`; evento inexistente → `404 "Evento no encontrado"`; actor no `ADMIN` y `event.organizer_id != current_user.id` → `403 "No tienes permisos para realizar esta acción"`. Se define en este módulo (no se reutiliza el de `sessions`) para no acoplar semánticas.
3. **`get_registration_for_actor`:** carga la inscripción con su evento; si no existe → `404`; si el actor es `ADMIN` → visible; si es el `ORGANIZER` propietario del evento → visible; si `registration.user_id == current_user.id` → visible; en cualquier otro caso → `404 "Inscripción no encontrada"` (nunca `403`, para no enumerar).
4. **Cadena de orden:** token (`401`) → rol (`403`) → recurso (`404`) → reglas de negocio (`409`) → schema (`422`).
5. **Evento visible para el alta:** el `ATTENDEE` no usa `get_visible_event` de `sessions`; el servicio aplica directamente la regla de `REG-BR-07` (`PUBLISHED` o `404`).

## 7. Router (`backend/app/registrations/router.py`)

- **Dos routers en un módulo**, ambos con tag `registrations`:
  - `router = APIRouter(prefix="/api", tags=["registrations"])` para `/registrations/me`, `/registrations/{id}` y `DELETE /registrations/{id}`.
  - `events_router = APIRouter(prefix="/api/events", tags=["registrations"])` para las dos altas y el listado por evento; se registran ambos en `app/main.py`.
- **Operaciones y códigos:**

| Operación                                                          | Éxito        | `responses`                                      |
| ------------------------------------------------------------------ | ------------ | ------------------------------------------------ |
| `POST /api/events/{event_id}/registrations`                        | `201` / `200` | `error_responses(401, 403, 404, 409, 422)`       |
| `POST /api/events/{event_id}/sessions/{session_id}/registrations`  | `201` / `200` | `error_responses(401, 403, 404, 409, 422)`       |
| `DELETE /api/registrations/{id}`                                   | `204`        | `error_responses(401, 403, 404, 409, 422)`       |
| `GET /api/registrations/me`                                        | `200`        | `error_responses(401, 403, 404, 409, 422)`       |
| `GET /api/events/{event_id}/registrations`                         | `200`        | `error_responses(401, 403, 404, 409, 422)`       |
| `GET /api/registrations/{id}`                                      | `200`        | `error_responses(401, 403, 404, 409, 422)`       |

- El `POST` que puede responder `201` o `200` se declara con `status_code=status.HTTP_201_CREATED` y `response_model=RegistrationRead`; el servicio devuelve la tupla `(dto, created: bool)` y el router ajusta `response.status_code = 200` cuando `created is False`.
- `Path(ge=1)` en `event_id`, `session_id` e `id` para que un valor no entero o `< 1` caiga en `422`.
- **`400` no se declara** en ninguna operación (la spec lo documenta como no usado).
- **OpenAPI:** los schemas `RegistrationRead`, `RegistrationEventSummary`, `RegistrationSessionSummary` y `RegistrationListRead` aparecen referenciados; `RegistrationCreate` no existe.

## 8. Caché Redis

- **Clave:** `registrations:me:{user_id}:page={page}:size={size}:status={status}:event={event_id}` con `status`/`event_id` vacíos cuando no se envían.
- **TTL:** `settings.cache_events_ttl_seconds` (60 s); no se añade variable nueva.
- **Lectura:** en `list_my_registrations` se intenta `cache.get(key)`; si el payload es un `dict` válido se valida con `PaginatedResponse[RegistrationRead].model_validate` y se devuelve; si falla la validación se registra un `warning` y se consulta PostgreSQL.
- **Escritura:** `cache.set(key, response.model_dump(mode="json"), ttl_seconds=...)`.
- **Invalidación:** tras cada alta, reactivación o cancelación se llama a `cache.invalidate_prefix(f"registrations:me:{user_id}:")` **y** a `cache.invalidate_prefix("events:")` (los contadores viven en `EventRead`/`SessionRead`).
- **Degradación:** `RedisError` y `ValueError`/`TypeError` se capturan en helpers `_cache_get`/`_cache_set`/`_invalidate` con `logger.warning` en inglés; la petición continúa (R4.4). Se reutiliza el patrón ya existente en `app/events/service.py`.
- **No se cachean** el listado por evento ni el detalle.

## 9. OpenAPI y errores

- Formato de error de `platform`: `{"detail": "..."}` en español; en `422`, `detail = "Error de validación en los datos enviados"` más `errors: [{"field", "message"}]` traducidos por `app/core/exceptions.py` (ya soporta `enum`, `missing`, `int_parsing`, `greater_than_equal`, `less_than_equal` y `extra_forbidden`).
- Los mensajes de negocio se definen como constantes del servicio y los tests comparan el `detail` exacto (evita deriva de mensajes).
- `IntegrityError` se captura y se traduce a `409`; nunca se expone SQL ni el nombre del índice (R5.8).

## 10. Frontend

### 10.1. `frontend/src/types/api.ts`

```ts
export type RegistrationStatus = 'ACTIVE' | 'CANCELLED'

export interface RegistrationEventSummary {
  id: number
  title: string
  date: string
  status: EventStatus
}

export interface RegistrationSessionSummary {
  id: number
  title: string
  speaker: string
  start_time: string
  end_time: string
}

export interface RegistrationRead {
  id: number
  user_id: number
  event_id: number
  session_id: number | null
  status: RegistrationStatus
  event: RegistrationEventSummary
  session: RegistrationSessionSummary | null
  created_at: string
  updated_at: string
}

export type RegistrationListResponse = PaginatedResponse<RegistrationRead>

export interface RegistrationListQuery {
  page?: number
  size?: number
  status?: RegistrationStatus
  event_id?: number
}
```

### 10.2. `frontend/src/services/registrations.ts`

- `fetchMyRegistrationsApi(query)` → `GET /registrations/me`.
- `fetchEventRegistrationsApi(eventId, query)` → `GET /events/${eventId}/registrations`.
- `fetchRegistrationByIdApi(id)` → `GET /registrations/${id}`.
- `registerForEventApi(eventId)` → `POST /events/${eventId}/registrations` sin cuerpo.
- `registerForSessionApi(eventId, sessionId)` → `POST /events/${eventId}/sessions/${sessionId}/registrations` sin cuerpo.
- `cancelRegistrationApi(id)` → `DELETE /registrations/${id}`.
- Usa `apiClient` (`baseURL: '/api'`); nunca rutas absolutas (R2.1).

### 10.3. `frontend/src/stores/registrations.ts` (`useRegistrationStore`)

- **Estado:** `items`, `total`, `page`, `size`, `pages`, `currentRegistration`, `isLoading`, `isSubmitting`, `errorMessage`, `fieldErrors`, `lastCreatedStatus` (`'created' | 'reactivated' | null`).
- **Acciones:** `fetchMyRegistrations(query)`, `fetchEventRegistrations(eventId, query)`, `fetchRegistrationById(id)`, `registerForEvent(eventId)`, `registerForSession(eventId, sessionId)`, `cancelRegistration(id)`, `clearErrors()`, `reset()`.
- **Sin cálculos:** el store guarda `status` y los resúmenes tal cual llegan; no resta cupos ni deduce capacidades (R2.5). El estado del cupo se lee de `event.available_capacity` y `session.available_capacity` que ya entrega la API.
- **Errores:** extrae `detail` y `errors[]` del `AxiosError` y los expone en español; el interceptor global sigue gestionando `401`/`403` (R5.6). Tras un alta o cancelación, el store invalida su propia lista (`items = []`) para forzar recarga desde el servidor.

### 10.4. Vistas y componentes

1. **`ProfileView.vue` — sección "Mis inscripciones":**
   - Carga `fetchMyRegistrations({ page, size: 10, status })` al montar y al cambiar de página o filtro.
   - Muestra título del evento, fecha formateada en español con `timeZone: 'UTC'`, estado traducido (`Activa`/`Cancelada`), resumen de sesión si existe y botón "Cancelar inscripción" con `window.confirm`.
   - Estados: `BaseSkeleton` mientras carga, mensaje "Todavía no tienes inscripciones." si `items` está vacío, `BaseAlert` con el `detail` en español si falla, y paginación con `BaseButton` anterior/siguiente.
   - Tras cancelar: feedback "Inscripción cancelada correctamente." y recarga.
2. **`EventDetailView.vue` — acción de inscripción al evento:**
   - Sustituye el bloque `data-testid="registration-placeholder"` por un bloque visible solo si `authStore.role === 'ATTENDEE'` y `event.status === 'PUBLISHED'`.
   - Botón "Inscribirme" deshabilitado si `event.available_capacity === 0` con aviso "No hay cupos disponibles para este evento".
   - Estado propio: `myEventRegistration` derivado de `fetchMyRegistrations({ event_id: id, status: 'ACTIVE', size: 50 })` buscando la fila con `session_id === null`; si existe, muestra "Ya estás inscrito en este evento" y permite cancelar.
   - Tras el alta/cancelación: refresca `store.fetchEventById(id)` y `sessionStore.fetchSessions(id)` para leer los contadores reales de la API; feedback de éxito o el `detail` del `409`.
3. **`EventDetailView.vue` — inscripción a sesiones:**
   - Usa el slot `#actions` de `SessionTimeline.vue` para `ATTENDEE`: botón "Inscribirme a esta sesión" por sesión, deshabilitado si `session.available_capacity === 0` con aviso, y "Ya estás inscrito" si el store tiene una inscripción activa con ese `session_id`.
   - Si no hay inscripción activa al evento, el control se deshabilita y se muestra "Debes inscribirte primero al evento" como ayuda de UX; el backend sigue siendo la autoridad (`409`).
4. **`EventDetailView.vue` — listado para organizador/`ADMIN`:**
   - Nuevo componente `frontend/src/components/registrations/EventRegistrationsList.vue` cargado con `defineAsyncComponent` y `BaseSpinner` como `loadingComponent` (lazy loading, bonus obligatorio).
   - Props: `eventId`, `canManage`. Paginación y filtro por estado; columnas: `user_id` (`Usuario #12`), estado traducido y fecha de creación (una fila por asistente, porque el endpoint solo devuelve inscripciones al evento). Sin `full_name` ni `email`.
   - Se muestra solo si `canManage` es verdadero (mismo cálculo ya existente en el detalle).
5. **Rutas:** no se añaden. "Mis inscripciones" vive en `/profile`; el listado por evento, en `/events/:id`.
6. **Prohibiciones:** sin `v-html` (R5.9), sin librerías de componentes (R4.3), sin cálculos de cupo (R2.5).

## 11. Estrategia de pruebas backend

- **Archivo:** `backend/tests/test_registrations.py`.
- **Base:** PostgreSQL real `mis_eventos_test` con la migración `0005_create_registrations` aplicada por el fixture `test_engine` (R3.6). Nunca SQLite.
- **Helpers:** usuarios `ADMIN`, `ORGANIZER` y `ATTENDEE`; eventos en cada estado; sesiones con capacidad; tokens con `create_access_token`; `FakeCache` para espiar claves e invalidaciones.
- **Casos por criterio:**
  - `REG-AC-01`: alta válida, DTO completo, `session_id = null`, contador del evento +1 y `EventRead` coherente.
  - `REG-AC-02`/`REG-AC-03`: `total_capacity = 2` con 1 y 2 inscripciones; tercera → `409`.
  - `REG-AC-04`: fixture concurrente (§11.1).
  - `REG-AC-05`/`REG-AC-06`/`REG-AC-07`/`REG-AC-08`: duplicado, reactivación `200`, reactivación sin cupo, reactivación con evento `CANCELLED`.
  - `REG-AC-09`: alta en `DRAFT` y en `CANCELLED` → `404`.
  - `REG-AC-10`: `PATCH` del evento a `CANCELLED` y verificación de que las inscripciones siguen `ACTIVE` y el contador no cambia.
  - `REG-AC-11`: `401` sin token y con token expirado; `403` para `ORGANIZER` y `ADMIN`.
  - `REG-AC-12` a `REG-AC-17`: alta a sesión, requisito previo, sesión de otro evento, capacidad de sesión, concurrencia, duplicado y reactivación; la reactivación con inscripción al evento `CANCELLED` o inexistente → `409 "Debes inscribirte primero al evento"` y la fila sigue `CANCELLED`.
  - `REG-AC-18` a `REG-AC-21`: cancelación, idempotencia, cascada evento → sesiones, permisos y `404`; cancelar una inscripción **a sesión** deja intactas la inscripción al evento y las demás sesiones (mismos contadores) y solo libera el cupo de esa sesión.
  - `REG-AC-22` a `REG-AC-24`: `/me` paginado, orden, vacío, filtros, `422` y aislamiento por usuario.
  - `REG-AC-25`/`REG-AC-26`: listado por evento solo con filas `session_id IS NULL` (crear una inscripción al evento y otra a sesión y comprobar que solo aparece la primera), `total` coherente, ausencia de `full_name`/`email` en el JSON, `403` y `404`.
  - `REG-AC-27`: detalle visible y no visible.
  - `REG-AC-28`/`REG-AC-29`: `FakeCache` registra claves y prefijos; con `RedisError` las respuestas siguen siendo correctas.
  - `REG-AC-30`: mensajes exactos y ausencia de `400`.
  - `REG-AC-31`: `/api/openapi.json` con las seis rutas, tag, schemas y códigos.
  - `REG-AC-32`: `sqlalchemy.inspect` sobre columnas, FKs (`user_id` con `ondelete == "RESTRICT"`; `event_id` y `session_id` con `ondelete == "CASCADE"`), `CHECK`, índices únicos parciales e índices de consulta.
  - `REG-AC-33`: conteos reales reflejados en `EventRead`/`SessionRead` y hooks monkeypatcheables.
  - `REG-AC-34`: `DELETE /api/events/{id}` y `DELETE /api/events/{id}/sessions/{sid}` con solo histórico `CANCELLED` → `204` y cero filas por la cascada de las FKs, sin purga en `delete_event`/`delete_session`; con inscripción `ACTIVE` → `409` y las filas intactas.

### 11.1. Fixture de concurrencia

- No se usa `db_session`: una sola conexión con `SAVEPOINT` no permite dos transacciones independientes.
- `concurrent_registrations`: dos `Session` sobre dos `Connection` distintas de `test_engine` con `autocommit=False`; siembra de usuarios, evento y sesión con una tercera conexión y `commit`.
- Ejecución en hilos (`ThreadPoolExecutor`) con una `Barrier` para que compitan; se invoca el servicio (o el endpoint con `TestClient` sobre una app con `dependency_overrides` por conexión) y se verifica un `201` y un `409`.
- Verificación final con una conexión nueva: `SELECT count(*)` de filas `ACTIVE` es exactamente `total_capacity` (evento) o `capacity` (sesión).
- Limpieza con `db_truncate`; repetir el test 3 veces para descartar intermitencias (R3.7).
- Se reutiliza el patrón ya probado en `sessions` (`concurrent_sessions`).

### 11.2. Otros puntos de prueba

- **Monkeypatch:** `monkeypatch.setattr("app.events.service.get_registered_count", lambda session, event_id: 3)` debe seguir afectando a `EventRead`, lo que demuestra que la firma no cambió.
- **Cobertura:** `uv run pytest --cov=app --cov-report=xml --cov-report=term-missing`; el dominio debe cubrir `models`, `schemas`, `dependencies`, `service` y `router`.

## 12. Estrategia de pruebas frontend

- **Archivos:** `frontend/src/__tests__/registrations.store.spec.ts`, `registrations.views.spec.ts` y `registrations.components.spec.ts`.
- **Store:** carga de `/me`, paginación, filtros, alta (`201` y `200`), cancelación, mapeo de `409`/`422` a `errorMessage`/`fieldErrors` y ausencia de cálculo de cupos.
- **`ProfileView.vue`:** render de la sección, estado vacío, paginación y cancelación con confirmación.
- **`EventDetailView.vue`:** botón visible solo para `ATTENDEE` en `PUBLISHED`; deshabilitado con `available_capacity === 0`; ausente para `ORGANIZER`/`ADMIN`; refresco de contadores tras el alta; aviso "Debes inscribirte primero al evento" en sesiones.
- **`EventRegistrationsList.vue`:** paginación, filtro por estado, columna `user_id` y ausencia de `full_name`/`email`; carga diferida verificada con `defineAsyncComponent`.
- **Comandos:** `npm run test -- --run`, `npx vitest run --coverage`, `npx vue-tsc --noEmit`, `npm run build`.

## 13. Riesgos y mitigaciones

| Riesgo                                                            | Mitigación                                                                                                                       |
| ----------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| Carrera en el último cupo                                         | `SELECT ... FOR UPDATE` sobre `events` (y `sessions`) + prueba concurrente con dos conexiones y `Barrier` (R3.6, R5.4).            |
| Duplicado activo por una ruta futura                              | Índices únicos parciales + traducción de `IntegrityError` a `409`.                                                                |
| Interbloqueo con escrituras de `sessions`                         | Orden fijo `events` → `sessions`, idéntico al de `SES-BR-08`.                                                                     |
| Doble conteo de cupo de evento                                    | El contador del evento filtra `session_id IS NULL`; prueba explícita con un usuario inscrito a tres sesiones.                     |
| `500` al borrar un evento o sesión con histórico cancelado        | D15: FKs `ON DELETE CASCADE` en `event_id`/`session_id`; el borrado elimina las filas por cascada y `delete_event`/`delete_session` no cambian; prueba `REG-AC-34`. |
| Borrado accidental de inscripciones `ACTIVE` por cascada           | Los guards `EVT-BR-07`/`SES-BR-11` devuelven `409` antes de llegar al `DELETE` cuando `registered_count > 0`; prueba `REG-AC-34` con inscripción activa. |
| Fuga de caché entre usuarios                                      | `user_id` dentro de la clave de `/me`; prueba con dos usuarios y `FakeCache`.                                                     |
| Caché obsoleta de eventos tras una inscripción                    | Invalidación de `events:` en cada escritura, incluso si falla Redis.                                                              |
| Cambiar la firma de los hooks y romper tests existentes           | Se conserva nombre, parámetros y retorno; se delega en el conteo real y se verifica con `monkeypatch`.                            |
| Mensajes de error inconsistentes                                  | Constantes en el servicio y aserciones sobre el `detail` exacto.                                                                  |
| Enumeración de inscripciones o eventos ajenos                     | `404 "Inscripción no encontrada"` y `404 "Evento no encontrado"`; `403` solo en el listado de gestión.                            |
| Frontend recalculando cupos                                       | El store y las vistas consumen `available_capacity` de la API; test que verifica que no se resta nada.                            |
| Aislamiento de tests contaminado                                  | `db_truncate` incluye `registrations` al estar en `SQLModel.metadata`; el test concurrente limpia con `TRUNCATE ... CASCADE`.      |
| Migración con orden roto                                          | `down_revision = "0004_create_sessions"`, import del modelo en `env.py` y verificación con `alembic current`.                     |
| Cuerpo inesperado en los `POST`                                   | Los endpoints no declaran body; el servidor ignora cualquier cuerpo y toma `user_id` del token y los ids de la ruta.              |

## 14. Dependencias, librerías de soporte y aprobación

### 14.1. Dependencias

- `platform` v1.0: formato de error, paginación, fechas UTC, Redis, OpenAPI, Docker.
- `auth` v1.0: JWT, RBAC, `require_roles`, `AUTH-BR-12`.
- `events` v1.0: `Event`, `EventStatus`, `total_capacity`, `organizer_id`, hook `get_registered_count`, prefijo `events:`.
- `sessions` v0.2: `Session`, `event_id`, `capacity`, hook `get_session_registered_count`, orden de bloqueo.

### 14.2. Librerías de soporte (R4.2)

- **No se añaden librerías nuevas.** SQLAlchemy/SQLModel, PostgreSQL, Redis, `pytest`, `pytest-cov`, Vue, Pinia, Axios, Vue Router y Vitest ya están en el stack y registradas en `MEMORY.md`.
- No se usan librerías de calendario, tablas ni componentes de UI (R4.3); el listado y la paginación se construyen con Tailwind y los componentes base existentes.

### 14.3. Decisiones que requieren aprobación

- La spec completa (`spec.md`, `plan.md`, `tasks.md`) requiere la aprobación explícita del usuario antes de implementar (R1.8). No se inicia ninguna tarea `B*`, `F*` o `V*` hasta entonces.
- D15 revisada: `event_id`/`session_id` con `ON DELETE CASCADE` y `user_id` con `RESTRICT`; no se toca `delete_event`/`delete_session` ni se añade purga. La alternativa descartada (`RESTRICT` + purga explícita) queda documentada en `spec.md` §14.
