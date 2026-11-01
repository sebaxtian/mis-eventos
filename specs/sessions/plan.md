# Plan técnico: Programación de Sesiones (`sessions`)

| Campo                  | Valor                            |
| ---------------------- | -------------------------------- |
| **ID del dominio**     | `SES`                            |
| **Spec de referencia** | `specs/sessions/spec.md` v1.0    |
| **Plan de referencia** | `specs/sessions/plan.md`         |
| **Fecha**              | 2026-10-31                       |

> Este plan describe **cómo** se implementará `specs/sessions/spec.md`. No añade comportamiento: si algo no está en `spec.md`, primero se agrega allí (R1.1, R1.5). Identificadores en inglés (Principio 6). Nada de este plan se ejecuta hasta que la spec esté _Aprobada_ (R1.8).

## 1. Modelo `Session` y tabla `sessions`

Se define en `backend/app/sessions/models.py` con `SQLModel` (`table=True`), sin campo `status` ni auditoría de usuario.

| Columna        | Tipo SQL                   | Nullabilidad | `PK` / `FK` / `CHECK` / `DEFAULT`                                                                                 |
| -------------- | -------------------------- | ------------ | ------------------------------------------------------------------------------------------------------------------- |
| `id`           | `INTEGER` (identity)       | `NOT NULL`   | `PRIMARY KEY`, autoincremental.                                                                                     |
| `event_id`     | `INTEGER`                  | `NOT NULL`   | `FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE`.                                                  |
| `title`        | `VARCHAR(160)`             | `NOT NULL`   | `CHECK (char_length(title) BETWEEN 3 AND 160)` (`ck_sessions_title_length`).                                        |
| `speaker`      | `VARCHAR(120)`             | `NOT NULL`   | `CHECK (char_length(speaker) BETWEEN 2 AND 120)` (`ck_sessions_speaker_length`).                                   |
| `description`  | `TEXT`                     | `NULL`       | `CHECK (description IS NULL OR char_length(description) <= 2000)` (`ck_sessions_description_length`).              |
| `start_time`   | `TIMESTAMP WITH TIME ZONE` | `NOT NULL`   | Almacenado en UTC.                                                                                                  |
| `end_time`     | `TIMESTAMP WITH TIME ZONE` | `NOT NULL`   | Almacenado en UTC; `CHECK (start_time < end_time)` (`ck_sessions_time_range`).                                      |
| `capacity`     | `INTEGER`                  | `NOT NULL`   | `CHECK (capacity >= 1)` (`ck_sessions_capacity_positive`) y `CHECK (capacity <= 100000)` (`ck_sessions_capacity_max`). |
| `created_at`   | `TIMESTAMP WITH TIME ZONE` | `NOT NULL`   | `DEFAULT now()`; asignado también con `utc_now()` desde la aplicación.                                              |
| `updated_at`   | `TIMESTAMP WITH TIME ZONE` | `NOT NULL`   | `DEFAULT now()`; actualizado por la aplicación (`utc_now()`) en cada `PATCH`.                                       |

Convenciones:

- El modelo importa `Session` de `sqlmodel` en el servicio como alias (`from sqlmodel import Session as DBSession`) para no colisionar con `app.sessions.models.Session`.
- Los `CHECK` de longitud son defensa en profundidad: la validación primaria es Pydantic (`422`), y las restricciones de BD protegen ante escrituras fuera de la API.
- `description` vacía se normaliza a `None` en el schema antes de persistir.
- Las fechas se gestionan con un tipo específico del dominio (ver §2.2) y se persisten como `DateTime(timezone=True)` en UTC.

## 2. Relación con `Event` y schemas

### 2.1. Relación uno a muchos

- `Event` (Dominio 2) no se modifica: no se añade `relationship` ni campo en `EventRead`.
- `Session.event_id` es `NOT NULL` e inmutable; se toma siempre de la ruta `/api/events/{event_id}/sessions`.
- La FK `ON DELETE CASCADE` garantiza que el borrado físico de un evento (permitido por `EVT-BR-07` solo con `registered_count == 0`) elimine sus sesiones sin lógica adicional en `events`.
- No se define `relationship` bidireccional en SQLModel para mantener el aislamiento del Dominio 2 (R2 y R1.1: no se toca `backend/app/events/`). Las consultas usan `event_id` explícito.

### 2.2. Schemas (`backend/app/sessions/schemas.py`)

