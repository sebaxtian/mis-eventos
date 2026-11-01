# Spec: Programación de Sesiones (`sessions`)

| Campo                      | Valor                                                                                                  |
| -------------------------- | ------------------------------------------------------------------------------------------------------ |
| **ID del dominio**         | `SES`                                                                                                  |
| **Versión**                | 0.2                                                                                                    |
| **Estado**                 | Implementada                                                                                           |
| **Fecha**                  | 2026-10-31                                                                                             |
| **Dependencias**           | `platform` (Dominio 0, v1.0), `auth` (Dominio 1, v1.0), `events` (Dominio 2, v1.0)                      |
| **Decisiones bloqueantes** | Ninguna; 8 decisiones resueltas con el usuario (D1–D8). Aprobada por el usuario el 2026-10-31; enmienda v0.2 (`SES-AC-29`/`SES-AC-30`) aprobada por el usuario el 2026-11-01. |

> Esta spec describe **qué** hace el sistema en el dominio `sessions`, no cómo se implementa. Los detalles técnicos van en `plan.md`. Estado según R1.8 de `docs/constitution.md`: solo el usuario la marca como _Aprobada_. Una spec con decisiones bloqueantes abiertas no puede aprobarse.

## 1. Objetivo

Permitir que el organizador propietario de un evento (o un administrador) construya y mantenga la agenda del evento mediante sesiones con título, ponente, horario y capacidad propia, garantizando que los horarios sean válidos en UTC, que no se solapen dentro del mismo evento y que la capacidad de cada sesión no exceda la del evento. El dominio expone una línea de tiempo de solo lectura para el público y para los asistentes en eventos publicados, y reserva la escritura al propietario o al `ADMIN`, preparando la frontera transaccional que `registrations` necesitará para inscribir asistentes a sesiones.

## 2. Alcance

### 2.1. Incluye

- Modelo `Session` vinculado uno a muchos a `Event`, con `title`, `speaker`, `description` opcional, `start_time`, `end_time`, `capacity`, `created_at` y `updated_at`.
- Listado completo de las sesiones de un evento (`GET /api/events/{event_id}/sessions`) con autenticación Bearer opcional, orden determinista `start_time ASC, id ASC` y sobre `{ items, total }`, sin paginación.
- Consulta de detalle anidada (`GET /api/events/{event_id}/sessions/{session_id}`) con verificación de pertenencia al evento.
- Creación (`POST`), edición parcial (`PATCH`) y eliminación física (`DELETE`) de sesiones por el `ORGANIZER` propietario del evento o un `ADMIN`.
- Validación de `start_time < end_time` estricto y de que ambas fechas incluyan zona horaria explícita, con normalización y serialización en UTC (`Z`).
- Validación de la ventana temporal del evento: la sesión debe comenzar en o después de `event.date` y terminar antes o en la medianoche UTC siguiente a la fecha UTC de `event.date`; no puede cruzar medianoche.
- Validación de no solapamiento entre sesiones del mismo evento con intervalos semiabiertos `[start_time, end_time)`, probada contra PostgreSQL real en condiciones de concurrencia.
- Serialización de escrituras por evento mediante bloqueo de fila (`SELECT ... FOR UPDATE`) sobre `events` durante la comprobación de solapamiento y la escritura.
- Capacidad propia de la sesión (`1..100000`) limitada por `event.total_capacity`, con exposición de `registered_count` y `available_capacity` calculados por el backend.
- Bloqueo de escrituras cuando el evento está en `CANCELLED`; escrituras permitidas en `DRAFT` y `PUBLISHED`.
- Invalidación del prefijo de caché `events:` en cada escritura de sesión, sin cachear el listado de sesiones en esta versión.
- Frontend Vue 3: tipos y servicio de sesiones, `useSessionStore`, `SessionTimeline.vue` en el detalle del evento, `SessionForm.vue` cargado de forma diferida, permisos de UI y mensajes de error en español.

### 2.2. No incluye

- Inscripción de asistentes a eventos o sesiones, cupos reales de sesión, anulación de inscripciones y "Mis inscripciones" (Dominio 4: `specs/registrations/`).
- Tabla `Speaker` o gestión de ponentes como entidad propia: el ponente es un campo de texto (`speaker`) en la sesión.
- Estados propios de sesión (cancelada, llena, en curso): el estado relevante es el del evento.
- Auditoría de usuario creador o editor de la sesión (`created_by`, `updated_by`).
- Sesiones que crucen medianoche o que empiecen antes de la hora de `event.date`; habilitarlo exige enmendar `EVT-BR-05` en `specs/events/spec.md`.
- Paginación, búsqueda o filtros del listado de sesiones.
- Caché Redis del listado o del detalle de sesiones en esta versión.
- Restricción de exclusión PostgreSQL (`EXCLUDE USING GIST` con `btree_gist`); se documenta como alternativa descartada.
- Edición del contrato de `events` (`EventRead` no incorpora sesiones) ni cambios en `backend/app/events/`.
- Reprogramación masiva, plantillas de agenda, series recurrentes o zonas horarias por sesión distintas de UTC en la API.

## 3. Dependencias

- **`platform` (v1.0):** formato de error `{"detail": "..."}` con `errors: [{"field", "message"}]` en `422`, cliente Redis prescindible, convención de fechas UTC, sufijo `Z` en JSON, `error_responses` para OpenAPI, Docker Compose y gateway Nginx.
- **`auth` (v1.0):** `User`, `UserRole` (`ADMIN`, `ORGANIZER`, `ATTENDEE`), `bearer_scheme`, `get_current_user`, `require_roles`, semántica estricta 401 ≠ 403 (R5.6).
- **`events` (v1.0):** tabla y modelo `Event`, `EventStatus` (`DRAFT`, `PUBLISHED`, `CANCELLED`), `event.organizer_id`, `event.date`, `event.total_capacity`, dependencia `get_optional_current_user`, índice y patrón de invalidación `events:`.
- **`registrations` (futuro):** consumirá `get_session_registered_count` y la fila del evento bloqueada; no se implementa aquí.

## 4. Roles involucrados

| Rol         | Qué puede hacer en este dominio                                                                                                                                                                                                                                                                                       |
| ----------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Anónimo     | Listar y ver el detalle de las sesiones de eventos `PUBLISHED`. Recibe `404 "Evento no encontrado"` en eventos `DRAFT` o `CANCELLED`. No puede escribir (`401`).                                                                                                                                                    |
| `ATTENDEE`  | Igual que Anónimo: lectura de sesiones de eventos `PUBLISHED` y `404` en eventos no publicados. No puede crear, editar ni eliminar sesiones (`403`).                                                                                                                                                                 |
| `ORGANIZER` | Lectura de las sesiones de todos los eventos `PUBLISHED` más las de sus propios eventos en cualquier estado (`DRAFT`, `PUBLISHED`, `CANCELLED`). Escritura (crear, editar, eliminar) **solo** en sesiones de eventos cuyo `organizer_id` es el suyo; `403` en eventos ajenos y `404` al leer por ID un evento ajeno no publicado. |
| `ADMIN`     | Lectura de las sesiones de cualquier evento en cualquier estado y escritura (crear, editar, eliminar) sobre cualquier evento, respetando las reglas de ventana, solapamiento, capacidad y estado `CANCELLED`.                                                                                                        |

## 5. Modelo conceptual observable

### 5.1. Entidad `Session`

| Campo         | Tipo                       | Obligatorio | Reglas                                                                                                                 |
| ------------- | -------------------------- | :---------: | ---------------------------------------------------------------------------------------------------------------------- |
| `id`          | entero                     |      —      | Clave primaria autoincremental, solo lectura.                                                                          |
| `event_id`    | entero                     |     Sí      | FK a `events.id`, inmutable. Se toma de la ruta, **nunca** del cuerpo.                                                 |
| `title`       | texto                      |     Sí      | `trim`, entre 3 y 160 caracteres.                                                                                      |
| `speaker`     | texto                      |     Sí      | `trim`, entre 2 y 120 caracteres. Texto libre; no existe tabla de ponentes.                                            |
| `description` | texto o `null`             |     No      | `trim`, máximo 2000 caracteres; una cadena vacía o solo espacios se normaliza a `null`.                                |
| `start_time`  | fecha y hora con zona      |     Sí      | ISO 8601 con offset o `Z`; se normaliza y almacena en UTC.                                                             |
| `end_time`    | fecha y hora con zona      |     Sí      | ISO 8601 con offset o `Z`; se normaliza y almacena en UTC. Debe ser estrictamente posterior a `start_time`.            |
| `capacity`    | entero                     |     Sí      | `1 <= capacity <= 100000` y `capacity <= event.total_capacity`.                                                        |
| `created_at`  | fecha y hora UTC           |      —      | Solo lectura, asignada al crear.                                                                                       |
| `updated_at`  | fecha y hora UTC           |      —      | Solo lectura, se actualiza en cada `PATCH` (aunque el valor enviado sea igual).                                        |