1. **`AwareUTCDateTime`** (`Annotated[datetime, ...]`):
   - Validadores **posteriores al parseo** (`AfterValidator`), aplicados en este orden: (1) si el `datetime` ya parseado tiene `tzinfo is None`, lanza `ValueError("La fecha y hora debe incluir zona horaria (por ejemplo, Z)")`; (2) convierte a UTC con `astimezone(timezone.utc)`.
   - No se usa `BeforeValidator` para esta comprobación: recibe la entrada cruda (habitualmente `str`), no el `datetime` parseado, así que la comprobación de `tzinfo is None` debe hacerse después del parseo.
   - Serializador JSON: `isoformat().replace("+00:00", "Z")`.
   - **No** reutiliza `UTCDateTime` de `app/core/datetime_utils.py`, porque ese tipo convierte `naive` a UTC en silencio y la spec exige rechazarlo. Tampoco se modifica el comportamiento de `events`/`auth`.
2. **`SessionCreate`** (`extra="forbid"`):
   - `title: str` (`strip`, 3..160).
   - `speaker: str` (`strip`, 2..120).
   - `description: str | None = None` (`strip`; `""` → `None`; máximo 2000).
   - `start_time: AwareUTCDateTime`.
   - `end_time: AwareUTCDateTime`.
   - `capacity: int` (`ge=1`, `le=100000`).
   - `@model_validator(mode="after")`: `start_time < end_time`; si no, `ValueError("La hora de inicio debe ser anterior a la hora de fin")`.
3. **`SessionUpdate`** (`extra="forbid"`):
   - Los seis campos son opcionales (pueden omitirse), pero solo `description` admite `null` explícito; `title`, `speaker`, `start_time`, `end_time` y `capacity`, si están presentes, deben tener valor no nulo (`null` → `422`).
   - `@model_validator(mode="after")`: exige que `model_fields_set` no esté vacío (cuerpo `{}` → `ValueError("Debes indicar al menos un campo para actualizar")`); los campos presentes distintos de `description` no pueden ser `null`; `description: null` es válido y limpia la descripción.
   - La validación `start < end` se hace en el servicio sobre el par combinado, no solo en el schema, porque un `PATCH` puede enviar un único extremo.
4. **`SessionRead`:** `id`, `event_id`, `title`, `description`, `speaker`, `start_time`, `end_time`, `capacity`, `registered_count`, `available_capacity`, `created_at`, `updated_at`.
5. **`SessionListRead`:** `items: list[SessionRead]`, `total: int`.

## 3. Relaciones futuras con `Registration`

No se implementan en este dominio; se deja el contrato preparado:

- `registrations.session_id` será `INTEGER NULL` con FK a `sessions.id`; el modelo exacto se decide en `specs/registrations/`.
- La unicidad por usuario/sesión se resolverá en `registrations` (restricción o índice parcial).
- La inscripción bloqueará el evento y/o la sesión en la misma transacción y validará ambos cupos (R5.4).
- `get_session_registered_count` se reemplazará por un `COUNT(*)` real sin cambiar la firma ni `SessionRead`.

## 4. Restricciones de base de datos

| Constraint                              | Definición                                                        | Motivo                                                     |
| --------------------------------------- | ----------------------------------------------------------------- | ---------------------------------------------------------- |
| `ck_sessions_time_range`                | `start_time < end_time`                                           | Refuerza `SES-BR-05` ante escrituras fuera de la API.      |
| `ck_sessions_capacity_positive`         | `capacity >= 1`                                                   | Refuerza `SES-BR-09`.                                      |
| `ck_sessions_capacity_max`              | `capacity <= 100000`                                              | Límite superior del contrato.                              |
| `ck_sessions_title_length`              | `char_length(title) BETWEEN 3 AND 160`                            | Refuerza `SES-BR-01`.                                      |
| `ck_sessions_speaker_length`            | `char_length(speaker) BETWEEN 2 AND 120`                          | Refuerza `SES-BR-01`.                                      |
| `ck_sessions_description_length`        | `description IS NULL OR char_length(description) <= 2000`         | Refuerza `SES-BR-01`.                                      |

No se crea un constraint que compare `capacity` con `events.total_capacity`: es una regla de negocio entre tablas que se valida en el servicio dentro de la transacción (y que `registrations` deberá revalidar). Un `CHECK` con subconsulta no es válido en PostgreSQL.

## 5. Foreign keys y política de borrado

- `event_id → events.id` con `ON DELETE CASCADE`, nombre `fk_sessions_event_id_events`.
- `ON UPDATE` por defecto (`NO ACTION`): `event_id` es inmutable.
- No hay FK a `users` (no hay auditoría de usuario en la sesión).
- El borrado de una sesión es físico (`DELETE`), no lógico.
- El borrado de un evento elimina sus sesiones en cascada; no se añade código en `events`.

## 6. Índices

| Índice                            | Columnas                | Tipo    | Uso                                                                                                   |
| --------------------------------- | ----------------------- | ------- | ----------------------------------------------------------------------------------------------------- |
| `ix_sessions_event_id_start_time` | `(event_id, start_time)` | B-Tree  | Listado ordenado `WHERE event_id = ? ORDER BY start_time, id` y filtro base del solapamiento.           |
| `ix_sessions_event_id_end_time`   | `(event_id, end_time)`   | B-Tree  | Segunda mitad de la condición de solapamiento (`existing.end_time > new.start_time`) y rango de ventana. |

Justificación: PostgreSQL no indexa automáticamente las FK, por lo que `event_id` necesita un índice propio, y el listado siempre filtra por evento y ordena por `start_time`. El índice compuesto `(event_id, start_time)` cubre ambos. El índice `(event_id, end_time)` es barato y evita escaneos del subconjunto del evento cuando la condición compara `end_time`; se conserva por claridad del plan de ejecución, aunque el volumen esperado no sea alto. No se añaden índices GIN ni de texto: no hay búsqueda en sesiones.

## 7. Migración Alembic

- **Archivo:** `backend/migrations/versions/0004_create_sessions.py`.
- `revision = "0004_create_sessions"`, `down_revision = "0003_create_events"`.
- **`upgrade()`:**
  1. `op.create_table("sessions", ...)` con todas las columnas, `PrimaryKeyConstraint("id")`, `ForeignKeyConstraint(["event_id"], ["events.id"], name="fk_sessions_event_id_events", ondelete="CASCADE")` y los `CheckConstraint` de §4.
  2. `op.create_index("ix_sessions_event_id_start_time", "sessions", ["event_id", "start_time"])`.
  3. `op.create_index("ix_sessions_event_id_end_time", "sessions", ["event_id", "end_time"])`.
- **`downgrade()`:** elimina los índices en orden inverso y después la tabla.
- **Registro del modelo:** añadir `from app.sessions import models  # noqa: F401` en `backend/migrations/env.py` para que `SQLModel.metadata` y el `TRUNCATE` de `tests/conftest.py` incluyan `sessions`.
- **Router:** registrar `app.sessions.router.router` en `backend/app/main.py` (`app.include_router(sessions_router)`), con prefijo `/api/events` y tag `sessions`.
- **Configuración:** no se añaden variables nuevas. Se reutiliza `settings.cache_events_ttl_seconds` solo si en el futuro se cachean sesiones (hoy no).

## 8. Estrategia de no solapamiento

1. Condición SQL exacta, con intervalos semiabiertos:

   ```text
   existing.event_id = :event_id
   AND existing.id <> :session_id          -- solo en PATCH
   AND existing.start_time < :new_end
   AND existing.end_time > :new_start
   ```

2. Se ejecuta con `select(Session.id).where(...).limit(1)` dentro de la transacción que ya bloqueó el evento.
3. Si devuelve una fila → `HTTPException(409, detail="La sesión se solapa con otra sesión del evento")`.
4. En `PATCH`, el par final se calcula combinando `payload.start_time or session.start_time` y `payload.end_time or session.end_time`; después se validan `start < end`, ventana y solapamiento.
5. En `DELETE` no hay comprobación de solapamiento, pero sí se bloquea el evento para serializar con altas/ediciones y evitar que una comprobación concurrente use una fila que está desapareciendo.
6. Las sesiones consecutivas no disparan la condición porque el borde es estricto (`<` y `>`), no `<=`/`>=`.

## 9. Estrategia transaccional PostgreSQL

Orden de una escritura (`POST`, `PATCH`, `DELETE`):

1. **Dependencias FastAPI:** validan token (`401`), rol (`403`) y existencia/propiedad del evento (`404`/`403`) antes de entrar al servicio.
2. **Inicio de transacción** en la sesión de SQLModel de la petición.
3. **Bloqueo del evento:** `select(Event).where(Event.id == event_id).with_for_update()`. Si el evento no existe, `404 "Evento no encontrado"` antes de bloquear (la dependencia ya lo resolvió, pero el servicio revalida dentro de la transacción).
4. **Revalidación de estado:** si `event.status == CANCELLED` → `409` con el mensaje de evento cancelado.
5. **Validaciones de negocio:** ventana del evento, capacidad contra `event.total_capacity`, `get_session_registered_count` (solo para reducción futura y borrado) y solapamiento.
6. **Escritura:** `session.add(...)`, `session.delete(...)`, asignación de `updated_at = utc_now()`.
7. **`commit()`** y `refresh()` para devolver el DTO.
8. **Invalidación de caché:** `cache.invalidate_prefix("events:")` después del `commit`, capturando `RedisError` y registrando un `warning` en inglés (R4.4).