No existe campo `status`, ni `created_by`, ni `updated_by`, ni campos de auditoría de usuario.

### 5.2. `SessionRead`

Toda respuesta que devuelve una sesión (`POST`, `GET` detalle, `PATCH` e `items[]` del listado) usa `SessionRead`:

| Campo                | Tipo             | Reglas                                                                                                        |
| -------------------- | ---------------- | ------------------------------------------------------------------------------------------------------------- |
| `id`                 | entero           | Identificador de la sesión.                                                                                    |
| `event_id`           | entero           | Evento al que pertenece.                                                                                       |
| `title`              | texto            | Recortado, 3–160.                                                                                              |
| `description`        | texto o `null`   | Recortado, máximo 2000; `null` si quedó vacío.                                                                 |
| `speaker`            | texto            | Recortado, 2–120.                                                                                              |
| `start_time`         | fecha y hora UTC | ISO 8601 terminado en `Z`.                                                                                     |
| `end_time`           | fecha y hora UTC | ISO 8601 terminado en `Z`.                                                                                     |
| `capacity`           | entero           | Capacidad propia de la sesión.                                                                                 |
| `registered_count`   | entero           | Calculado por el backend. En este dominio vale `0` (hook `get_session_registered_count`).                       |
| `available_capacity` | entero           | Calculado por el backend como `max(0, capacity - registered_count)` (R2.5).                                     |
| `created_at`         | fecha y hora UTC | ISO 8601 `Z`, solo lectura.                                                                                    |
| `updated_at`         | fecha y hora UTC | ISO 8601 `Z`, solo lectura, actualizado en cada `PATCH`.                                                       |

### 5.3. `SessionListRead`

| Campo   | Tipo             | Reglas                                                 |
| ------- | ---------------- | ------------------------------------------------------ |
| `items` | `SessionRead[]`  | Sesiones ordenadas por `start_time ASC, id ASC`.       |
| `total` | entero           | Número total de sesiones del evento visible para el actor. |

No incluye `page`, `size` ni `pages`: el listado no se pagina en esta versión.

### 5.4. `SessionCreate` y `SessionUpdate`

- **`SessionCreate`:** `title`, `speaker`, `description` (opcional), `start_time`, `end_time`, `capacity`. `extra="forbid"`; `event_id`, `id`, `registered_count`, `available_capacity`, `created_at` y `updated_at` están prohibidos en el cuerpo (`422` con `"Este campo no está permitido"`).
- **`SessionUpdate`:** todos los campos opcionales (`title`, `speaker`, `description`, `start_time`, `end_time`, `capacity`); `extra="forbid"`. Un cuerpo `{}` o sin campos actualizables responde `422` con `errors[].message = "Debes indicar al menos un campo para actualizar"`. `description: null` es válido y borra la descripción; cualquier otro campo enviado como `null` responde `422`. Enviar solo `start_time` o solo `end_time` se combina con el valor actual para validar el par final.

## 6. Reglas de negocio

- **SES-BR-01 (Modelo y validaciones de campos):** Cada sesión pertenece a un evento y exige `title` (`trim`, 3–160), `speaker` (`trim`, 2–120), `description` opcional (`trim`, máximo 2000; vacío se normaliza a `null`) y `capacity` entera entre `1` y `100000`; los cuerpos de entrada aplican `extra="forbid"`, `id`/`event_id`/campos calculados están prohibidos, y `created_at`/`updated_at` son de solo lectura (R5.5, R6).
- **SES-BR-02 (Relación uno a muchos y cascada):** Un `Event` tiene muchas `Session`; cada `Session` pertenece exactamente a un `Event` mediante `event_id` obligatorio e inmutable, con FK `ON DELETE CASCADE`. `event_id` solo se toma de la ruta; el evento debe existir. El borrado físico de un evento sin inscritos elimina sus sesiones en cascada sin cambios en el contrato de `events`.
- **SES-BR-03 (Permisos de escritura y propiedad):** Solo el `ORGANIZER` propietario del evento (`event.organizer_id == current_user.id`) o un `ADMIN` pueden crear, editar o eliminar sesiones. Sin token válido la respuesta es `401` con `"No autenticado o sesión expirada"` y `WWW-Authenticate: Bearer`; un `ATTENDEE` o un `ORGANIZER` ajeno recibe `403` con `"No tienes permisos para realizar esta acción"` (R5.2, R5.3, R5.6).
- **SES-BR-04 (Visibilidad de lectura):** Las lecturas aceptan Bearer opcional. Anónimo y `ATTENDEE` solo ven sesiones de eventos `PUBLISHED`; el `ORGANIZER` ve las de eventos `PUBLISHED` y las de sus propios eventos en cualquier estado; el `ADMIN` ve todas. Si el evento no existe o no es visible para el actor, la respuesta es `404 "Evento no encontrado"`; si el evento es visible pero la sesión no existe o no le pertenece, `404 "Sesión no encontrada"` (R5.3, R5.8).
- **SES-BR-05 (Fechas UTC estrictas, orden y marcas de tiempo):** `start_time` y `end_time` deben incluir zona horaria explícita (offset o `Z`); una fecha `naive` se rechaza con `422` y `errors[].message = "La fecha y hora debe incluir zona horaria (por ejemplo, Z)"`. Las fechas se normalizan, almacenan y serializan en UTC (`TIMESTAMP WITH TIME ZONE`, ISO 8601 terminado en `Z`). El listado se ordena por `start_time ASC, id ASC`. Las fechas pasadas se permiten para mantener pruebas deterministas (R3.7); no se comparan con el reloj del sistema.
- **SES-BR-06 (Ventana del evento y medianoche):** Sea `event_date` el instante UTC de `event.date`. Toda sesión debe cumplir `event_date <= start_time` y `end_time <= date_trunc('day', event_date) + 1 day` (medianoche UTC siguiente a la fecha UTC del evento). En consecuencia, la sesión debe celebrarse en la misma fecha UTC del evento y no puede cruzar medianoche. El incumplimiento responde `409` con `"La sesión debe estar dentro de la fecha UTC del evento y no puede cruzar la medianoche"`.
- **SES-BR-07 (No solapamiento):** Los intervalos son semiabiertos `[start_time, end_time)`. Dos sesiones del mismo evento se solapan si `existing.start_time < new.end_time AND existing.end_time > new.start_time`. Sesiones consecutivas (una termina cuando la otra empieza) son válidas; eventos distintos pueden tener sesiones simultáneas. En `PATCH` se excluye la propia sesión. Un solapamiento responde `409` con `"La sesión se solapa con otra sesión del evento"`.
- **SES-BR-08 (Concurrencia y transacción):** Cada escritura de sesión abre una transacción, bloquea la fila del evento con `SELECT ... FOR UPDATE` y solo entonces comprueba solapamiento y escribe, de modo que las escrituras del mismo evento se serializan. El bloqueo también aplica a `DELETE` para serializar con altas y ediciones. La regla se prueba contra PostgreSQL real con dos conexiones independientes (R3.6, R5.4).
- **SES-BR-09 (Capacidad y cupos):** `capacity` es propia de la sesión, obligatoria, entera entre `1` y `100000`, y no puede superar `event.total_capacity` (`409` con `"La capacidad de la sesión no puede superar la capacidad total del evento"`). `SessionRead` expone `capacity`, `registered_count` y `available_capacity = max(0, capacity - registered_count)` calculados por el backend (R2.5). Mientras no exista `registrations`, `registered_count` es `0`; una reducción futura por debajo de los inscritos responderá `409` con `"No se puede reducir la capacidad de la sesión por debajo del número de inscritos actuales"`. Si el evento reduce su `total_capacity`, las sesiones no se ajustan retroactivamente; `registrations` deberá validar ambos límites al inscribir.
- **SES-BR-10 (Estados del evento):** En eventos `DRAFT` y `PUBLISHED` se pueden crear, editar y eliminar sesiones. En `CANCELLED` la agenda es de solo lectura y cualquier escritura (`POST`, `PATCH`, `DELETE`) responde `409` con `"Un evento cancelado no permite modificar sus sesiones"`. La comprobación de propiedad (`403`) precede a la comprobación de estado (`409`).
- **SES-BR-11 (Listado, detalle y borrado):** `GET /api/events/{event_id}/sessions` devuelve `SessionListRead { items, total }` sin paginación y ordenado por `start_time ASC, id ASC`; `GET /api/events/{event_id}/sessions/{session_id}` devuelve el detalle solo si la sesión pertenece al evento de la ruta; `DELETE` borra físicamente la fila y responde `204 No Content`; si existen asistentes inscritos en la sesión (hook de dominio) responde `409` con `"No se puede eliminar una sesión con asistentes inscritos"`.
- **SES-BR-12 (Errores, OpenAPI, caché y contrato frontend):** Todos los errores usan el formato de `platform` con `detail` en español y, en `422`, `detail = "Error de validación en los datos enviados"` más `errors[].message` en español. El código `400` no se usa en este dominio. Las cinco operaciones se documentan con tag `sessions` y `error_responses(401, 403, 404, 409, 422)`. El listado de sesiones no se cachea; toda escritura invalida el prefijo `events:` y tolera que Redis no esté disponible (R4.4). El frontend consume `available_capacity` de la API y nunca lo recalcula (R2.5).