Aislamiento: `READ COMMITTED` (el valor por defecto de PostgreSQL). La fila del evento actúa como mutex lógico: la segunda transacción espera en `FOR UPDATE` hasta que la primera hace `commit`; al continuar, su consulta de solapamiento ve la fila recién insertada y responde `409`.

Manejo de errores: si una validación lanza `HTTPException`, se hace `rollback()` explícito antes de propagar para liberar el bloqueo de forma determinista y no dejar la transacción abierta.

## 10. Bloqueos y concurrencia

- **Qué se bloquea:** una única fila de `events` por escritura de sesión.
- **Duración:** desde el `SELECT ... FOR UPDATE` hasta el `commit`/`rollback`; incluye la consulta de solapamiento y la escritura.
- **Granularidad:** por evento, no por sesión. Dos altas de sesiones del mismo evento se serializan aunque no se solapen; es aceptable por el volumen y simplifica la corrección.
- **Alternativas descartadas:**
  - `EXCLUDE USING GIST (event_id WITH =, tstzrange(start_time, end_time) WITH &&)` con `btree_gist`: correcta a nivel de BD, pero exige una extensión adicional, complica la migración y el mensaje de error, y no es necesaria para el alcance (R4.5). Se documenta como alternativa no usada.
  - `pg_advisory_xact_lock(event_id)`: también serializa, pero introduce una convención global de claves y no aprovecha el bloqueo natural de la fila del evento.
- **Riesgo residual:** si en el futuro una escritura de sesión no bloquea el evento (por ejemplo, un script de mantenimiento), el invariante puede romperse. Se mitiga con la regla de que toda escritura pasa por el servicio y con la prueba concurrente.

## 11. Validación de capacidad

1. **Schema:** `capacity` entero `1..100000` (`422` fuera de rango).
2. **Servicio:** tras bloquear el evento, si `payload.capacity > event.total_capacity` → `409` con `"La capacidad de la sesión no puede superar la capacidad total del evento"`.
3. **Cupos:** `to_session_read(session_row, registered_count)` construye `SessionRead` con `available_capacity = max(0, capacity - registered_count)`.
4. **Hook:** `get_session_registered_count(session: DBSession, session_id: int) -> int` devuelve `0` en este dominio y es monkeypatcheable en tests (mismo patrón que `get_registered_count` de `events`).
5. **Reducción futura:** si `registered_count > 0` y `payload.capacity < registered_count` → `409` con `"No se puede reducir la capacidad de la sesión por debajo del número de inscritos actuales"`. Hoy no se dispara; se deja implementado como guarda para el Dominio 4.
6. **Evento:** no se ajustan sesiones al reducir `event.total_capacity`; `registrations` validará ambos límites al inscribir.

## 12. Autorización

### 12.1. Dependencias (`backend/app/sessions/dependencies.py`)

1. **Lecturas:** `get_optional_current_user` reutilizada de `app.events.dependencies` (misma semántica: sin cabecera → `None`; cabecera inválida → `401`).
2. **Escrituras:**
   - `require_session_editor = require_roles(UserRole.ORGANIZER, UserRole.ADMIN)`: corta con `401` sin token y `403` para `ATTENDEE`.
   - `get_owned_event_for_write(event_id: int = Path(ge=1), current_user = Depends(require_session_editor), session = Depends(get_session)) -> Event`: busca el evento; si no existe → `404 "Evento no encontrado"`; si el actor no es `ADMIN` y `event.organizer_id != current_user.id` → `403 "No tienes permisos para realizar esta acción"`.
   - `get_session_in_event(event_id: int, session_id: int, event: Event = Depends(get_owned_event_for_write), session = Depends(get_session)) -> Session`: busca la sesión por `id` y `event_id`; si no existe o no pertenece → `404 "Sesión no encontrada"`.
3. **Orden:** token (`401`) → rol (`403`) → evento (`404`) → propiedad (`403`) → sesión (`404`) → estado del evento (`409`) → reglas de negocio (`409`) → schema (`422`).

### 12.2. Visibilidad de lectura (`backend/app/sessions/service.py`)

- `get_visible_event(session, event_id, actor) -> Event`:
  - No existe → `404 "Evento no encontrado"`.
  - `PUBLISHED` → visible para todos.
  - No publicado: visible solo si `actor` es `ADMIN` o (`ORGANIZER` y `organizer_id == actor.id`); en cualquier otro caso → `404 "Evento no encontrado"`.
- El listado y el detalle llaman primero a `get_visible_event` y después filtran por `event_id`.
- En el detalle, si la sesión no existe o no pertenece → `404 "Sesión no encontrada"`.

## 13. Visibilidad

| Actor                     | Evento `PUBLISHED` | Evento `DRAFT` propio | Evento `DRAFT` ajeno | Evento `CANCELLED` propio | Evento `CANCELLED` ajeno |
| ------------------------- | :----------------: | :-------------------: | :------------------: | :-----------------------: | :----------------------: |
| Anónimo / `ATTENDEE`      |         ✓          |         `404`         |        `404`         |           `404`           |          `404`           |
| `ORGANIZER` propietario   |         ✓          |          ✓            |          —           |             ✓             |           —              |
| `ORGANIZER` ajeno         |         ✓          |         `404`         |        `404`         |           `404`           |          `404`           |
| `ADMIN`                   |         ✓          |          ✓            |          ✓           |             ✓             |           ✓              |

Las escrituras no usan esta tabla de visibilidad: usan `get_owned_event_for_write`, que devuelve `403` al `ORGANIZER` ajeno (no `404`), porque el actor ya está autenticado y el verbo revela la intención de modificar.

## 14. Ordenamiento

`ORDER BY sessions.start_time ASC, sessions.id ASC` en el listado. `id` desempata sesiones con el mismo `start_time` y hace el resultado determinista (R3.7). El detalle no ordena (una sola fila).

## 15. Paginación

No aplica: la agenda de un evento es un conjunto acotado y la UI la muestra completa en una línea de tiempo. El contrato es `SessionListRead { items, total }`, sin `page`, `size` ni `pages`. No se reutiliza `PaginationParams` ni `build_paginated_response`. Si en el futuro se pagina, será un cambio de contrato con subida de versión de la spec (R1.4, R2.4).

## 16. Contratos OpenAPI

- **Router:** `APIRouter(prefix="/api/events", tags=["sessions"])`.
- **Rutas:**
  - `GET /api/events/{event_id}/sessions` → `SessionListRead`, `responses=error_responses(401, 403, 404, 409, 422)`.
  - `POST /api/events/{event_id}/sessions` → `SessionRead`, `201`, mismos códigos.
  - `GET /api/events/{event_id}/sessions/{session_id}` → `SessionRead`, mismos códigos.
  - `PATCH /api/events/{event_id}/sessions/{session_id}` → `SessionRead`, mismos códigos.
  - `DELETE /api/events/{event_id}/sessions/{session_id}` → `204`, mismos códigos.
- **Parámetros de ruta:** `event_id` y `session_id` con `Path(ge=1)` para que un valor no entero o `< 1` caiga en `422`.
- **Schemas:** `SessionCreate`, `SessionUpdate`, `SessionRead`, `SessionListRead`; se reutilizan `ErrorResponse` y `ValidationErrorResponse` de `app/core/exceptions.py`.
- **Ejemplos:** los de `spec.md` §8; el router puede declarar `openapi_examples` para `POST` y `PATCH`, pero no es obligatorio para el criterio `SES-AC-23`.
- **`400`:** no se declara en `error_responses` porque este dominio no lo usa. La spec lo documenta como no usado.

## 17. Integración con eventos

- **Sin cambios en `EventRead`:** el detalle del evento no incluye sesiones. El frontend compone la vista con dos llamadas.
- **Caché:** cada escritura de sesión invalida `events:` (listado y detalle de eventos pueden contener `registered_count`/`available_capacity`, y la arquitectura §3.6 exige invalidar el evento afectado). No se cachea el listado de sesiones en v1.
- **Cascada:** el `DELETE /api/events/{id}` existente sigue igual; la FK `ON DELETE CASCADE` borra las sesiones.
- **Frontera de capacidad:** `events` no conoce `sessions`; `sessions` lee `event.total_capacity` y `event.date`. La reducción de `total_capacity` no toca sesiones.
- **Estado:** `sessions` lee `event.status` y bloquea escrituras en `CANCELLED`; no cambia estados del evento.
- **Propiedad:** `sessions` lee `event.organizer_id`; no lo modifica.

## 18. Integración frontend prevista