## 7. Matriz de permisos (acciones × roles)

| Acción                                                        | Anónimo | `ATTENDEE` | `ORGANIZER` (evento propio) | `ORGANIZER` (evento ajeno) | `ADMIN` |
| ------------------------------------------------------------- | :-----: | :--------: | :-------------------------: | :------------------------: | :-----: |
| `GET /api/events/{event_id}/sessions` (evento `PUBLISHED`)     |    ✓    |     ✓      |              ✓              |             ✓              |    ✓    |
| `GET /api/events/{event_id}/sessions` (evento `DRAFT`)         |  `404`  |   `404`    |              ✓              |            `404`           |    ✓    |
| `GET /api/events/{event_id}/sessions` (evento `CANCELLED`)     |  `404`  |   `404`    |              ✓              |            `404`           |    ✓    |
| `GET /api/events/{event_id}/sessions/{session_id}` (`PUBLISHED`) |    ✓    |     ✓      |              ✓              |             ✓              |    ✓    |
| `GET /api/events/{event_id}/sessions/{session_id}` (`DRAFT`/`CANCELLED`) |  `404`  |   `404`    |              ✓              |            `404`           |    ✓    |
| `POST /api/events/{event_id}/sessions`                        |  `401`  |   `403`    |              ✓              |            `403`           |    ✓    |
| `PATCH /api/events/{event_id}/sessions/{session_id}`           |  `401`  |   `403`    |              ✓              |            `403`           |    ✓    |
| `DELETE /api/events/{event_id}/sessions/{session_id}`          |  `401`  |   `403`    |              ✓              |            `403`           |    ✓    |

Notas:

- Un token presente pero inválido, expirado o de usuario inactivo en cualquier operación (incluidas las lecturas con Bearer opcional) responde `401`.
- Las escrituras sobre eventos `CANCELLED` devuelven `409` incluso al propietario o al `ADMIN`; la comprobación de propiedad ocurre antes: un `ORGANIZER` ajeno recibe `403`, no `409`.
- El `ADMIN` no puede saltarse las reglas de ventana, solapamiento, capacidad ni estado cancelado.

## 8. Contrato de API

Todas las rutas cuelgan de `/api/events/{event_id}/sessions`. Los errores siguen el formato de `specs/platform/spec.md`. Todas las fechas se serializan en UTC ISO 8601 con sufijo `Z`. Los ejemplos usan un evento con `date = "2026-11-15T14:00:00Z"`.

### 8.1. `GET /api/events/{event_id}/sessions`

- **Descripción:** Lista todas las sesiones de un evento visible para el actor, ordenadas por `start_time ASC, id ASC`.
- **Autenticación / rol requerido:** Público con Bearer opcional (Anónimo, `ATTENDEE`, `ORGANIZER`, `ADMIN`).
- **Parámetros de ruta:** `event_id` entero `>= 1`.
- **Parámetros de consulta:** Ninguno. `page`/`size` no aplican y no se documentan.
- **Paginación:** No aplica. El listado es completo y se devuelve en `SessionListRead`.
- **Response `200 OK`:**

```json
{
  "items": [
    {
      "id": 10,
      "event_id": 5,
      "title": "Apertura y bienvenida",
      "description": "Presentación del programa del día.",
      "speaker": "Ana Torres",
      "start_time": "2026-11-15T14:00:00Z",
      "end_time": "2026-11-15T15:00:00Z",
      "capacity": 80,
      "registered_count": 0,
      "available_capacity": 80,
      "created_at": "2026-10-31T18:00:00Z",
      "updated_at": "2026-10-31T18:00:00Z"
    },
    {
      "id": 11,
      "event_id": 5,
      "title": "Taller de FastAPI",
      "description": null,
      "speaker": "Luis Gómez",
      "start_time": "2026-11-15T15:00:00Z",
      "end_time": "2026-11-15T16:30:00Z",
      "capacity": 40,
      "registered_count": 0,
      "available_capacity": 40,
      "created_at": "2026-10-31T18:05:00Z",
      "updated_at": "2026-10-31T18:05:00Z"
    }
  ],
  "total": 2
}
```

- **Errores:**

| Código | Cuándo                                                                                     | `detail` (español)                                |
| ------ | ------------------------------------------------------------------------------------------ | ------------------------------------------------- |
| 400    | No se usa en este dominio                                                                  | —                                                 |
| 401    | Se envía un Bearer inválido, expirado o de usuario inactivo                                | `"No autenticado o sesión expirada"`              |
| 403    | No se usa en lectura (reservado al contrato OpenAPI)                                       | `"No tienes permisos para realizar esta acción"`  |
| 404    | El evento no existe o no es visible para el actor                                          | `"Evento no encontrado"`                          |
| 409    | No se usa en lectura (reservado al contrato OpenAPI)                                       | —                                                 |
| 422    | `event_id` no es un entero válido o es menor que 1                                         | `"Error de validación en los datos enviados"` + `errors[].message` |

### 8.2. `POST /api/events/{event_id}/sessions`

- **Descripción:** Crea una sesión dentro de la ventana del evento, validando solapamiento y capacidad.
- **Autenticación / rol requerido:** `ORGANIZER` propietario del evento o `ADMIN`.
- **Parámetros de ruta:** `event_id` entero `>= 1`.
- **Request:**

```json
{
  "title": "Apertura y bienvenida",
  "speaker": "Ana Torres",
  "description": "Presentación del programa del día.",
  "start_time": "2026-11-15T14:00:00Z",
  "end_time": "2026-11-15T15:00:00Z",
  "capacity": 80
}
```

- **Response `201 Created`:** `SessionRead` con `event_id` tomado de la ruta, `registered_count = 0`, `available_capacity = capacity` y `created_at`/`updated_at` en UTC.
- **Errores:**