1. `EventDetailView.vue` ejecuta en paralelo `store.fetchEventById(id)` y `sessionStore.fetchSessions(id)` (`Promise.all`), con `BaseSkeleton` mientras carga y `BaseAlert` si falla cualquiera de las dos.
2. La línea de tiempo se renderiza con `SessionTimeline.vue`; el formulario se abre en un panel o modal dentro del detalle, sin nueva ruta.
3. El botón "Añadir sesión" se muestra solo si `canManage` (mismo cálculo que ya usa el detalle: `ADMIN` o `ORGANIZER` dueño) y el evento no está `CANCELLED`.
4. En `CANCELLED`, la línea de tiempo sigue visible para quien pueda leer el evento, pero los controles de escritura se ocultan o deshabilitan con un aviso en español.
5. No se usa `v-html`; los textos se interpolan con `{{ }}` (R5.9).
6. Los cupos se leen de `session.available_capacity`/`session.capacity`; el frontend no resta (R2.5).

## 19. Store y servicios futuros

### 19.1. `frontend/src/types/api.ts`

- `SessionRead` (espejo exacto de `SessionRead`).
- `SessionListResponse { items: SessionRead[]; total: number }`.
- `SessionCreatePayload` (`title`, `speaker`, `description?`, `start_time`, `end_time`, `capacity`).
- `SessionUpdatePayload` (todos opcionales, sin `event_id`).

### 19.2. `frontend/src/services/sessions.ts`

- `fetchSessionsApi(eventId: number): Promise<SessionListResponse>` → `GET /events/${eventId}/sessions`.
- `fetchSessionByIdApi(eventId, sessionId): Promise<SessionRead>`.
- `createSessionApi(eventId, payload): Promise<SessionRead>`.
- `updateSessionApi(eventId, sessionId, payload): Promise<SessionRead>`.
- `deleteSessionApi(eventId, sessionId): Promise<void>`.
- Usa `apiClient` (`baseURL: '/api'`) y no construye rutas absolutas (R2.1).

### 19.3. `frontend/src/stores/sessions.ts` (`useSessionStore`)

- **Estado:** `items: ref<SessionRead[]>([])`, `total: ref(0)`, `currentSession: ref<SessionRead | null>(null)`, `isLoading: ref(false)`, `isSubmitting: ref(false)`, `errorMessage: ref('')`, `fieldErrors: ref<ValidationFieldError[]>([])`.
- **Acciones:** `fetchSessions(eventId)`, `fetchSessionById(eventId, sessionId)`, `createSession(eventId, payload)`, `updateSession(eventId, sessionId, payload)`, `deleteSession(eventId, sessionId)`, `clearErrors()`, `reset()`.
- **Errores:** extrae `detail` y `errors[]` del `AxiosError` y los expone en español; el interceptor global sigue gestionando `401`/`403` (R5.6).
- **Sin cálculos de cupos:** el store guarda `available_capacity` tal como llega.

## 20. Componentes y vistas futuras

1. **`frontend/src/components/sessions/SessionTimeline.vue`:**
   - `defineProps<{ sessions: SessionRead[] }>()`.
   - Lista ordenada (la API ya la envía ordenada) con hora de inicio/fin formateada en español y `timeZone: 'UTC'`, título, ponente, descripción opcional y `available_capacity`/`capacity` de la API.
   - Estado vacío: "Este evento todavía no tiene sesiones programadas.".
   - Tailwind, sin librerías de calendario (R4.3), sin `v-html`.
2. **`frontend/src/components/sessions/SessionForm.vue`:**
   - Props: `eventId: number`, `session?: SessionRead | null`, `disabled?: boolean`.
   - Campos: `title` (`BaseInput`), `speaker` (`BaseInput`), `description` (`textarea`), `start_time` y `end_time` (`input type="datetime-local"`), `capacity` (`input type="number" min="1"`).
   - Emite `submit` con `SessionCreatePayload`/`SessionUpdatePayload`; no llama directamente a la API para poder testearlo aislado.
   - Convierte los valores `datetime-local` a UTC con `new Date(value).toISOString()` antes de emitir; al editar, convierte el ISO UTC a un valor local para el input.
   - Muestra `errors[]` por campo y `detail` de `409` con `BaseAlert`.
   - `BaseButton` deshabilitado mientras `isSubmitting`.
3. **`EventDetailView.vue`:**
   - Añade el bloque de agenda con `SessionTimeline`.
   - Carga `SessionForm.vue` con `defineAsyncComponent(() => import('@/components/sessions/SessionForm.vue'))` y `BaseSpinner` como `loadingComponent` (bonus de lazy loading).
   - `canManage` existente controla la visibilidad del botón y del formulario; `isCancelled` oculta/deshabilita la escritura.
   - Tras crear/editar/eliminar, refresca `fetchSessions(id)` y muestra feedback en español.