| Código | Cuándo                                                                                                                       | `detail` (español)                                                                                 | `errors[].message` (español)                                     |
| ------ | ---------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| 400    | No se usa                                                                                                                    | —                                                                                                  | —                                                                |
| 401    | Token ausente, inválido, expirado o usuario inactivo                                                                         | `"No autenticado o sesión expirada"`                                                               | —                                                                |
| 403    | Rol `ATTENDEE` u `ORGANIZER` ajeno                                                                                           | `"No tienes permisos para realizar esta acción"`                                                   | —                                                                |
| 404    | El evento no existe                                                                                                          | `"Evento no encontrado"`                                                                           | —                                                                |
| 409    | El evento está en `CANCELLED`                                                                                                | `"Un evento cancelado no permite modificar sus sesiones"`                                          | —                                                                |
| 409    | La sesión se solapa con otra del mismo evento                                                                                | `"La sesión se solapa con otra sesión del evento"`                                                 | —                                                                |
| 409    | La sesión queda fuera de la fecha UTC del evento o cruza medianoche                                                          | `"La sesión debe estar dentro de la fecha UTC del evento y no puede cruzar la medianoche"`         | —                                                                |
| 409    | `capacity > event.total_capacity`                                                                                            | `"La capacidad de la sesión no puede superar la capacidad total del evento"`                       | —                                                                |
| 422    | `title` fuera de 3–160 tras `trim`; `speaker` fuera de 2–120; `description` > 2000; `capacity` fuera de 1..100000             | `"Error de validación en los datos enviados"`                                                      | Mensaje de validación correspondiente                            |
| 422    | `start_time >= end_time`                                                                                                     | `"Error de validación en los datos enviados"`                                                      | `"La hora de inicio debe ser anterior a la hora de fin"`         |
| 422    | `start_time` o `end_time` sin zona horaria                                                                                   | `"Error de validación en los datos enviados"`                                                      | `"La fecha y hora debe incluir zona horaria (por ejemplo, Z)"`   |
| 422    | Campo extra (`event_id`, `id`, `registered_count`, `available_capacity`, `created_at`, `updated_at`)                          | `"Error de validación en los datos enviados"`                                                      | `"Este campo no está permitido"`                                 |

### 8.3. `GET /api/events/{event_id}/sessions/{session_id}`

- **Descripción:** Devuelve el detalle de una sesión que pertenece al evento indicado.
- **Autenticación / rol requerido:** Público con Bearer opcional.
- **Parámetros de ruta:** `event_id` y `session_id` enteros `>= 1`.
- **Response `200 OK`:** `SessionRead`.
- **Errores:**

| Código | Cuándo                                                                 | `detail` (español)                   |
| ------ | ---------------------------------------------------------------------- | ------------------------------------ |
| 400    | No se usa                                                              | —                                    |
| 401    | Bearer inválido, expirado o de usuario inactivo                        | `"No autenticado o sesión expirada"` |
| 403    | No se usa en lectura                                                   | —                                    |
| 404    | El evento no existe o no es visible para el actor                      | `"Evento no encontrado"`             |
| 404    | El evento es visible pero la sesión no existe o no pertenece al evento | `"Sesión no encontrada"`             |
| 409    | No se usa en lectura                                                   | —                                    |
| 422    | `event_id` o `session_id` no son enteros válidos                       | `"Error de validación en los datos enviados"` + `errors[].message` |

### 8.4. `PATCH /api/events/{event_id}/sessions/{session_id}`

- **Descripción:** Actualiza parcialmente una sesión y `updated_at`, recalculando la ventana y el solapamiento sobre el par final de horarios.
- **Autenticación / rol requerido:** `ORGANIZER` propietario del evento o `ADMIN`.
- **Request:** Al menos uno de `title`, `speaker`, `description`, `start_time`, `end_time`, `capacity`.

```json
{
  "start_time": "2026-11-15T15:00:00Z",
  "end_time": "2026-11-15T16:30:00Z",
  "capacity": 60
}
```

- **Response `200 OK`:** `SessionRead` actualizado.
- **Errores:** los mismos códigos y mensajes que `POST`, con estas particularidades:
  - `404 "Sesión no encontrada"` si la sesión no existe o no pertenece a `event_id`.
  - `422` con `"Debes indicar al menos un campo para actualizar"` si el cuerpo es `{}` o no trae campos.
  - El solapamiento se evalúa excluyendo la propia sesión; un horario idéntico al actual no genera conflicto consigo mismo.

### 8.5. `DELETE /api/events/{event_id}/sessions/{session_id}`

- **Descripción:** Elimina físicamente una sesión sin asistentes inscritos.
- **Autenticación / rol requerido:** `ORGANIZER` propietario del evento o `ADMIN`.
- **Parámetros de ruta:** `event_id` y `session_id` enteros `>= 1`.
- **Response `204 No Content`:** Sin cuerpo.
- **Errores:**

| Código | Cuándo                                                                 | `detail` (español)                                                            |
| ------ | ---------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| 400    | No se usa                                                              | —                                                                             |
| 401    | Token ausente, inválido, expirado o usuario inactivo                   | `"No autenticado o sesión expirada"`                                          |
| 403    | Rol `ATTENDEE` u `ORGANIZER` ajeno                                     | `"No tienes permisos para realizar esta acción"`                              |
| 404    | El evento no existe                                                    | `"Evento no encontrado"`                                                      |
| 404    | La sesión no existe o no pertenece al evento                           | `"Sesión no encontrada"`                                                      |
| 409    | El evento está en `CANCELLED`                                          | `"Un evento cancelado no permite modificar sus sesiones"`                     |
| 409    | La sesión tiene asistentes inscritos (hook de dominio > 0)             | `"No se puede eliminar una sesión con asistentes inscritos"`                  |
| 422    | `event_id` o `session_id` no son enteros válidos                       | `"Error de validación en los datos enviados"` + `errors[].message`            |

## 9. Reglas de fecha y hora

1. **Entrada:** `start_time` y `end_time` aceptan ISO 8601 con offset explícito (`2026-11-15T09:00:00-05:00`) o `Z` (`2026-11-15T14:00:00Z`).
2. **Rechazo de fechas `naive`:** una cadena sin zona horaria (`2026-11-15T14:00:00`) responde `422` con `errors[].field` igual al campo y `errors[].message = "La fecha y hora debe incluir zona horaria (por ejemplo, Z)"`. No se asume UTC en silencio.
3. **Normalización:** cualquier offset se convierte a UTC antes de comparar, almacenar o serializar; en PostgreSQL se guarda como `TIMESTAMP WITH TIME ZONE` y en JSON se serializa con sufijo `Z`.
4. **Orden:** `start_time` debe ser estrictamente anterior a `end_time`; igualdad o inversión responde `422` con `"La hora de inicio debe ser anterior a la hora de fin"`.
5. **Ventana:** `start_time >= event.date` (instante UTC) y `end_time <= date_trunc('day', event.date en UTC) + 1 day`. Una sesión que empieza el día anterior, que termina después de medianoche o que cruza medianoche queda fuera y responde `409`.
6. **Fechas pasadas:** se permiten si cumplen la ventana del evento; no se compara contra el reloj del sistema. Esto mantiene las pruebas deterministas (R3.7).
7. **Medianoche exacta:** `end_time` igual a la medianoche UTC siguiente es válido (`00:00:00` del día siguiente); un segundo después no.
8. **Zona horaria del evento:** `event.date` con offset se normaliza a UTC antes de calcular la ventana. La frontera es la fecha UTC resultante, no la fecha local original.

### 9.1. Limitación documentada de la ventana

La interpretación literal de `EVT-BR-05` (`session.start_time >= event.date`) impide programar sesiones antes de la hora del día de `event.date`: si el evento está fechado a las `14:00Z`, una sesión a las `09:00Z` del mismo día se rechaza con `409`. Permitir mañanas requeriría enmendar `specs/events/spec.md` (`EVT-BR-05`) para separar la fecha del evento de la hora de inicio de su agenda. Esa enmienda está **fuera del alcance** de esta ejecución y no se aplica aquí.

## 10. Regla de no solapamiento

1. **Semántica:** intervalos semiabiertos `[start_time, end_time)`. El instante `end_time` no pertenece a la sesión.
2. **Bordes válidos:** una sesión `10:00–11:00` y otra `11:00–12:00` no se solapan. Una sesión `10:00–11:00` y otra `10:30–11:30` sí.
3. **Ámbito:** solo se comparan sesiones del mismo `event_id`. Eventos distintos pueden tener sesiones en el mismo horario.
4. **Condición:** `existing.start_time < new.end_time AND existing.end_time > new.start_time`.
5. **`PATCH`:** se excluye la propia sesión (`Session.id != session_id`) y se evalúa el par final resultante de combinar los campos enviados con los actuales.
6. **Respuesta:** `409` con `detail = "La sesión se solapa con otra sesión del evento"`.
7. **Transacción:** la comprobación y la escritura ocurren dentro de la misma transacción, con la fila del evento bloqueada con `SELECT ... FOR UPDATE` antes de consultar solapamientos. El bloqueo también se toma en `DELETE`.
8. **Aislamiento:** PostgreSQL en `READ COMMITTED`; el bloqueo de la fila del evento serializa todas las escrituras de sesiones de ese evento, incluidas las de conexiones concurrentes.

## 11. Reglas de capacidad

1. `capacity` es obligatoria, entera, `>= 1` y `<= 100000` (límites de schema → `422`).
2. `capacity <= event.total_capacity` en creación y edición; si se supera → `409` con `"La capacidad de la sesión no puede superar la capacidad total del evento"`.
3. `registered_count` se obtiene de `get_session_registered_count(session, session_id) -> int`, que devuelve `0` mientras no exista `registrations` y es sustituible por monkeypatch en pruebas.
4. `available_capacity = max(0, capacity - registered_count)`; el frontend lo consume tal cual y no lo recalcula (R2.5).
5. **Contrato futuro:** si en el futuro `capacity < get_session_registered_count(...)`, la edición responderá `409` con `"No se puede reducir la capacidad de la sesión por debajo del número de inscritos actuales"`. Hoy el hook devuelve `0`, por lo que el camino no se dispara; la regla queda especificada para `registrations`.
6. **Reducción de la capacidad del evento:** si `events` reduce `total_capacity` después de crear sesiones, las capacidades de las sesiones no se ajustan retroactivamente. `registrations` deberá validar simultáneamente la capacidad del evento y la de la sesión al inscribir. Esta frontera no modifica `backend/app/events/`.
7. **Borrado con inscritos:** `DELETE` de una sesión con `get_session_registered_count(...) > 0` responde `409` con `"No se puede eliminar una sesión con asistentes inscritos"`.

## 12. Reglas de visibilidad

1. **Evento visible para el actor:**
   - Anónimo y `ATTENDEE`: solo `PUBLISHED`.
   - `ORGANIZER`: `PUBLISHED` de cualquiera más cualquier estado de sus propios eventos.
   - `ADMIN`: cualquier estado.
2. **Evento no visible o inexistente:** `404 "Evento no encontrado"`. No se revela si el evento existe en `DRAFT`/`CANCELLED` ajeno (R5.8).
3. **Evento visible pero sesión inexistente o de otro evento:** `404 "Sesión no encontrada"`.
4. **Lecturas:** Bearer opcional; un token inválido presente corta con `401` en lugar de tratarse como Anónimo.
5. **Escrituras:** la cadena es 401 (token) → 403 (rol/propiedad) → 404 (evento o sesión inexistente) → 409 (estado, ventana, solapamiento, capacidad, inscritos) → 422 (schema). Un `ORGANIZER` ajeno recibe `403` aunque el evento esté `CANCELLED`.
6. **Listado:** el `total` refleja solo las sesiones del evento visible; un evento visible sin sesiones devuelve `200` con `items: []` y `total: 0`.

## 13. Casos límite

- **Evento inexistente:** `404 "Evento no encontrado"` en listado, detalle y escrituras, después de validar token y rol.
- **Sesión inexistente:** `404 "Sesión no encontrada"` en detalle, `PATCH` y `DELETE` cuando el evento sí es visible.
- **Sesión de otro evento:** `GET`, `PATCH` o `DELETE` con `session_id` de otro evento → `404 "Sesión no encontrada"`; nunca se opera sobre ella.
- **Evento `CANCELLED`:** lecturas permitidas según visibilidad; `POST`, `PATCH` y `DELETE` → `409 "Un evento cancelado no permite modificar sus sesiones"`.
- **Evento borrado con sesiones:** al eliminar un evento sin inscritos, la FK `ON DELETE CASCADE` elimina sus sesiones; no quedan huérfanas.
- **Body vacío en `PATCH`:** `422` con `errors[].message = "Debes indicar al menos un campo para actualizar"`.
- **Fecha sin zona horaria:** `422` con el mensaje exacto de zona horaria; no se interpreta como UTC.
- **Cruce de medianoche:** `start_time` el día del evento y `end_time` al día siguiente → `409` por ventana.
- **Sesión antes de la hora de `event.date`:** `409` por ventana (limitación documentada en §9.1).
- **Solapamiento exacto:** dos sesiones con el mismo `start_time` y `end_time` → la segunda recibe `409`.
- **Sesiones consecutivas:** `10:00–11:00` y `11:00–12:00` → ambas válidas.
- **Mismo horario en eventos distintos:** válido; el no solapamiento es por evento.
- **Concurrencia:** dos transacciones intentan crear sesiones solapadas del mismo evento; una responde `201` y la otra `409`; al final existe una sola fila.
- **Capacidad límite:** `capacity = 1` y `capacity = event.total_capacity` son válidos; `capacity = 0` y `capacity = 100001` son `422`; `capacity = event.total_capacity + 1` es `409`.
- **Descripción vacía:** `""` o `"   "` se normaliza a `null`; no produce error.
- **`event_id` en el cuerpo:** `422` con `"Este campo no está permitido"`; el valor de la ruta manda y es inmutable.
- **IDs inválidos:** `event_id` o `session_id` no entero o `< 1` → `422`.
- **Evento sin sesiones:** `200` con `items: []` y `total: 0`.
- **PATCH que no cambia el horario:** se permite si el par final no se solapa con otras sesiones; `updated_at` cambia igualmente.
- **PATCH de solo `start_time`:** se combina con el `end_time` actual; si el resultado invierte el orden, `422`; si sale de la ventana o se solapa, `409`.

## 14. Seguridad y privacidad

- **Cadena única de dependencias (R5.2):** token presente → firma → expiración → usuario existente → usuario activo → rol → propiedad del evento → existencia de la sesión. El primer fallo corta la petición.
- **Autorización en servidor (R5.3):** la UI puede ocultar controles, pero el backend verifica propiedad y rol en cada escritura. Los guards y formularios de Vue son ayudas de UX (R2.5).
- **No enumeración de borradores (R5.8):** un evento `DRAFT` o `CANCELLED` ajeno responde `404 "Evento no encontrado"` en lectura, no `403`.
- **Privacidad:** no se exponen datos de usuarios, inscripciones ni identificadores internos; `SessionRead` solo contiene datos de la sesión.
- **Errores sin trazas (R5.8):** los mensajes son en español, no incluyen SQL, rutas de archivos, nombres de tablas ni trazas.
- **XSS (R5.9):** `title`, `speaker` y `description` se interpolan en Vue con `{{ ... }}`; prohibido `v-html`.
- **Secretos (R5.7):** esta spec no contiene credenciales ni datos personales.
- **Integridad transaccional (R5.4):** el bloqueo `FOR UPDATE` del evento evita carreras de solapamiento; la capacidad se recalcula en el backend.

## 15. Dependencias futuras con `registrations`

No se implementa nada de esta sección en el Dominio 3; se documenta el contrato para el Dominio 4.

1. `registrations` añadirá `session_id` opcional con FK a `sessions.id`; la inscripción a una sesión requerirá inscripción previa al evento (decisión del Dominio 4).
2. La unicidad de inscripción por usuario y sesión se modelará con restricción/índice en `registrations`.
3. La inscripción a una sesión comprobará de forma atómica la capacidad del evento y de la sesión, bloqueando las filas necesarias en la misma transacción.
4. `get_session_registered_count(session, session_id)` se implementará consultando el conteo real; hasta entonces devuelve `0`.
5. Toda inscripción o anulación que afecte a una sesión invalidará el prefijo `events:` y el listado/detalle de sesiones cuando exista caché de sesiones (hoy no la hay).
6. `SessionRead.registered_count` y `available_capacity` pasarán a reflejar valores reales sin cambiar el contrato.

## 16. Criterios de aceptación (EARS)

Cada criterio tiene al menos un test cuyo nombre incluye su ID (R1.5, R1.9). Se usan las cinco formas de EARS: ubicuo, por evento, por estado, no deseado y opcional.