4. **Rutas:** no se añaden rutas nuevas. La agenda vive en `/events/:id`.

## 21. Manejo de errores

- **401:** el interceptor global limpia la sesión y redirige a login (R5.6). El store no duplica la redirección.
- **403:** el interceptor mantiene la sesión y muestra un aviso; la UI ya oculta controles, pero el backend sigue siendo la autoridad (R2.5).
- **404:** "Evento no encontrado" o "Sesión no encontrada" según corresponda; el detalle muestra un estado vacío/aviso sin revelar existencia de borradores.
- **409:** se muestra `detail` en español (solapamiento, ventana, capacidad, evento cancelado, inscritos).
- **422:** se mapean `errors[].field` a los campos del formulario y se muestra `errors[].message`; si no hay campo reconocible, se muestra `detail`.
- **500/503:** mensaje genérico en español; no se exponen trazas (R5.8).

## 22. Plan TDD contra PostgreSQL

- **Archivo:** `backend/tests/test_sessions.py`.
- **Base:** PostgreSQL real `mis_eventos_test` con migración `0004_create_sessions` aplicada por el fixture `test_engine` (R3.6). Nunca SQLite.
- **Helpers:** crear usuarios (`ADMIN`, `ORGANIZER`, `ATTENDEE`), eventos en cada estado y sesiones; tokens con `create_access_token`; `FakeCache` para espiar invalidaciones.
- **Casos por criterio:**
  - `SES-AC-01`: alta válida con defaults y campos calculados.
  - `SES-AC-02`: longitudes, `description` vacía, `extra="forbid"` (`event_id` en body).
  - `SES-AC-03`: `capacity` 1, 100000, 0, 100001 y `> event.total_capacity`.
  - `SES-AC-04`: `start == end` y `start > end`.
  - `SES-AC-05`: naive en ambos campos; offset `-05:00` normalizado a `Z`.
  - `SES-AC-06`: antes de `event.date`, fin después de medianoche, fin exactamente en medianoche.
  - `SES-AC-07`: fecha pasada dentro de la ventana.
  - `SES-AC-08`: solapamiento total, parcial, consecutivo y eventos distintos.
  - `SES-AC-09`: `PATCH` solo `start_time`/solo `end_time`, exclusión de la propia sesión.
  - `SES-AC-10`: concurrencia con dos conexiones independientes (ver fixture abajo).
  - `SES-AC-11`: orden y `{items,total}`, evento sin sesiones.
  - `SES-AC-12`: detalle correcto, sesión de otro evento, evento inexistente.
  - `SES-AC-13`/`14`/`15`: visibilidad por rol y estado.
  - `SES-AC-16`: 401/403 en las tres escrituras.
  - `SES-AC-17`: escrituras en `DRAFT` y `PUBLISHED`.
  - `SES-AC-18`: 409 en `CANCELLED` para las tres escrituras.
  - `SES-AC-19`: `DELETE` `204`; monkeypatch de `get_session_registered_count` → `409`.
  - `SES-AC-20`: borrar evento con sesiones mediante `DELETE /api/events/{id}` y verificar cero filas en `sessions`.
  - `SES-AC-21`: `updated_at` cambia en `PATCH`; `event_id` en body `422`.
  - `SES-AC-22`: `PATCH {}`, mensajes exactos, `400` no usado.
  - `SES-AC-23`: `/api/openapi.json` con rutas, tag, schemas y códigos.
  - `SES-AC-24`: `FakeCache` registra `invalidate_prefix("events:")`; con `RedisError` la escritura sigue en `200/201/204`.
  - `SES-AC-25`: inspección de columnas, FK, checks e índices con `sqlalchemy.inspect`.
  - `SES-AC-26`, `SES-AC-27` y `SES-AC-28` son de frontend: se cubren con Vitest en `tasks.md` (`F1..F7`) y se cierran en `V4..V6`.
  - `SES-AC-29`: `PATCH` y `DELETE` con sesión de otro evento, con sesión inexistente y con evento inexistente; `404 "Sesión no encontrada"` / `404 "Evento no encontrado"` y ninguna fila modificada ni eliminada.
  - `SES-AC-30`: dos conexiones independientes donde un `DELETE` compite con un `POST`/`PATCH` del mismo evento; se reutiliza el fixture `concurrent_sessions` y se repite 3 veces para verificar que el resultado final es consistente (una sola fila nueva o un `409`).
- **Fixture de concurrencia:**
  - No usar `db_session`: usa una única conexión con `SAVEPOINT` y no permite dos transacciones independientes.
  - Definir `concurrent_sessions` que abre dos `Session` sobre dos `Connection` distintas del `test_engine`, con `autocommit=False`.
  - Sembrar usuarios/evento con una tercera conexión y `commit`.
  - Ejecutar las dos altas en hilos (`ThreadPoolExecutor`) con una `Barrier` para que compitan; una debe completar y la otra recibir `HTTPException(409)`.
  - Verificar con una conexión nueva que `SELECT count(*) FROM sessions` es `1`.
  - Limpiar con `db_truncate` al finalizar.
- **Monkeypatch:** `monkeypatch.setattr("app.sessions.service.get_session_registered_count", lambda session, session_id: 3)` para el borrado y la reducción futura.
- **Cobertura:** `uv run pytest --cov=app --cov-report=xml --cov-report=term-missing`; el dominio debe cubrir modelos, schemas, dependencias, servicio y router.

## 23. Riesgos y mitigaciones

| Riesgo                                                         | Mitigación                                                                                                                                          |
| -------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| Carrera entre dos altas solapadas                              | `SELECT ... FOR UPDATE` sobre `events` + prueba concurrente con dos conexiones y `Barrier` (R3.6, R5.4).                                            |
| Fechas `naive` aceptadas por accidente                         | Tipo `AwareUTCDateTime` específico del dominio, sin reutilizar `UTCDateTime`; test explícito de rechazo.                                            |
| Ventana demasiado restrictiva (impide mañanas)                 | Se documenta en `spec.md` §9.1; se respeta `EVT-BR-05` y se deja la enmienda de `events` fuera de alcance.                                          |
| Colisión de nombres `Session` (modelo) vs `sqlmodel.Session`   | Importar `Session as DBSession` en servicios y dependencias; nombres de test claros.                                                               |
| Caché obsoleta de eventos tras escrituras de sesión            | Invalidar `events:` después del `commit`, incluso si no hay caché de sesiones; capturar `RedisError` y degradar (R4.4).                            |
| `datetime-local` envía hora local sin zona                     | Convertir con `new Date(value).toISOString()` antes de enviar; al editar, convertir el ISO UTC a local para el input.                              |
| Capacidad de sesión desincronizada con la del evento           | `sessions` valida al crear/editar; `registrations` revalidará ambos cupos; no se ajustan sesiones retroactivamente.                               |
| Orden de migraciones roto                                      | `down_revision = "0003_create_events"`; test de `alembic head` y de columnas; importar el modelo en `env.py`.                                       |
| Aislamiento de tests contaminado                               | `db_truncate` incluye `sessions` al estar en `SQLModel.metadata`; el test concurrente limpia con `TRUNCATE ... CASCADE`.                            |
| `GET` declara `403/409` que no usa                              | Se declaran por contrato común de `error_responses`; la spec explica que no se usan en lectura.                                                     |
| Mensajes de error inconsistentes                               | Constantes de mensajes en español en el servicio y tests que comparan `detail` exacto.                                                              |
| Enumeración de borradores                                      | `get_visible_event` devuelve `404` para eventos no visibles; el detalle de sesión también `404`.                                                    |

## 24. Dependencias, aprobación y librerías de soporte

### 24.1. Dependencias

- `platform` v1.0: formato de error, fechas UTC, Redis, OpenAPI, Docker.
- `auth` v1.0: JWT, RBAC, usuarios.
- `events` v1.0: `Event`, `EventStatus`, `event.date`, `event.total_capacity`, `event.organizer_id`, `get_optional_current_user`, invalidación `events:`.
- `registrations` (futuro): consumirá el hook y el bloqueo del evento.

### 24.2. Decisiones que requieren aprobación

- La spec completa (`spec.md`, `plan.md`, `tasks.md`) requiere la aprobación explícita del usuario antes de implementar (R1.8). No se inicia ninguna tarea `B*`, `F*` o `V*` hasta entonces.

### 24.3. Librerías de soporte (R4.2)

- **No se añaden librerías nuevas.** SQLAlchemy/SQLModel, PostgreSQL, Redis y las utilidades de test ya están en el stack y registradas en `MEMORY.md`.
- `btree_gist` se menciona únicamente como alternativa descartada; **no se instala ni se usa**.
- No se usan librerías de calendario en el frontend (R4.3); la línea de tiempo se construye con Tailwind y utilidades nativas de `Date`.