| ID            | Criterio (notación EARS en español)                                                                                                                                                                                                                                                                                                                                                                                   | Reglas                                  |
| ------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------- |
| **SES-AC-01** | Cuando el `ORGANIZER` propietario o un `ADMIN` envía `POST /api/events/{event_id}/sessions` con datos válidos, el sistema debe crear la sesión con `event_id` tomado de la ruta, `registered_count = 0`, `available_capacity = capacity`, `created_at` y `updated_at` en UTC, y responder `201` con `SessionRead`.                                                                                                          | SES-BR-01, SES-BR-02, SES-BR-03, SES-BR-09 |
| **SES-AC-02** | Si el cuerpo de `POST` o `PATCH` incluye `event_id`, `id`, `registered_count`, `available_capacity`, `created_at`, `updated_at` u otro campo no permitido, o si `title`/`speaker`/`description` incumplen sus longitudes tras `trim`, entonces el sistema debe responder `422` con `detail = "Error de validación en los datos enviados"` y `errors[].message` en español (`"Este campo no está permitido"` para extras).       | SES-BR-01, SES-BR-12                    |
| **SES-AC-03** | El sistema debe aceptar `capacity` entre `1` y `100000` en el schema; si `capacity < 1` o `capacity > 100000` debe responder `422`, y si `capacity > event.total_capacity` debe responder `409` con `"La capacidad de la sesión no puede superar la capacidad total del evento"`.                                                                                                                                        | SES-BR-01, SES-BR-09                    |
| **SES-AC-04** | Si en `POST` o `PATCH` el par final cumple `start_time >= end_time`, entonces el sistema debe responder `422` con `errors[].message = "La hora de inicio debe ser anterior a la hora de fin"`.                                                                                                                                                                                                                           | SES-BR-05                               |
| **SES-AC-05** | Si `start_time` o `end_time` llegan sin zona horaria, entonces el sistema debe responder `422` con `errors[].message = "La fecha y hora debe incluir zona horaria (por ejemplo, Z)"`; cuando llegan con offset, el sistema debe normalizarlas a UTC y serializarlas en ISO 8601 terminadas en `Z`.                                                                                                                           | SES-BR-05                               |
| **SES-AC-06** | Cuando una sesión se crea o edita, el sistema debe exigir `start_time >= event.date` y `end_time <= date_trunc('day', event.date en UTC) + 1 day`; si queda fuera o cruza medianoche, debe responder `409` con `"La sesión debe estar dentro de la fecha UTC del evento y no puede cruzar la medianoche"`.                                                                                                              | SES-BR-06                               |
| **SES-AC-07** | Donde la sesión se celebre en una fecha pasada respecto al reloj del servidor, el sistema debe permitirla siempre que cumpla la ventana del evento, para que las pruebas sean deterministas.                                                                                                                                                                                                                            | SES-BR-05, SES-BR-06                    |
| **SES-AC-08** | Cuando se crea una sesión que se solapa con otra del mismo evento según la condición `existing.start_time < new.end_time AND existing.end_time > new.start_time`, el sistema debe responder `409` con `"La sesión se solapa con otra sesión del evento"`; las sesiones consecutivas y las de eventos distintos deben aceptarse.                                                                                          | SES-BR-07                               |
| **SES-AC-09** | Cuando se envía `PATCH` con solo `start_time` o solo `end_time`, el sistema debe combinar el valor enviado con el actual, validar `start < end`, la ventana y el solapamiento sobre el par final excluyendo la propia sesión, y responder `200` o el `409`/`422` correspondiente.                                                                                                                                        | SES-BR-05, SES-BR-06, SES-BR-07         |
| **SES-AC-10** | Mientras dos conexiones independientes contra PostgreSQL intentan crear sesiones solapadas del mismo evento de forma concurrente, el sistema debe serializar las escrituras con `SELECT ... FOR UPDATE` sobre el evento, permitir un solo `201`, responder `409` a la otra y dejar exactamente una fila.                                                                                                                  | SES-BR-08, SES-BR-07                    |
| **SES-AC-11** | Cuando un actor visible consulta `GET /api/events/{event_id}/sessions`, el sistema debe devolver `200` con `SessionListRead { items, total }`, ordenado por `start_time ASC, id ASC`, sin paginación, y `items: []`, `total: 0` si el evento no tiene sesiones.                                                                                                                                                           | SES-BR-05, SES-BR-11                    |
| **SES-AC-12** | Cuando se consulta `GET /api/events/{event_id}/sessions/{session_id}` con un evento visible y una sesión existente del evento, el sistema debe responder `200` con `SessionRead`; si la sesión no existe o pertenece a otro evento, debe responder `404 "Sesión no encontrada"`; si el evento no existe o no es visible, `404 "Evento no encontrado"`.                                                                     | SES-BR-04, SES-BR-11                    |
| **SES-AC-13** | Mientras el actor sea Anónimo o `ATTENDEE`, el sistema debe permitirle leer únicamente sesiones de eventos `PUBLISHED` y responder `404 "Evento no encontrado"` en `DRAFT` o `CANCELLED`.                                                                                                                                                                                                                              | SES-BR-04                               |
| **SES-AC-14** | Cuando el actor sea un `ORGANIZER`, el sistema debe permitirle leer las sesiones de todos los eventos `PUBLISHED` y las de sus propios eventos en cualquier estado, y responder `404 "Evento no encontrado"` en eventos no publicados ajenos.                                                                                                                                                                             | SES-BR-04                               |
| **SES-AC-15** | Cuando el actor sea `ADMIN`, el sistema debe permitirle leer las sesiones de cualquier evento en cualquier estado (`DRAFT`, `PUBLISHED`, `CANCELLED`) tanto en listado como en detalle.                                                                                                                                                                                                                                  | SES-BR-04                               |
| **SES-AC-16** | Si una petición de escritura (`POST`, `PATCH`, `DELETE`) carece de token válido, entonces el sistema debe responder `401` con `"No autenticado o sesión expirada"` y `WWW-Authenticate: Bearer`; si proviene de un `ATTENDEE` o de un `ORGANIZER` ajeno al evento, debe responder `403` con `"No tienes permisos para realizar esta acción"`.                                                                              | SES-BR-03                               |
| **SES-AC-17** | Cuando el `ORGANIZER` propietario o un `ADMIN` crea, edita o elimina sesiones de un evento en `DRAFT` o `PUBLISHED`, el sistema debe aplicar la operación y responder `201`, `200` o `204` respectivamente.                                                                                                                                                                                                             | SES-BR-03, SES-BR-10                    |
| **SES-AC-18** | Mientras el evento esté en `CANCELLED`, si el propietario o un `ADMIN` intenta `POST`, `PATCH` o `DELETE` sobre sus sesiones, entonces el sistema debe responder `409` con `"Un evento cancelado no permite modificar sus sesiones"`.                                                                                                                                                                                    | SES-BR-10                               |
| **SES-AC-19** | Cuando el propietario o un `ADMIN` elimina una sesión sin inscritos, el sistema debe borrarla físicamente y responder `204`; si `get_session_registered_count` devuelve un valor mayor que `0`, debe responder `409` con `"No se puede eliminar una sesión con asistentes inscritos"`.                                                                                                                                  | SES-BR-09, SES-BR-11                    |
| **SES-AC-20** | Cuando se elimina físicamente un evento sin inscritos, el sistema debe eliminar sus sesiones mediante la FK `ON DELETE CASCADE`, sin dejar filas huérfanas ni modificar el contrato de `events`.                                                                                                                                                                                                                         | SES-BR-02                               |
| **SES-AC-21** | El sistema debe almacenar y serializar `created_at` y `updated_at` en UTC (`Z`), actualizar `updated_at` en cada `PATCH`, y mantener `event_id` inmutable: no se acepta en el cuerpo y no cambia por la ruta.                                                                                                                                                                                                            | SES-BR-01, SES-BR-02, SES-BR-05         |
| **SES-AC-22** | El sistema debe usar el formato de error de `platform`: `{"detail": "..."}` en español para `401/403/404/409` y `detail = "Error de validación en los datos enviados"` más `errors: [{"field", "message"}]` en español para `422`, incluido el cuerpo vacío de `PATCH` con `"Debes indicar al menos un campo para actualizar"`; el código `400` no se usa en este dominio.                                              | SES-BR-12                               |
| **SES-AC-23** | El sistema debe exponer en `/api/openapi.json` las cinco operaciones de sesiones con tag `sessions`, los schemas `SessionCreate`, `SessionUpdate`, `SessionRead` y `SessionListRead`, y los códigos `401`, `403`, `404`, `409` y `422` declarados en cada operación.                                                                                                                                                     | SES-BR-12                               |
| **SES-AC-24** | Cuando se crea, edita o elimina una sesión, el sistema debe invalidar el prefijo de caché `events:` sin cachear el listado de sesiones; si Redis no está disponible, la escritura debe completarse igualmente sin propagar el error.                                                                                                                                                                                  | SES-BR-12                               |
| **SES-AC-25** | El sistema debe crear la tabla `sessions` mediante la migración Alembic `0004_create_sessions` con PK, FK `event_id → events.id ON DELETE CASCADE`, `NOT NULL` donde corresponde, restricciones de longitud, `CHECK` de rango de tiempos y capacidad, e índices `(event_id, start_time)` y `(event_id, end_time)`.                                                                                                       | SES-BR-01, SES-BR-02, SES-BR-07, SES-BR-08 |
| **SES-AC-26** | Cuando el frontend invoca las acciones de `useSessionStore`, el store debe consumir `/api/events/{event_id}/sessions`, actualizar `items`, `total`, `currentSession`, `isLoading` y `errorMessage`, y sus DTOs en `types/api.ts` deben coincidir con `SessionRead`/`SessionListRead` sin recalcular `available_capacity` ni enviar `event_id` en el cuerpo.                                                              | SES-BR-09, SES-BR-12                    |
| **SES-AC-27** | Cuando un usuario navega a `/events/:id`, `EventDetailView.vue` debe componer el detalle con dos llamadas (`GET /api/events/{id}` y `GET /api/events/{id}/sessions`), mostrar `SessionTimeline.vue` con las sesiones en orden cronológico, su ponente, horario y cupos de la API, estados de carga y vacío, y sin usar `v-html`.                                                                                        | SES-BR-04, SES-BR-11, SES-BR-12         |
| **SES-AC-28** | Donde el usuario sea el `ORGANIZER` dueño del evento o `ADMIN`, el frontend debe mostrar el formulario `SessionForm.vue` para crear o editar sesiones, convertir `datetime-local` a UTC con sufijo `Z` antes de enviar, mostrar los errores `422` por campo y los `409` en español, ocultarlo o deshabilitarlo en eventos `CANCELLED` y cargarlo con `defineAsyncComponent`; a los demás roles no debe mostrarle controles de escritura. | SES-BR-03, SES-BR-10, SES-BR-12         |
| **SES-AC-29** | Si se envía `PATCH` o `DELETE` sobre una sesión que no existe o que pertenece a otro evento, entonces el sistema debe responder `404 "Sesión no encontrada"` sin modificar ni eliminar ninguna fila; si el evento no existe, debe responder `404 "Evento no encontrado"`.                                                                                                                                                  | SES-BR-11, SES-BR-03                    |
| **SES-AC-30** | Mientras una transacción elimina una sesión y otra crea o edita una sesión del mismo evento de forma concurrente, el sistema debe serializarlas con `SELECT ... FOR UPDATE` sobre la fila del evento, de modo que la comprobación de solapamiento nunca observe una fila en proceso de borrado y el resultado final sea consistente (una sola fila nueva o un `409`).                                                        | SES-BR-08, SES-BR-07                    |

## 17. Decisiones resueltas

Todas las decisiones fueron consultadas y resueltas con el usuario el **2026-10-31**.

| Fecha      | Pregunta / decisión                                                                 | Resolución adoptada                                                                                                                                                                                                                                                                                                                                 | Motivo                                                                                                  |
| ---------- | ----------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| 2026-10-31 | **D1. Modelo `Session`**                                                             | Tabla `sessions` con `id`, `event_id`, `title` (3–160), `speaker` (2–120, texto), `description` opcional (≤ 2000, vacío → `null`), `start_time`/`end_time` UTC, `capacity` (≥ 1), `created_at`/`updated_at`. Sin `status` ni auditoría de usuario. `SessionRead` incluye `registered_count` y `available_capacity` con hook `get_session_registered_count`. | Modelo mínimo fiel a la arquitectura v1.1 §3.4 y al requisito de ponentes sin introducir una entidad extra. |
| 2026-10-31 | **D2. Relación con `Event`**                                                         | 1:N con FK `event_id → events.id ON DELETE CASCADE`; `event_id` inmutable y fuera del cuerpo; el evento debe existir. `DRAFT`/`PUBLISHED` permiten escrituras; `CANCELLED` es solo lectura. El borrado de eventos no cambia.                                                                                                                            | Integridad referencial y preparación de agenda antes de publicar.                                        |
| 2026-10-31 | **D3. Permisos y visibilidad**                                                       | Escrituras: `ORGANIZER` dueño o `ADMIN` (`401`/`403`). Lecturas con Bearer opcional: Anónimo/`ATTENDEE` solo `PUBLISHED`; `ORGANIZER` `PUBLISHED` + propios; `ADMIN` todo. Evento no visible → `404 "Evento no encontrado"`; sesión no visible → `404 "Sesión no encontrada"`.                                                                         | R5.3 y R5.8: no revelar borradores ni permitir escritura ajena.                                          |
| 2026-10-31 | **D4. Fechas, zona horaria y ventana del evento**                                    | ISO 8601 con offset o `Z`; `naive` → `422` con mensaje específico; almacenamiento/serialización UTC. Ventana literal de `EVT-BR-05`: `event.date <= start_time` y `end_time <= medianoche UTC siguiente`; sin cruce de medianoche; `409` con mensaje exacto. Fechas pasadas permitidas.                                                              | Determinismo (R3.7) y coherencia con `EVT-BR-05`; la limitación de mañanas queda documentada.           |
| 2026-10-31 | **D5. Solapamiento y concurrencia**                                                  | Intervalos `[start, end)`; condición `existing.start_time < new.end_time AND existing.end_time > new.start_time`; consecutivas válidas; `PATCH` excluye la propia sesión. Transacción con `SELECT ... FOR UPDATE` sobre `events` antes de comprobar y escribir; `DELETE` también bloquea. `EXCLUDE USING GIST`/`btree_gist` descartado.                     | Serialización simple y portable con el stack actual (R4.5, R5.4).                                        |
| 2026-10-31 | **D6. Capacidad**                                                                    | `capacity` propia `1..100000` y `<= event.total_capacity` (`409`); cupos calculados en backend con hook; reducción futura bajo inscritos `409`; el evento no ajusta sesiones retroactivamente; borrado con inscritos `409`.                                                                                                                           | R2.5 y frontera explícita con `registrations`.                                                           |
| 2026-10-31 | **D7. Endpoints, listado y borrado**                                                 | Rutas anidadas; listado completo sin paginación `{items,total}` ordenado `start_time ASC, id ASC`; `PATCH` parcial; `DELETE` físico `204`; `PATCH {}` → `422`; `extra="forbid"`; sin cambios en `EventRead`.                                                                                                                                         | Contrato mínimo y coherente con la UI de detalle.                                                        |
| 2026-10-31 | **D8. API, errores y OpenAPI**                                                       | Tag `sessions`; `error_responses(401, 403, 404, 409, 422)` por operación; `400` no se usa; mensajes exactos definidos en §8; `422` con `errors[]` en español.                                                                                                                                                                                         | Contrato verificable y consistente con `platform` y `events`.                                            |
| 2026-10-31 | Derivada: ventana impide sesiones antes de la hora de `event.date`                   | Se acepta la interpretación literal de `EVT-BR-05`; permitir mañanas exigiría enmendar `specs/events/spec.md`, fuera de alcance.                                                                                                                                                                                                                       | No se reabre una spec ya implementada en esta ejecución; se documenta la limitación.                     |
| 2026-10-31 | Derivada: capacidad del evento vs. capacidad de sesión                              | No se ajustan sesiones al reducir `total_capacity`; `registrations` validará ambos límites al inscribir.                                                                                                                                                                                                                                               | Evita efectos retroactivos y mantiene `events` intacto.                                                  |

## 18. Decisiones pendientes

Ninguna. El usuario aprobó explícitamente esta spec el 2026-10-31 ("Sí, apruebo") y se inició la implementación (R1.8).

La enmienda v0.2 (2026-11-01), que añade `SES-AC-29` y `SES-AC-30` y las tareas `B27`/`B28`, fue aprobada explícitamente por el usuario el 2026-11-01 (R1.8) y se retoma la implementación.

La implementación TDD (`B1..B28`, `F1..F7`) y la validación (`V1..V6`) se completaron el 2026-11-01; el `reviewer` emitió el veredicto `¿pasa? sí` (30/30 criterios `SES-AC` y 12/12 reglas `SES-BR`), por lo que la spec pasa de `En implementación` a `Implementada`.

No se detectaron contradicciones sin resolver entre la prueba técnica, la constitución, la arquitectura v1.1 y las specs de `platform`, `auth` y `events`. La única tensión documentada es la limitación de la ventana de §9.1, que se resuelve respetando `EVT-BR-05` y queda registrada para una posible enmienda futura de `events`.

## 19. Matriz de trazabilidad (`SES-BR-NN` ↔ `SES-AC-NN` ↔ tareas)

| Regla de negocio | Criterios de aceptación                                     | Tareas TDD asociadas (`specs/sessions/tasks.md`)                     |
| ---------------- | ----------------------------------------------------------- | -------------------------------------------------------------------- |
| **SES-BR-01**    | `SES-AC-01`, `SES-AC-02`, `SES-AC-03`, `SES-AC-21`, `SES-AC-25` | `B1`, `B2`, `B3`, `B4`, `B22`                                        |
| **SES-BR-02**    | `SES-AC-01`, `SES-AC-20`, `SES-AC-21`, `SES-AC-25`          | `B1`, `B2`, `B22`, `B26`                                             |
| **SES-BR-03**    | `SES-AC-01`, `SES-AC-16`, `SES-AC-17`, `SES-AC-28`, `SES-AC-29` | `B2`, `B17`, `B18`, `B27`, `F5`, `F6`                                |
| **SES-BR-04**    | `SES-AC-12`, `SES-AC-13`, `SES-AC-14`, `SES-AC-15`, `SES-AC-27` | `B13`, `B14`, `B15`, `B16`, `F3`                                  |
| **SES-BR-05**    | `SES-AC-04`, `SES-AC-05`, `SES-AC-07`, `SES-AC-09`, `SES-AC-11`, `SES-AC-21` | `B5`, `B6`, `B8`, `B10`, `B12`, `B22`                                |
| **SES-BR-06**    | `SES-AC-06`, `SES-AC-07`, `SES-AC-09`                       | `B7`, `B8`, `B10`                                                    |
| **SES-BR-07**    | `SES-AC-08`, `SES-AC-09`, `SES-AC-10`, `SES-AC-25`, `SES-AC-30` | `B9`, `B10`, `B11`, `B28`, `V3`                                      |
| **SES-BR-08**    | `SES-AC-10`, `SES-AC-25`, `SES-AC-30`                       | `B1`, `B11`, `B28`, `V3`                                             |
| **SES-BR-09**    | `SES-AC-01`, `SES-AC-03`, `SES-AC-19`, `SES-AC-26`          | `B2`, `B4`, `B20`, `B21`, `F1`                                       |
| **SES-BR-10**    | `SES-AC-17`, `SES-AC-18`, `SES-AC-28`                       | `B18`, `B19`, `F5`, `F6`                                             |
| **SES-BR-11**    | `SES-AC-11`, `SES-AC-12`, `SES-AC-19`, `SES-AC-20`, `SES-AC-27`, `SES-AC-29` | `B12`, `B13`, `B20`, `B21`, `B26`, `B27`, `F2`, `F3`, `F7`           |
| **SES-BR-12**    | `SES-AC-02`, `SES-AC-22`, `SES-AC-23`, `SES-AC-24`, `SES-AC-26`, `SES-AC-27`, `SES-AC-28` | `B3`, `B23`, `B24`, `B25`, `F1`, `F2`, `F3`, `F4`, `F5`, `F6`, `F7`, `V2`, `V4`, `V5` |

Cobertura de criterios por tarea (resumen):

| Tarea | Criterios                                                                                   |
| ----- | ------------------------------------------------------------------------------------------- |
| `B1`  | `SES-AC-25`                                                                                 |
| `B2`  | `SES-AC-01`                                                                                 |
| `B3`  | `SES-AC-02`                                                                                 |
| `B4`  | `SES-AC-03`                                                                                 |
| `B5`  | `SES-AC-04`                                                                                 |
| `B6`  | `SES-AC-05`                                                                                 |
| `B7`  | `SES-AC-06`                                                                                 |
| `B8`  | `SES-AC-07`                                                                                 |
| `B9`  | `SES-AC-08`                                                                                 |
| `B10` | `SES-AC-09`                                                                                 |
| `B11` | `SES-AC-10`                                                                                 |
| `B12` | `SES-AC-11`                                                                                 |
| `B13` | `SES-AC-12`                                                                                 |
| `B14` | `SES-AC-13`                                                                                 |
| `B15` | `SES-AC-14`                                                                                 |
| `B16` | `SES-AC-15`                                                                                 |
| `B17` | `SES-AC-16`                                                                                 |
| `B18` | `SES-AC-17`                                                                                 |
| `B19` | `SES-AC-18`                                                                                 |
| `B20` | `SES-AC-19`                                                                                 |
| `B21` | `SES-AC-19`                                                                                 |
| `B22` | `SES-AC-21`                                                                                 |
| `B23` | `SES-AC-22`                                                                                 |
| `B24` | `SES-AC-23`                                                                                 |
| `B25` | `SES-AC-24`                                                                                 |
| `B26` | `SES-AC-20`                                                                                 |
| `B27` | `SES-AC-29`                                                                                 |
| `B28` | `SES-AC-30`                                                                                 |
| `F1`  | `SES-AC-26`                                                                                 |
| `F2`  | `SES-AC-27`                                                                                 |
| `F3`  | `SES-AC-27`                                                                                 |
| `F4`  | `SES-AC-28`                                                                                 |
| `F5`  | `SES-AC-28`                                                                                 |
| `F6`  | `SES-AC-28`                                                                                 |
| `F7`  | `SES-AC-27`, `SES-AC-28`                                                                    |
| `V1`  | `SES-AC-25`                                                                                 |
| `V2`  | `SES-AC-23`                                                                                 |
| `V3`  | `SES-AC-08`, `SES-AC-10`, `SES-AC-30`                                                       |
| `V4`  | `SES-AC-26`, `SES-AC-27`, `SES-AC-28`                                                       |
| `V5`  | `SES-AC-27`, `SES-AC-28`                                                                    |
| `V6`  | Todos (`SES-AC-01` a `SES-AC-30`)                                                           |

## 20. Historial

| Versión | Fecha      | Cambio                                                                                                                                                          |
| ------- | ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 0.1     | 2026-10-31 | Borrador inicial completo del dominio `sessions` (`SES`) con las 8 decisiones funcionales D1–D8 resueltas con el usuario y 28 criterios EARS `SES-AC-01..28`.   |
| 0.1     | 2026-10-31 | Aprobación explícita del usuario ("Sí, apruebo") tras la revisión de la spec: Borrador → Aprobada.                                                               |
| 0.1     | 2026-10-31 | Inicio de la implementación aprobado en la misma decisión: Aprobada → En implementación (Paso 6, TDD).                                                          |
| 0.2     | 2026-11-01 | Enmienda por hallazgos de QA: nuevos criterios SES-AC-29 (404 en escrituras sobre sesión ajena/inexistente) y SES-AC-30 (serialización de DELETE con FOR UPDATE) y tareas B27/B28. |
| 0.2     | 2026-11-01 | Aprobación explícita de la enmienda v0.2 por el usuario ("Sí, apruebo la v0.2"): se retoma la implementación de B27/B28 y la validación. |
| 0.2     | 2026-11-01 | Implementación TDD completa (B1..B28, F1..F7) y validación (V1..V6) con veredicto ¿pasa? sí del reviewer (30/30 SES-AC): En implementación → Implementada. |

## 21. Referencias normativas

1. `docs/prueba_tecnica_desarrollador_fullstack.md` — "Programación de sesiones: creación y gestión, asignación de ponentes, validación de horarios y control de capacidad"; detalle de evento con sesiones.
2. `docs/constitution.md` (v1.1.1) — Principios 1–6, R1.5/R1.8/R1.9, R2.5, R3.4/R3.6/R3.7, R4.4/R4.5, R5.2–R5.9, R6.
3. `docs/Analisis-Arquitectonico-Funcional-Plataforma-Mis-Eventos.md` (v1.1) — §3.4 modelo de datos y diagrama ER, §3.5 reglas críticas, §3.6 caché, §3.7 migraciones.
4. `specs/README.md` — orden de dominios, dependencias y estado de las specs.
5. `specs/platform/spec.md` — formato de error, fechas UTC, caché y convenciones.
6. `specs/auth/spec.md` — JWT, RBAC y semántica 401/403.
7. `specs/events/spec.md` — `Event`, `EventStatus`, `event.date`, `event.total_capacity`, `EVT-BR-05` y caché `events:`.
