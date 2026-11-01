# Spec: Inscripciones y Capacidad (`registrations`)

| Campo                      | Valor                                                                                                                                                                  |
| -------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **ID del dominio**         | `REG`                                                                                                                                                                  |
| **Versión**                | 0.1                                                                                                                                                                    |
| **Estado**                 | Implementada                                                                                                                                                           |
| **Fecha**                  | 2026-11-01                                                                                                                                                             |
| **Dependencias**           | `platform` (Dominio 0, v1.0), `auth` (Dominio 1, v1.0), `events` (Dominio 2, v1.0), `sessions` (Dominio 3, v0.2)                                                         |
| **Decisiones bloqueantes** | Ninguna; 14 decisiones resueltas con el usuario el 2026-11-01 (D1–D14) y 2 decisiones derivadas (D15–D16). Aprobada explícitamente por el usuario el 2026-11-01.        |

> Esta spec describe **qué** hace el sistema en el dominio `registrations`, no cómo se implementa. Los detalles técnicos van en `plan.md`. Estado según R1.8 de `docs/constitution.md`: solo el usuario la marca como _Aprobada_. Una spec con decisiones bloqueantes abiertas no puede aprobarse.

## 1. Objetivo

Permitir que un asistente autenticado se inscriba a un evento publicado consumiendo exactamente un cupo de su capacidad, y opcionalmente a las sesiones de ese evento consumiendo el cupo propio de cada sesión, garantizando la atomicidad de la comprobación de capacidad y la inserción incluso con peticiones concurrentes, la unicidad de la inscripción activa por usuario y la liberación inmediata del cupo al cancelar. El dominio expone además "Mis inscripciones" al asistente y el listado de asistentes de un evento a su organizador propietario o a un administrador, sin revelar datos personales de los usuarios.

## 2. Alcance

### 2.1. Incluye

- Modelo `Registration` que vincula un usuario con un evento y, opcionalmente, con una sesión de ese evento, con estados `ACTIVE` y `CANCELLED` y marcas `created_at`/`updated_at` en UTC.
- Inscripción al evento (`POST /api/events/{event_id}/registrations`): obligatoria, un cupo por persona, solo en eventos `PUBLISHED`.
- Inscripción a una sesión (`POST /api/events/{event_id}/sessions/{session_id}/registrations`): opcional, exige inscripción activa al evento, consume el cupo propio de la sesión y no consume un cupo adicional del evento.
- Validación atómica de capacidad del evento y de la sesión en la misma transacción, con bloqueo de filas en el orden `events` → `sessions` y `READ COMMITTED`, probada contra PostgreSQL real con conexiones concurrentes.
- Restricciones únicas parciales que impiden dos inscripciones activas del mismo usuario al mismo evento y a la misma sesión.
- Reactivación de una inscripción `CANCELLED` mediante el mismo `POST`, revalidando estado del evento y capacidad.
- Cancelación lógica (`DELETE /api/registrations/{id}`) idempotente, sin plazo, con liberación inmediata del cupo y cancelación en cascada de las inscripciones activas a sesiones del mismo evento y usuario.
- Consultas: "mis inscripciones" paginada y filtrable (inscripciones al evento **y** a sesiones), listado paginado por evento para el organizador propietario o el `ADMIN` (solo inscripciones al evento, una por asistente) y detalle por identificador.
- Contadores reales en `EventRead.registered_count` y `SessionRead.registered_count` mediante los hooks existentes, sin cambiar sus firmas.
- Caché Redis prescindible de "mis inscripciones" por usuario con TTL de 60 segundos e invalidación en cada escritura.
- Frontend Vue 3: tipos, servicio y `useRegistrationStore`; sección "Mis inscripciones" en el perfil; acción de inscripción al evento y a sesiones en el detalle; listado de inscripciones del evento para organizador/`ADMIN`.

### 2.2. No incluye

- Cobros, facturación, entradas, códigos QR, check-in, control de asistencia real ni certificados.
- Listas de espera, sobreventa, reservas temporales de cupo o expiración de inscripciones por tiempo.
- Validación de conflicto de horario entre sesiones a las que se inscribe un mismo asistente (fuera de alcance; documentado en §11).
- Transferencia de una inscripción a otro usuario, inscripción en nombre de terceros o inscripción grupal.
- Notificaciones por correo, recordatorios o integraciones externas.
- Borrado físico de inscripciones desde la API: la cancelación es lógica y conserva la fila para permitir la reactivación.
- Cambio de `user_id`, `event_id` o `session_id` de una inscripción existente: son inmutables; la reactivación reutiliza la fila con los mismos identificadores.
- Un estado `PENDING`/`WAITLIST` ni máquina de estados adicional: solo `ACTIVE` y `CANCELLED`.
- Cupos por tipo de entrada, cupos por franja horaria ni aforo agregado distinto de la suma de sesiones.
- Modificación del contrato de `events` (`EventRead` no incorpora inscripciones) ni de `sessions` (`SessionRead` no incorpora inscripciones); solo se sustituye el cuerpo de sus hooks de conteo.
- Purga cruzada de inscripciones desde `events`/`sessions`: el histórico `CANCELLED` se elimina por la cascada de las FKs (`ON DELETE CASCADE`), sin lógica nueva en `delete_event`/`delete_session` (D15).
- Nuevas rutas de frontend: "Mis inscripciones" vive en `/profile` y el listado por evento en `/events/:id`.
- Dependencias nuevas de backend o frontend.

## 3. Dependencias

- **`platform` (v1.0):** formato de error `{"detail": "..."}` con `errors: [{"field", "message"}]` en `422`, convención de paginación `page`/`size` 1-indexed con sobre `{ items, total, page, size, pages }`, cliente Redis prescindible, fechas UTC con sufijo `Z`, `error_responses` para OpenAPI, gateway Nginx.
- **`auth` (v1.0):** `User`, `UserRole` (`ADMIN`, `ORGANIZER`, `ATTENDEE`), `get_current_user`, `require_roles`, semántica estricta 401 ≠ 403 (R5.6) y la frontera `AUTH-BR-12`/`AUTH-AC-30`: solo `ATTENDEE` se inscribe.
- **`events` (v1.0):** tabla `Event`, `EventStatus` (`DRAFT`, `PUBLISHED`, `CANCELLED`), `event.organizer_id`, `event.total_capacity`, `EventRead` con `registered_count`/`available_capacity`, hook `get_registered_count(session, event_id)` y prefijo de caché `events:` (`EVT-BR-04`, `EVT-BR-07`, `EVT-AC-15`, `EVT-AC-19`).
- **`sessions` (v0.2):** tabla `Session`, `session.event_id`, `session.capacity`, `SessionRead` con `registered_count`/`available_capacity`, hook `get_session_registered_count(session, session_id)` y el orden de bloqueo `events` → `sessions` ya establecido en `SES-BR-08` (`SES-BR-09`, `SES-BR-11`, §15).

## 4. Actores y roles

| Rol         | Qué puede hacer en este dominio                                                                                                                                                                                                                                                                                                                       |
| ----------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Anónimo     | Nada: todas las operaciones exigen token. Cualquier petición sin token válido responde `401 "No autenticado o sesión expirada"`.                                                                                                                                                                                                                      |
| `ATTENDEE`  | Crear su inscripción a un evento `PUBLISHED` con cupo (`201`), reactivarla (`200`), inscribirse a sesiones de ese evento con cupo (`201`), cancelar sus propias inscripciones (`204`), consultar "Mis inscripciones" y el detalle de sus propias inscripciones. No puede inscribir a terceros ni listar las inscripciones de un evento (`403`).        |
| `ORGANIZER` | No puede inscribirse (`403`, `AUTH-BR-12`). Ve y cancela las inscripciones de **sus** eventos; consulta el listado paginado por evento de sus propios eventos y el detalle de cualquiera de ellas. En eventos ajenos recibe `403` en el listado y `404` al operar sobre una inscripción concreta.                                                     |
| `ADMIN`     | No puede inscribirse (`403`, `AUTH-BR-12`). Ve y cancela las inscripciones de **cualquier** evento, consulta el listado por evento de cualquier evento y el detalle de cualquier inscripción, con las mismas reglas de negocio (capacidad, estado del evento y sesión).                                                                                  |

### 4.1. Matriz de permisos (acción × rol)

| Acción                                                          | Anónimo | `ATTENDEE` | `ORGANIZER` (evento propio) | `ORGANIZER` (evento ajeno) | `ADMIN` |
| --------------------------------------------------------------- | :-----: | :--------: | :-------------------------: | :------------------------: | :-----: |
| `POST /api/events/{event_id}/registrations`                     |  `401`  |     ✓      |            `403`            |           `403`            |  `403`  |
| `POST /api/events/{event_id}/sessions/{session_id}/registrations` |  `401`  |     ✓      |            `403`            |           `403`            |  `403`  |
| `DELETE /api/registrations/{id}` (inscripción propia)           |  `401`  |     ✓      |              ✓              |             ✓              |    ✓    |
| `DELETE /api/registrations/{id}` (inscripción de su evento)     |  `401`  |   `404`    |              ✓              |           `404`            |    ✓    |
| `GET /api/registrations/me`                                     |  `401`  |     ✓      |        ✓ (propias)          |       ✓ (propias)          |    ✓    |
| `GET /api/events/{event_id}/registrations`                      |  `401`  |   `403`    |              ✓              |           `403`            |    ✓    |
| `GET /api/registrations/{id}` (propia o de su evento)           |  `401`  |     ✓      |              ✓              |           `404`            |    ✓    |

Notas:

- Un `ORGANIZER` o un `ADMIN` que fue `ATTENDEE` antes de ser promovido conserva sus inscripciones históricas: las ve en `/me` y puede cancelarlas como dueño, pero no puede crear nuevas.
- El listado por evento es un endpoint de gestión: un actor autenticado sin permiso recibe `403` (mismo criterio que las escrituras de `sessions`). El detalle de una inscripción concreta responde `404` para no revelar la existencia de inscripciones ajenas (R5.8).

## 5. Modelo conceptual observable

### 5.1. Entidad `Registration`

| Campo        | Tipo                    | Obligatorio | Reglas                                                                                                                       |
| ------------ | ----------------------- | :---------: | ---------------------------------------------------------------------------------------------------------------------------- |
| `id`         | entero                  |      —      | Clave primaria autoincremental, solo lectura.                                                                                |
| `user_id`    | entero                  |     Sí      | FK a `users.id` (`ON DELETE RESTRICT`). Se toma del token, **nunca** del cuerpo. Inmutable.                                   |
| `event_id`   | entero                  |     Sí      | FK a `events.id` (`ON DELETE CASCADE`). Se toma de la ruta. Inmutable.                                                        |
| `session_id` | entero o `null`         |     No      | FK a `sessions.id` (`ON DELETE CASCADE`, nullable). `null` = inscripción al evento; con valor = inscripción a esa sesión del evento. |
| `status`     | enumerado               |     Sí      | `ACTIVE` o `CANCELLED` (valores en inglés, traducidos solo en la UI). `CHECK` en base de datos.                              |
| `created_at` | fecha y hora UTC        |      —      | Solo lectura, asignada al crear la fila; no cambia al reactivar.                                                              |
| `updated_at` | fecha y hora UTC        |      —      | Solo lectura, se actualiza al reactivar y al cancelar.                                                                        |

Invariantes del modelo:

1. Una fila con `session_id IS NULL` es una inscripción **al evento**; una fila con `session_id` no nulo es una inscripción **a la sesión** y su `event_id` debe coincidir con `session.event_id` (se valida en el servicio, porque un `CHECK` no puede consultar otra tabla).
2. Solo puede existir una fila `ACTIVE` por `(user_id, event_id)` con `session_id IS NULL` y una fila `ACTIVE` por `(user_id, session_id)`.
3. No existe borrado físico de inscripciones desde la API: cancelar cambia `status` a `CANCELLED` y conserva la fila. El borrado físico del **padre** (evento o sesión) sí elimina sus filas por cascada (D15).

### 5.2. `RegistrationRead`

Toda respuesta que devuelve una inscripción (`POST` con `201` o `200`, `GET /api/registrations/{id}` e `items[]` de los dos listados) usa `RegistrationRead`:

| Campo        | Tipo                                | Reglas                                                                                                         |
| ------------ | ----------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| `id`         | entero                              | Identificador de la inscripción.                                                                               |
| `user_id`    | entero                              | Dueño de la inscripción. Es el único dato del usuario que se expone (D13).                                      |
| `event_id`   | entero                              | Evento de la inscripción.                                                                                      |
| `session_id` | entero o `null`                     | Sesión de la inscripción, o `null` si es al evento.                                                            |
| `status`     | enumerado                           | `ACTIVE` o `CANCELLED`.                                                                                        |
| `event`      | `RegistrationEventSummary`          | Resumen descriptivo del evento; **no** incluye cupos (los cupos autoritativos son los de `EventRead`).           |
| `session`    | `RegistrationSessionSummary \| null` | Resumen descriptivo de la sesión, o `null`.                                                                    |
| `created_at` | fecha y hora UTC                    | ISO 8601 terminado en `Z`.                                                                                     |
| `updated_at` | fecha y hora UTC                    | ISO 8601 terminado en `Z`.                                                                                     |

**`RegistrationEventSummary`:** `id`, `title`, `date` (UTC `Z`) y `status` (`DRAFT`, `PUBLISHED`, `CANCELLED`). Se devuelve también cuando el evento ya está `CANCELLED`, porque el dueño de la inscripción debe poder ver a qué evento se inscribió.

**`RegistrationSessionSummary`:** `id`, `title`, `speaker`, `start_time` y `end_time` (UTC `Z`).

`RegistrationRead` **nunca** incluye `full_name`, `email`, `password_hash`, `is_active` ni ningún otro dato personal del usuario (R5.8, D13).

### 5.3. `RegistrationListRead`

| Campo   | Tipo                  | Reglas                                                          |
| ------- | --------------------- | --------------------------------------------------------------- |
| `items` | `RegistrationRead[]`  | Página solicitada.                                              |
| `total` | entero                | Total de filas que cumplen los filtros para el actor.           |
| `page`  | entero                | Página devuelta (1-indexed).                                    |
| `size`  | entero                | Tamaño de página aplicado (por defecto 10, máximo 50).          |
| `pages` | entero                | Número total de páginas (`0` si `total = 0`).                   |

Sigue la convención `PLAT-BR-05`.

### 5.4. `RegistrationCreate`

**No aplica.** Los dos endpoints de alta no reciben cuerpo de petición: `user_id` procede del token y `event_id`/`session_id` de la ruta. Enviar un cuerpo con `user_id`, `event_id`, `session_id`, `status` o campos calculados no altera el resultado, porque el servidor no los lee; la fuente de verdad es siempre el token y la ruta.

## 6. Reglas de negocio

- **REG-BR-01 (Modelo, estados e inmutabilidad):** Cada inscripción vincula un `user_id` (tomado del token) con un `event_id` (tomado de la ruta) y, opcionalmente, con un `session_id`; `status` solo admite `ACTIVE` o `CANCELLED`; `user_id`, `event_id` y `session_id` son inmutables; `created_at` se asigna al crear y `updated_at` cambia al reactivar y al cancelar; no existe borrado físico desde la API (R5.5, R6.1).
- **REG-BR-02 (Unidad evento + sesión):** La inscripción al evento es obligatoria y previa; la inscripción a una sesión es opcional y exige una inscripción `ACTIVE` al evento del usuario; la sesión debe pertenecer al `event_id` de la ruta. Inscribirse a una sesión sin inscripción activa al evento responde `409 "Debes inscribirte primero al evento"` (D1).
- **REG-BR-03 (Capacidad del evento):** `EventRead.registered_count` es el número de inscripciones `ACTIVE` del evento con `session_id IS NULL`, de modo que una persona ocupa exactamente **un cupo** aunque se inscriba a varias sesiones; la inscripción se acepta mientras `registered_count < event.total_capacity` (límite exacto incluido) y se rechaza con `409 "No hay cupos disponibles para este evento"` al superarlo (D2, R2.5, R5.4).
- **REG-BR-04 (Capacidad de la sesión):** `SessionRead.registered_count` es el número de inscripciones `ACTIVE` con ese `session_id`; cada sesión tiene cupo propio e independiente del de evento y de las demás sesiones; se acepta mientras `registered_count < session.capacity` y se rechaza con `409 "No hay cupos disponibles para esta sesión"` al superarlo (D2, R2.5).
- **REG-BR-05 (Concurrencia y transacción):** Toda escritura abre una transacción y bloquea **primero** la fila de `events` con `SELECT ... FOR UPDATE` y **después**, si aplica, la fila de `sessions`, siempre en ese orden, con aislamiento `READ COMMITTED`; la comprobación de capacidad, la de duplicados y la escritura ocurren dentro de esa transacción; las restricciones únicas parciales actúan como red de seguridad; no se usan `advisory locks` (D3, R5.4, R3.6).
- **REG-BR-06 (Duplicados y reactivación):** Solo puede existir una inscripción `ACTIVE` por usuario y evento (filas con `session_id IS NULL`) y por usuario y sesión; si ya existe una `ACTIVE`, el `POST` responde `409` con `"Ya estás inscrito en este evento"` o `"Ya estás inscrito en esta sesión"`; si existe una `CANCELLED`, el `POST` la reactiva reutilizando la misma fila y responde `200`, revalidando el estado del evento, la capacidad y, cuando la fila es de sesión, también la **inscripción `ACTIVE` al evento** del usuario (`409 "Debes inscribirte primero al evento"` si no la tiene) (D4, D14).
- **REG-BR-07 (Estados del evento):** Solo los eventos `PUBLISHED` admiten inscripciones; `DRAFT` y `CANCELLED` responden `404 "Evento no encontrado"` al `ATTENDEE`, sin revelar su existencia; cancelar un evento **no** anula sus inscripciones ni altera sus contadores (D5).
- **REG-BR-08 (Sesiones inscribibles):** Una sesión es inscribible solo si el evento está `PUBLISHED`, la sesión pertenece a ese evento y el usuario tiene inscripción `ACTIVE` al evento; si la sesión no existe o pertenece a otro evento, la respuesta es `404 "Sesión no encontrada"`; no se valida conflicto de horario entre sesiones (D6, fuera de alcance).
- **REG-BR-09 (Cancelación y cascada):** Puede cancelar el `ATTENDEE` dueño, el `ORGANIZER` propietario del evento y el `ADMIN`, sin plazo; la cancelación es lógica, libera el cupo de inmediato y responde `204`; `DELETE` es idempotente (`204` aunque ya estuviera cancelada); al cancelar una inscripción al evento se cancelan en la misma transacción las inscripciones `ACTIVE` de ese usuario a sesiones de ese evento; la cancelación de una inscripción **a sesión** solo libera el cupo de esa sesión y **no** modifica la inscripción al evento ni las demás sesiones (la cascada va solo en sentido evento → sesiones); si la inscripción no existe o no es visible, responde `404 "Inscripción no encontrada"` (D7, D12).
- **REG-BR-10 (RBAC y propiedad):** Crear inscripción es exclusivo del rol `ATTENDEE` (anónimo `401`, `ORGANIZER` y `ADMIN` `403`, según `AUTH-BR-12`/`AUTH-AC-30`); "mis inscripciones" solo devuelve las propias; el listado por evento es del `ORGANIZER` propietario o del `ADMIN`; el detalle es visible para el dueño, el organizador propietario o el `ADMIN`; lo no visible responde `404` en recursos individuales y `403` en el listado de gestión; la cadena de autorización es token (`401`) → rol (`403`) → recurso (`404`) → reglas de negocio (`409`) → schema (`422`) (D8, R5.2, R5.3, R5.8).
- **REG-BR-11 (Consultas y paginación):** `GET /api/registrations/me` devuelve por defecto **todas** las inscripciones del usuario (`ACTIVE` y `CANCELLED`, tanto al evento como a sesiones), paginadas, con filtros opcionales `status` y `event_id` y orden `created_at DESC, id DESC`; `GET /api/events/{event_id}/registrations` devuelve **solo** las inscripciones al evento (filas con `session_id IS NULL`, una por asistente) de ese evento, paginadas con filtro `status` y sin incluir las inscripciones a sesiones; ambas usan `page` (por defecto 1) y `size` (por defecto 10, máximo 50) y devuelven `200` con `items: []` cuando no hay resultados (D9).
- **REG-BR-12 (Caché):** Solo se cachea `GET /api/registrations/me`, por usuario, bajo claves `registrations:me:{user_id}:...` con TTL de 60 segundos; cada alta, reactivación o cancelación invalida el prefijo `registrations:me:{user_id}:` del usuario afectado **y** el prefijo `events:`; los listados por evento no se cachean; Redis es prescindible y su fallo no altera la respuesta (D10, R4.4).
- **REG-BR-13 (Errores, OpenAPI y privacidad):** Todos los errores usan el formato de `platform` con `detail` en español y, en `422`, `detail = "Error de validación en los datos enviados"` más `errors[].message` en español; el código `400` no se usa; las seis operaciones se documentan con tag `registrations` y `error_responses(401, 403, 404, 409, 422)`; ninguna respuesta incluye `full_name`, `email` ni datos personales del usuario; el frontend no usa `v-html` (D13, R5.5, R5.8, R5.9, R6).
- **REG-BR-14 (Integridad referencial y contadores):** `user_id` es `ON DELETE RESTRICT` y `event_id`/`session_id` son `ON DELETE CASCADE` (la segunda nullable), de modo que el borrado físico de un evento o de una sesión elimina por cascada sus inscripciones sin lógica adicional en `events`/`sessions`; los guards existentes siguen devolviendo `409` con inscripciones `ACTIVE` (`EVT-BR-07`/`SES-BR-11`), por lo que la cascada solo alcanza al histórico `CANCELLED`; los hooks `get_registered_count(session, event_id)` y `get_session_registered_count(session, session_id)` pasan a contar filas reales **sin cambiar su firma** (D15, R3.6, R5.4).

## 7. Contrato de API

Todas las rutas cuelgan de `/api`. Los errores siguen el formato de `specs/platform/spec.md`. Todas las fechas se serializan en UTC ISO 8601 con sufijo `Z`. Los ejemplos usan un evento `PUBLISHED` con `id = 5`, `date = "2026-11-15T14:00:00Z"` y `total_capacity = 100`, y una sesión `id = 10` con `capacity = 40`.

### 7.1. `POST /api/events/{event_id}/registrations`

- **Descripción:** Inscribe al usuario autenticado al evento; reactiva su inscripción si estaba cancelada.
- **Autenticación / rol requerido:** `ATTENDEE` (Bearer obligatorio).
- **Parámetros de ruta:** `event_id` entero `>= 1`.
- **Request:** sin cuerpo.

- **Response `201 Created`** (inscripción nueva):

```json
{
  "id": 41,
  "user_id": 7,
  "event_id": 5,
  "session_id": null,
  "status": "ACTIVE",
  "event": {
    "id": 5,
    "title": "Conferencia de Tecnología 2026",
    "date": "2026-11-15T14:00:00Z",
    "status": "PUBLISHED"
  },
  "session": null,
  "created_at": "2026-11-01T10:00:00Z",
  "updated_at": "2026-11-01T10:00:00Z"
}
```

- **Response `200 OK`** (reactivación de una fila `CANCELLED`): mismo esquema, con el mismo `id` de la fila reactivada, `status = "ACTIVE"`, `created_at` sin cambios y `updated_at` posterior.

- **Errores:**

| Código | Cuándo                                                                 | `detail` (español)                                                    |
| ------ | ---------------------------------------------------------------------- | --------------------------------------------------------------------- |
| 400    | No se usa en este dominio                                              | —                                                                     |
| 401    | Token ausente, inválido, expirado o de usuario inactivo                | `"No autenticado o sesión expirada"` (+ `WWW-Authenticate: Bearer`)    |
| 403    | Rol `ORGANIZER` o `ADMIN`                                              | `"No tienes permisos para realizar esta acción"`                      |
| 404    | El evento no existe, está `DRAFT` o está `CANCELLED`                   | `"Evento no encontrado"`                                              |
| 409    | Ya existe una inscripción `ACTIVE` al evento                           | `"Ya estás inscrito en este evento"`                                  |
| 409    | El evento alcanzó `total_capacity` inscripciones activas               | `"No hay cupos disponibles para este evento"`                         |
| 422    | `event_id` no es un entero válido o es menor que 1                     | `"Error de validación en los datos enviados"` + `errors[].message`    |

Precedencia: `401` → `403` → `404` (evento) → `409` duplicado → `409` capacidad → `422`.

### 7.2. `POST /api/events/{event_id}/sessions/{session_id}/registrations`

- **Descripción:** Inscribe al usuario autenticado a una sesión del evento; reactiva su inscripción si estaba cancelada.
- **Autenticación / rol requerido:** `ATTENDEE` (Bearer obligatorio).
- **Parámetros de ruta:** `event_id` y `session_id` enteros `>= 1`.
- **Request:** sin cuerpo.

- **Response `201 Created`** (inscripción nueva) / **`200 OK`** (reactivación):

```json
{
  "id": 42,
  "user_id": 7,
  "event_id": 5,
  "session_id": 10,
  "status": "ACTIVE",
  "event": {
    "id": 5,
    "title": "Conferencia de Tecnología 2026",
    "date": "2026-11-15T14:00:00Z",
    "status": "PUBLISHED"
  },
  "session": {
    "id": 10,
    "title": "Apertura y bienvenida",
    "speaker": "Ana Torres",
    "start_time": "2026-11-15T14:00:00Z",
    "end_time": "2026-11-15T15:00:00Z"
  },
  "created_at": "2026-11-01T10:05:00Z",
  "updated_at": "2026-11-01T10:05:00Z"
}
```

- **Errores:**

| Código | Cuándo                                                                     | `detail` (español)                                                 |
| ------ | -------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| 400    | No se usa                                                                  | —                                                                  |
| 401    | Token ausente, inválido, expirado o de usuario inactivo                    | `"No autenticado o sesión expirada"` (+ `WWW-Authenticate: Bearer`) |
| 403    | Rol `ORGANIZER` o `ADMIN`                                                  | `"No tienes permisos para realizar esta acción"`                   |
| 404    | El evento no existe, está `DRAFT` o está `CANCELLED`                       | `"Evento no encontrado"`                                           |
| 404    | La sesión no existe o no pertenece al `event_id` de la ruta                | `"Sesión no encontrada"`                                           |
| 409    | El usuario no tiene inscripción `ACTIVE` al evento                         | `"Debes inscribirte primero al evento"`                            |
| 409    | Ya existe una inscripción `ACTIVE` a esa sesión                            | `"Ya estás inscrito en esta sesión"`                               |
| 409    | La sesión alcanzó `capacity` inscripciones activas                         | `"No hay cupos disponibles para esta sesión"`                      |
| 422    | `event_id` o `session_id` no son enteros válidos o son menores que 1       | `"Error de validación en los datos enviados"` + `errors[].message` |

Precedencia: `401` → `403` → `404` (evento) → `404` (sesión) → `409` inscripción previa al evento → `409` duplicado → `409` capacidad → `422`.

### 7.3. `DELETE /api/registrations/{id}`

- **Descripción:** Cancela lógicamente una inscripción, libera su cupo y, si es la inscripción al evento, cancela en cascada las inscripciones activas del mismo usuario a sesiones de ese evento.
- **Autenticación / rol requerido:** dueño de la inscripción, `ORGANIZER` propietario del evento o `ADMIN`.
- **Parámetros de ruta:** `id` entero `>= 1`.
- **Response `204 No Content`:** sin cuerpo. Idempotente: repetir sobre una inscripción ya cancelada vuelve a responder `204`.

- **Errores:**

| Código | Cuándo                                                              | `detail` (español)                                                 |
| ------ | ------------------------------------------------------------------- | ------------------------------------------------------------------ |
| 400    | No se usa                                                           | —                                                                  |
| 401    | Token ausente, inválido, expirado o de usuario inactivo             | `"No autenticado o sesión expirada"` (+ `WWW-Authenticate: Bearer`) |
| 403    | No se usa (reservado al contrato OpenAPI)                           | `"No tienes permisos para realizar esta acción"`                   |
| 404    | La inscripción no existe o no es visible para el actor              | `"Inscripción no encontrada"`                                      |
| 409    | No se usa (la cancelación nunca entra en conflicto)                 | —                                                                  |
| 422    | `id` no es un entero válido o es menor que 1                        | `"Error de validación en los datos enviados"` + `errors[].message` |

### 7.4. `GET /api/registrations/me`

- **Descripción:** Lista las inscripciones del usuario autenticado, activas y canceladas.
- **Autenticación / rol requerido:** cualquier usuario autenticado (`ATTENDEE`, `ORGANIZER`, `ADMIN`), siempre sobre sus propias filas.
- **Parámetros de consulta:** `page` (entero `>= 1`, por defecto `1`), `size` (entero `1..50`, por defecto `10`), `status` (`ACTIVE` o `CANCELLED`, opcional), `event_id` (entero `>= 1`, opcional).

- **Response `200 OK`:**

```json
{
  "items": [
    {
      "id": 42,
      "user_id": 7,
      "event_id": 5,
      "session_id": 10,
      "status": "ACTIVE",
      "event": {
        "id": 5,
        "title": "Conferencia de Tecnología 2026",
        "date": "2026-11-15T14:00:00Z",
        "status": "PUBLISHED"
      },
      "session": {
        "id": 10,
        "title": "Apertura y bienvenida",
        "speaker": "Ana Torres",
        "start_time": "2026-11-15T14:00:00Z",
        "end_time": "2026-11-15T15:00:00Z"
      },
      "created_at": "2026-11-01T10:05:00Z",
      "updated_at": "2026-11-01T10:05:00Z"
    },
    {
      "id": 41,
      "user_id": 7,
      "event_id": 5,
      "session_id": null,
      "status": "ACTIVE",
      "event": {
        "id": 5,
        "title": "Conferencia de Tecnología 2026",
        "date": "2026-11-15T14:00:00Z",
        "status": "PUBLISHED"
      },
      "session": null,
      "created_at": "2026-11-01T10:00:00Z",
      "updated_at": "2026-11-01T10:00:00Z"
    }
  ],
  "total": 2,
  "page": 1,
  "size": 10,
  "pages": 1
}
```

- **Errores:**

| Código | Cuándo                                                                    | `detail` (español)                                                 |
| ------ | ------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| 400    | No se usa                                                                 | —                                                                  |
| 401    | Token ausente, inválido, expirado o de usuario inactivo                   | `"No autenticado o sesión expirada"` (+ `WWW-Authenticate: Bearer`) |
| 403    | No se usa                                                                 | —                                                                  |
| 404    | No se usa                                                                 | —                                                                  |
| 409    | No se usa                                                                 | —                                                                  |
| 422    | `page`/`size`/`event_id` fuera de rango o `status` con un valor no válido | `"Error de validación en los datos enviados"` + `errors[].message` |

Sin inscripciones, o con un `event_id` que no corresponde a ninguna inscripción propia, la respuesta es `200` con `items: []`, `total: 0`, `pages: 0`.

### 7.5. `GET /api/events/{event_id}/registrations`

- **Descripción:** Lista las inscripciones **al evento** (filas con `session_id IS NULL`, una por asistente) para su organizador propietario o un administrador; no incluye las inscripciones a sesiones.
- **Autenticación / rol requerido:** `ORGANIZER` propietario del evento o `ADMIN`.
- **Parámetros de ruta:** `event_id` entero `>= 1`.
- **Parámetros de consulta:** `page`, `size`, `status` (`ACTIVE` o `CANCELLED`, opcional).

- **Response `200 OK`:** `RegistrationListRead` con las inscripciones al evento ordenadas por `created_at DESC, id DESC`; `total` cuenta solo esas filas. Cada elemento expone `user_id`, `status` y fechas; nunca `full_name` ni `email`. Las inscripciones a sesiones se consultan por `/api/registrations/me` o por `/api/registrations/{id}`.

- **Errores:**

| Código | Cuándo                                                                    | `detail` (español)                                                 |
| ------ | ------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| 400    | No se usa                                                                 | —                                                                  |
| 401    | Token ausente, inválido, expirado o de usuario inactivo                   | `"No autenticado o sesión expirada"` (+ `WWW-Authenticate: Bearer`) |
| 403    | Rol `ATTENDEE` u `ORGANIZER` ajeno al evento                              | `"No tienes permisos para realizar esta acción"`                   |
| 404    | El evento no existe                                                       | `"Evento no encontrado"`                                           |
| 409    | No se usa                                                                 | —                                                                  |
| 422    | `event_id`, `page`, `size` o `status` inválidos                           | `"Error de validación en los datos enviados"` + `errors[].message` |

### 7.6. `GET /api/registrations/{id}`

- **Descripción:** Devuelve el detalle de una inscripción visible para el actor.
- **Autenticación / rol requerido:** dueño, `ORGANIZER` propietario del evento o `ADMIN`.
- **Parámetros de ruta:** `id` entero `>= 1`.
- **Response `200 OK`:** `RegistrationRead`.

- **Errores:**

| Código | Cuándo                                                       | `detail` (español)                                                 |
| ------ | ------------------------------------------------------------ | ------------------------------------------------------------------ |
| 400    | No se usa                                                    | —                                                                  |
| 401    | Token ausente, inválido, expirado o de usuario inactivo      | `"No autenticado o sesión expirada"` (+ `WWW-Authenticate: Bearer`) |
| 403    | No se usa (lo no visible responde `404`)                     | —                                                                  |
| 404    | La inscripción no existe o no es visible para el actor        | `"Inscripción no encontrada"`                                      |
| 409    | No se usa                                                    | —                                                                  |
| 422    | `id` no es un entero válido o es menor que 1                 | `"Error de validación en los datos enviados"` + `errors[].message` |

## 8. Reglas de concurrencia y transacción

1. **Orden de bloqueo obligatorio:** `events` primero, `sessions` después. Nunca al revés, para no invertir el orden que ya usan las escrituras de `sessions` (`SES-BR-08`) y provocar interbloqueos.
2. **Qué bloquea cada operación:**
   - Alta al evento: `SELECT ... FOR UPDATE` sobre la fila de `events`.
   - Alta a sesión: `SELECT ... FOR UPDATE` sobre `events` y después sobre `sessions`.
   - Cancelación de una inscripción al evento: `FOR UPDATE` sobre `events` (la cascada solo reduce contadores de sesiones, no requiere bloquear cada sesión).
   - Cancelación de una inscripción a sesión: `FOR UPDATE` sobre `events` y sobre `sessions`.
   - Reactivación: mismos bloqueos que el alta correspondiente.
3. **Aislamiento:** `READ COMMITTED` (valor por defecto de PostgreSQL). El bloqueo de la fila del evento actúa como mutex lógico: la segunda transacción espera y, al continuar, ve las filas confirmadas por la primera.
4. **Dentro de la transacción** se ejecutan, en este orden: comprobación de estado del evento, pertenencia de la sesión, inscripción previa al evento, duplicados, capacidad y escritura. Cualquier fallo hace `rollback` explícito antes de propagar el error.
5. **Red de seguridad:** los índices únicos parciales impiden duplicados activos incluso si una ruta futura omitiera la comprobación previa; una violación de unicidad se traduce en el `409` de duplicado, nunca en `500`.
6. **Sin `advisory locks`:** se descartan porque el bloqueo de fila del evento ya serializa y no introduce una convención global de claves (D3).
7. **Invariante de cupo:** `registered_count <= capacidad` se mantiene en todo momento porque la comprobación y la inserción son atómicas. La reducción de `event.total_capacity` por debajo de los inscritos ya está bloqueada en `events` (`EVT-BR-04`) y la de `session.capacity` en `sessions` (`SES-BR-09`).
8. **Cancelación concurrente con un alta:** el `DELETE` toma el mismo bloqueo, de modo que el alta posterior ve el cupo liberado y la cancelación posterior ve la fila recién creada.

## 9. Reglas de capacidad y contadores

1. **Cupo del evento:** `registered_count(evento) = COUNT(*)` de `registrations` con `event_id = :id`, `session_id IS NULL` y `status = 'ACTIVE'`.
2. **Cupo de la sesión:** `registered_count(sesión) = COUNT(*)` de `registrations` con `session_id = :id` y `status = 'ACTIVE'`.
3. **Una persona, un cupo de evento:** inscribirse a tres sesiones no incrementa el contador del evento; solo lo hace la fila con `session_id IS NULL`.
4. **Cupos independientes por sesión:** dos sesiones del mismo evento tienen contadores propios; llenar una no afecta a las demás.
5. **Límite exacto:** con `total_capacity = N` y `N-1` inscripciones activas, la inscripción número `N` se acepta (`201`). Lo mismo con `session.capacity`.
6. **Cálculo en el backend:** `available_capacity = max(0, capacidad - registered_count)` se calcula en el servidor; el frontend consume el valor y nunca lo recalcula (R2.5).
7. **Hooks:** `get_registered_count(session, event_id)` en `app/events/service.py` y `get_session_registered_count(session, session_id)` en `app/sessions/service.py` mantienen nombre y firma y pasan a ejecutar el `COUNT(*)` descrito; siguen siendo monkeypatcheables en las pruebas existentes.
8. **Cancelar libera de inmediato:** el contador se recalcula en la siguiente lectura; no hay cupos reservados ni temporales.
9. **Histórico cancelado no ocupa cupo:** las filas `CANCELLED` no cuentan en ningún contador.

## 10. Reglas de consulta, paginación y caché

1. **Orden:** `created_at DESC, id DESC` en ambos listados; `id` desempata marcas de tiempo iguales y hace el resultado determinista (R3.7).
2. **Paginación:** `page` por defecto `1` (`>= 1`) y `size` por defecto `10` (`1..50`), con sobre `{ items, total, page, size, pages }` y `pages = ceil(total / size)` (`0` si `total = 0`).
3. **Filtros:** `/me` admite `status` y `event_id`; el listado por evento admite `status`. Un `status` fuera de `ACTIVE`/`CANCELLED` responde `422`.
4. **Ámbito:** `/me` filtra siempre por el `user_id` del token; el listado por evento filtra por el `event_id` de la ruta y por la propiedad del evento.
5. **Caché de `/me`:** clave `registrations:me:{user_id}:page={page}:size={size}:status={status}:event={event_id}`, TTL 60 s (`settings.cache_events_ttl_seconds`, sin variable de entorno nueva). El `user_id` en la clave impide fugas entre usuarios (R5.8).
6. **Invalidación:** toda alta, reactivación o cancelación invalida `registrations:me:{user_id}:` del usuario afectado (el dueño de la inscripción, aunque quien cancele sea el organizador o el `ADMIN`) y el prefijo `events:` completo, porque `EventRead`/`SessionRead` exponen contadores.
7. **Sin caché por evento:** el listado por evento y el detalle no se cachean; son datos de gestión y deben reflejar el estado inmediato.
8. **Redis prescindible:** un fallo de lectura, escritura o invalidación se registra como `warning` en inglés y la petición continúa contra PostgreSQL (R4.4).

## 11. Casos límite

- **Evento inexistente:** `404 "Evento no encontrado"` en las dos altas, después de validar token y rol.
- **Evento `DRAFT` o `CANCELLED`:** `404 "Evento no encontrado"` para el `ATTENDEE` en las dos altas; no se revela su existencia (R5.8).
- **Evento cancelado con inscripciones:** las inscripciones permanecen `ACTIVE` y visibles en `/me`; los contadores no cambian (D5).
- **Evento lleno:** `409 "No hay cupos disponibles para este evento"`, también en el intento de reactivación.
- **Límite exacto:** la última inscripción permitida responde `201`; la siguiente responde `409`.
- **Duplicado activo:** `409 "Ya estás inscrito en este evento"` / `"Ya estás inscrito en esta sesión"`; no se crean filas nuevas.
- **Reactivación:** `200`, mismo `id`, `created_at` intacto, `updated_at` nuevo, cupo revalidado.
- **Reactivación de una inscripción a sesión sin inscripción activa al evento:** `409 "Debes inscribirte primero al evento"` y la fila sigue `CANCELLED`.
- **Reactivación imposible por estado:** `404 "Evento no encontrado"` y la fila sigue `CANCELLED`.
- **Sesión de otro evento:** `404 "Sesión no encontrada"`; nunca se opera sobre ella.
- **Sesión sin inscripción previa al evento:** `409 "Debes inscribirte primero al evento"`.
- **Sesión llena:** `409 "No hay cupos disponibles para esta sesión"`; el cupo del evento no se ve afectado.
- **Sesión cancelada o inexistente:** `404 "Sesión no encontrada"`.
- **Inscripción a sesiones simultáneas:** permitida; no se valida conflicto de horario (fuera de alcance, §2.2).
- **Cancelar dos veces:** `204` ambas veces; la segunda no altera `updated_at`.
- **Cancelar la inscripción al evento con sesiones activas:** las sesiones de ese usuario y evento quedan `CANCELLED` en la misma transacción.
- **Cancelar una inscripción a sesión:** no afecta a la inscripción al evento ni a otras sesiones.
- **Cancelar inscripción inexistente o ajena:** `404 "Inscripción no encontrada"`; no se distingue entre inexistente y no visible.
- **Concurrencia en el último cupo:** una petición `201`, la otra `409`, exactamente `total_capacity` (o `capacity`) filas activas.
- **Concurrencia de dos reactivaciones de la misma fila:** una `200` y la otra `409 "Ya estás inscrito…"`; el índice único parcial actúa como red de seguridad.
- **Cancelación concurrente con un alta:** el resultado final es coherente con el orden de los bloqueos; nunca hay más inscripciones activas que cupos.
- **`/me` vacío:** `200` con `items: []`, `total: 0`, `pages: 0`.
- **`/me` con `event_id` sin inscripciones:** `200` con `items: []`.
- **`/me` con `page` más allá del total:** `200` con `items: []` y el `total` real.
- **`status` inválido:** `422` con `errors[].message` en español.
- **Listado por evento vacío:** `200` con `items: []`, `total: 0` y `pages: 0`; un evento con asistentes inscritos solo a sesiones también devuelve `items: []`, porque el listado solo incluye inscripciones al evento.
- **`ATTENDEE` listando por evento:** `403 "No tienes permisos para realizar esta acción"`.
- **`ORGANIZER` ajeno listando por evento:** `403`; si el evento no existe, `404`.
- **Usuario promovido de `ATTENDEE` a `ORGANIZER`:** conserva sus inscripciones, las ve en `/me` y puede cancelarlas, pero no puede crear nuevas (`403`).
- **Borrado de evento o sesión sin inscripciones activas:** las FKs `ON DELETE CASCADE` eliminan por cascada las inscripciones de ese evento o sesión (incluido el histórico `CANCELLED`) y el `DELETE` sigue respondiendo `204`; con inscripciones `ACTIVE` los guards de `events`/`sessions` siguen respondiendo `409` según `EVT-BR-07`/`SES-BR-11`.
- **Redis caído:** `/me` responde desde PostgreSQL y las escrituras se completan.

## 12. Seguridad y privacidad

- **Cadena única de dependencias (R5.2):** token presente → firma → expiración → usuario existente → usuario activo → rol → propiedad → existencia del recurso. El primer fallo corta la petición.
- **Autorización en servidor (R5.3):** la UI oculta controles, pero el backend verifica rol y propiedad en cada operación. Guards y botones de Vue son ayudas de UX (R2.5).
- **No enumeración (R5.8):** una inscripción ajena responde `404 "Inscripción no encontrada"`; un evento no publicado responde `404 "Evento no encontrado"` al `ATTENDEE`.
- **Privacidad del listado por evento (D13):** expone `user_id`, `status` y fechas; **nunca** `full_name`, `email`, `password_hash` ni `is_active`. Solo el `ADMIN` ve perfiles ajenos, y por los endpoints de `auth`.
- **Caché sin fugas:** la clave incluye `user_id`, de modo que `/me` nunca devuelve la caché de otro usuario.
- **Errores sin trazas:** mensajes en español, sin SQL, rutas de archivos, nombres de tablas ni trazas.
- **XSS (R5.9):** los títulos de evento y sesión se interpolan con `{{ ... }}`; prohibido `v-html`.
- **Secretos (R5.7):** esta spec no contiene credenciales ni datos personales.
- **Integridad transaccional (R5.4):** bloqueo `FOR UPDATE` en el orden `events` → `sessions` más restricciones únicas parciales.

## 13. Criterios de aceptación (EARS)

Cada criterio tiene al menos un test cuyo nombre incluye su ID (R1.5, R1.9). Se usan las cinco formas de EARS: ubicuo, por evento, por estado, no deseado y opcional.

| ID            | Criterio (notación EARS en español)                                                                                                                                                                                                                                                                                                                                                                                                                    | Reglas                                  |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------- |
| **REG-AC-01** | Cuando un `ATTENDEE` autenticado envía `POST /api/events/{event_id}/registrations` sobre un evento `PUBLISHED` con cupo disponible y sin inscripción activa previa, el sistema debe crear una fila con `user_id` del token, `event_id` de la ruta, `session_id = null`, `status = "ACTIVE"` y `created_at`/`updated_at` en UTC, responder `201` con `RegistrationRead` e incrementar en uno el `registered_count` del evento.                                | REG-BR-01, REG-BR-03                     |
| **REG-AC-02** | Mientras el evento tenga `total_capacity = N` e inscripciones activas `N-1`, el sistema debe aceptar la inscripción número `N` y responder `201`.                                                                                                                                                                                                                                                                                                        | REG-BR-03                               |
| **REG-AC-03** | Si el evento ya tiene `total_capacity` inscripciones activas, entonces el sistema debe responder `409` con `detail = "No hay cupos disponibles para este evento"` sin crear ni reactivar ninguna fila y sin alterar `registered_count`.                                                                                                                                                                                                                  | REG-BR-03                               |
| **REG-AC-04** | Mientras dos conexiones independientes contra PostgreSQL compiten por el último cupo del mismo evento, el sistema debe serializar las altas con `SELECT ... FOR UPDATE` sobre `events`, permitir un único `201`, responder `409` a la otra y dejar exactamente `total_capacity` filas activas.                                                                                                                                                             | REG-BR-03, REG-BR-05                     |
| **REG-AC-05** | Si el usuario ya tiene una inscripción `ACTIVE` al evento, entonces el sistema debe responder `409` con `detail = "Ya estás inscrito en este evento"` sin crear filas duplicadas.                                                                                                                                                                                                                                                                        | REG-BR-06                               |
| **REG-AC-06** | Cuando el usuario tiene una inscripción `CANCELLED` al evento y vuelve a enviar `POST /api/events/{event_id}/registrations` con cupo disponible y evento `PUBLISHED`, el sistema debe reactivar la misma fila (`status = "ACTIVE"`, `updated_at` actualizado), responder `200` con `RegistrationRead` e incrementar el `registered_count` en uno.                                                                                                          | REG-BR-06                               |
| **REG-AC-07** | Si la reactivación solicitada no encuentra cupo disponible, entonces el sistema debe responder `409` con `"No hay cupos disponibles para este evento"` y mantener la fila en `CANCELLED`.                                                                                                                                                                                                                                                                | REG-BR-06                               |
| **REG-AC-08** | Si el usuario intenta reactivar su inscripción a un evento que ya no está `PUBLISHED`, entonces el sistema debe responder `404 "Evento no encontrado"` y mantener la fila en `CANCELLED`.                                                                                                                                                                                                                                                               | REG-BR-06, REG-BR-07                     |
| **REG-AC-09** | Mientras el evento esté en `DRAFT` o `CANCELLED`, el sistema debe responder `404 "Evento no encontrado"` a cualquier intento de inscripción de un `ATTENDEE`, sin revelar la existencia del evento y sin crear filas.                                                                                                                                                                                                                                    | REG-BR-07                               |
| **REG-AC-10** | Cuando un evento pasa a `CANCELLED`, el sistema debe conservar intactas las inscripciones existentes (estado, fechas y contadores), de modo que cancelar el evento no cancele inscripciones.                                                                                                                                                                                                                                                             | REG-BR-07                               |
| **REG-AC-11** | Si la petición de alta carece de token válido, entonces el sistema debe responder `401` con `"No autenticado o sesión expirada"` y `WWW-Authenticate: Bearer`; si proviene de un `ORGANIZER` o un `ADMIN`, debe responder `403` con `"No tienes permisos para realizar esta acción"`.                                                                                                                                                                     | REG-BR-10                               |
| **REG-AC-12** | Cuando un `ATTENDEE` con inscripción `ACTIVE` al evento envía `POST /api/events/{event_id}/sessions/{session_id}/registrations` sobre una sesión del evento con cupo, el sistema debe crear una fila con `event_id`, `session_id`, `status = "ACTIVE"`, responder `201` con `RegistrationRead` y mantener sin cambios el `registered_count` del evento.                                                                                                    | REG-BR-02, REG-BR-04                     |
| **REG-AC-13** | Si el usuario no tiene inscripción `ACTIVE` al evento (no existe o está `CANCELLED`), entonces la inscripción a una sesión debe responder `409` con `detail = "Debes inscribirte primero al evento"` sin crear filas.                                                                                                                                                                                                                                    | REG-BR-02, REG-BR-08                     |
| **REG-AC-14** | Si la sesión indicada no existe o no pertenece al `event_id` de la ruta, entonces el sistema debe responder `404 "Sesión no encontrada"` sin crear filas.                                                                                                                                                                                                                                                                                                | REG-BR-08, REG-BR-02                     |
| **REG-AC-15** | Mientras una sesión tenga `capacity = M` e inscripciones activas `M-1`, el sistema debe aceptar la inscripción número `M` con `201`; si ya tiene `M`, debe responder `409` con `"No hay cupos disponibles para esta sesión"`.                                                                                                                                                                                                                            | REG-BR-04                               |
| **REG-AC-16** | Mientras dos conexiones independientes compiten por el último cupo de una misma sesión, el sistema debe serializar las altas bloqueando primero `events` y después `sessions`, permitir un único `201`, responder `409` a la otra y dejar exactamente `capacity` filas activas.                                                                                                                                                                          | REG-BR-04, REG-BR-05                     |
| **REG-AC-17** | Si el usuario ya tiene una inscripción `ACTIVE` a la sesión, el sistema debe responder `409 "Ya estás inscrito en esta sesión"`; si la tenía `CANCELLED` y hay cupo, debe reactivarla y responder `200`, pero solo si mantiene una inscripción `ACTIVE` al evento: sin ella debe responder `409 "Debes inscribirte primero al evento"` y dejar la fila en `CANCELLED`.                                                                                                                                  | REG-BR-06, REG-BR-08                     |
| **REG-AC-18** | Cuando el `ATTENDEE` dueño, el `ORGANIZER` propietario del evento o un `ADMIN` envía `DELETE /api/registrations/{id}` sobre una inscripción `ACTIVE`, el sistema debe marcarla `CANCELLED`, actualizar `updated_at`, liberar el cupo de inmediato y responder `204` sin cuerpo, conservando la fila; si la inscripción era **a una sesión**, solo debe liberar el cupo de esa sesión y dejar intactas la inscripción al evento y las demás sesiones del usuario.                                                                                                                                                     | REG-BR-09                               |
| **REG-AC-19** | Si se repite `DELETE` sobre una inscripción ya `CANCELLED`, entonces el sistema debe responder `204` sin modificar la fila ni los contadores.                                                                                                                                                                                                                                                                                                            | REG-BR-09                               |
| **REG-AC-20** | Cuando se cancela una inscripción al evento, el sistema debe cancelar en la misma transacción todas las inscripciones `ACTIVE` de ese usuario a sesiones de ese evento, de modo que los contadores de cada sesión y del evento reflejen la liberación.                                                                                                                                                                                                     | REG-BR-09                               |
| **REG-AC-21** | Si se intenta cancelar una inscripción inexistente o no visible para el actor, entonces el sistema debe responder `404 "Inscripción no encontrada"` sin modificar filas; un `ORGANIZER` ajeno y un `ATTENDEE` ajeno reciben `404`, nunca `403`.                                                                                                                                                                                                          | REG-BR-09, REG-BR-10                     |
| **REG-AC-22** | Cuando un usuario autenticado consulta `GET /api/registrations/me`, el sistema debe devolver `200` con el sobre `{ items, total, page, size, pages }`, todas sus inscripciones (`ACTIVE` y `CANCELLED`, al evento y a sesiones) ordenadas por `created_at DESC, id DESC`, paginadas con `page` (por defecto 1) y `size` (por defecto 10, máximo 50), e `items: []` cuando no tenga ninguna.                                                                                        | REG-BR-11                               |
| **REG-AC-23** | Cuando `GET /api/registrations/me` recibe `status` o `event_id`, el sistema debe filtrar por ellos; si `status` no es `ACTIVE`/`CANCELLED` o `event_id`/`page`/`size` son inválidos, debe responder `422` con `detail = "Error de validación en los datos enviados"` y `errors[].message` en español.                                                                                                                                                    | REG-BR-11                               |
| **REG-AC-24** | El sistema debe limitar `GET /api/registrations/me` a las inscripciones cuyo `user_id` coincide con el del token, sin aceptar ningún parámetro que permita consultar las de otro usuario.                                                                                                                                                                                                                                                                | REG-BR-10, REG-BR-11                     |
| **REG-AC-25** | Cuando el `ORGANIZER` propietario o un `ADMIN` consulta `GET /api/events/{event_id}/registrations`, el sistema debe devolver `200` con el sobre paginado de las inscripciones **al evento** (`session_id IS NULL`, una por asistente), filtrable por `status`, con `total` contando solo esas filas y exponiendo `user_id`, `status` y fechas, y nunca `full_name`, `email` ni otros datos personales del usuario.                                                                                                                                                           | REG-BR-10, REG-BR-11, REG-BR-13          |
| **REG-AC-26** | Si un `ATTENDEE` o un `ORGANIZER` ajeno solicita el listado por evento, el sistema debe responder `403 "No tienes permisos para realizar esta acción"`; si el evento no existe, `404 "Evento no encontrado"`; si no tiene inscripciones al evento (aunque tenga inscripciones a sesiones), `200` con `items: []` y `total: 0`.                                                                                                                                                                                           | REG-BR-10, REG-BR-11                     |
| **REG-AC-27** | Cuando se consulta `GET /api/registrations/{id}` con un actor que es el dueño, el `ORGANIZER` propietario del evento o un `ADMIN`, el sistema debe responder `200` con `RegistrationRead`; en cualquier otro caso debe responder `404 "Inscripción no encontrada"`.                                                                                                                                                                                        | REG-BR-10                               |
| **REG-AC-28** | El sistema debe cachear únicamente `GET /api/registrations/me` bajo claves `registrations:me:{user_id}:...` con TTL de 60 segundos, aisladas por usuario, e invalidar el prefijo `registrations:me:{user_id}:` del usuario afectado y el prefijo `events:` en cada alta, reactivación y cancelación.                                                                                                                                                       | REG-BR-12                               |
| **REG-AC-29** | Si Redis no está disponible, entonces el sistema debe servir `GET /api/registrations/me` desde PostgreSQL y completar las altas y cancelaciones sin propagar error al cliente.                                                                                                                                                                                                                                                                          | REG-BR-12                               |
| **REG-AC-30** | El sistema debe usar el formato de error de `platform` con `detail` en español para `401`, `403`, `404` y `409`, y `detail = "Error de validación en los datos enviados"` más `errors: [{field, message}]` en español para `422`; el código `400` no debe usarse en este dominio.                                                                                                                                                                          | REG-BR-13                               |
| **REG-AC-31** | El sistema debe exponer en `/api/openapi.json` las seis operaciones del dominio con tag `registrations`, los esquemas `RegistrationRead` y `RegistrationListRead`, y los códigos `401`, `403`, `404`, `409` y `422` declarados en cada operación, sin declarar `400`.                                                                                                                                                                                       | REG-BR-13                               |
| **REG-AC-32** | El sistema debe crear la tabla `registrations` con la migración `0005_create_registrations` (`down_revision = "0004_create_sessions"`), con PK, FK `user_id → users.id` (`ON DELETE RESTRICT`), FKs `event_id → events.id` y `session_id → sessions.id` (`ON DELETE CASCADE`, la última nullable), `CHECK (status IN ('ACTIVE','CANCELLED'))`, índices únicos parciales por usuario/evento activo y usuario/sesión activa, e índices `(event_id, status)`, `(session_id, status)` y `(user_id, status, created_at)`. | REG-BR-01, REG-BR-14                     |
| **REG-AC-33** | El sistema debe calcular `EventRead.registered_count` como el número de inscripciones `ACTIVE` con `session_id IS NULL` del evento y `SessionRead.registered_count` como el número de inscripciones `ACTIVE` de la sesión, manteniendo las firmas `get_registered_count(session, event_id)` y `get_session_registered_count(session, session_id)` y reflejando `available_capacity = max(0, capacidad - registered_count)`.                                  | REG-BR-03, REG-BR-04, REG-BR-14          |
| **REG-AC-34** | Cuando `events` o `sessions` eliminan físicamente un evento o una sesión sin inscripciones `ACTIVE`, el sistema debe eliminar sus inscripciones por la cascada de las FKs `ON DELETE CASCADE`, responder `204` y no dejar filas huérfanas, sin purga adicional en `delete_event`/`delete_session`; si existe alguna inscripción `ACTIVE`, el borrado debe seguir respondiendo `409` con el mensaje de `EVT-BR-07`/`SES-BR-11`.                                                                                                                  | REG-BR-14                               |
| **REG-AC-35** | Cuando el frontend invoca las acciones de `useRegistrationStore`, el store debe consumir `/api/registrations/me`, `/api/events/{event_id}/registrations` y `/api/registrations/{id}` con los DTOs de `types/api.ts` alineados con `RegistrationRead`/`RegistrationListRead`, y `ProfileView.vue` debe mostrar la sección «Mis inscripciones» paginada y filtrable con estados de carga, vacío y error en español, sin recalcular cupos ni usar `v-html`.     | REG-BR-11, REG-BR-13                     |
| **REG-AC-36** | Donde el usuario sea `ATTENDEE` y el evento esté `PUBLISHED`, `EventDetailView.vue` debe mostrar el botón «Inscribirme» habilitado solo si `available_capacity > 0`, deshabilitado con aviso en español si es `0`, mostrar el `detail` de los `409` y refrescar los contadores desde la API tras el alta; a `ORGANIZER` y `ADMIN` no debe mostrarles el control.                                                                                          | REG-BR-03, REG-BR-07, REG-BR-10          |
| **REG-AC-37** | Donde el usuario sea `ATTENDEE` con inscripción activa al evento, el detalle debe permitir inscribirse a cada sesión con cupo disponible y mostrar «Debes inscribirte primero al evento» cuando no la tenga; con `available_capacity` de la sesión igual a `0` el control debe deshabilitarse con aviso, sin calcular cupos en el cliente.                                                                                                               | REG-BR-02, REG-BR-04, REG-BR-08          |
| **REG-AC-38** | Donde el actor sea el `ORGANIZER` propietario o un `ADMIN`, `EventDetailView.vue` debe cargar de forma diferida un listado paginado de las inscripciones del evento con `user_id`, estado y fechas, filtro por estado y estados de carga/error en español, sin mostrar `full_name` ni `email`.                                                                                                                                                             | REG-BR-10, REG-BR-11, REG-BR-13          |

## 14. Decisiones adoptadas y descartadas

Todas las decisiones D1–D14 fueron consultadas y aprobadas por el usuario el **2026-11-01**. Las D15–D16 son derivadas de la auditoría de esta spec y no reabren ninguna decisión aprobada.

| ID  | Pregunta / decisión                                  | Resolución adoptada                                                                                                                                                                                                                                   | Motivo / alternativas descartadas                                                                                     |
| --- | ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------- |
| D1  | Unidad de inscripción                                | Inscripción al **evento obligatoria** y a **sesiones opcional**; inscribirse a una sesión exige inscripción activa al evento (`409 "Debes inscribirte primero al evento"`).                                                                            | Modelo natural de la arquitectura v1.1 §3.4 y del requisito "registrarse a un evento". Descartado: sesiones independientes sin evento. |
| D2  | Consumo de cupos                                     | Una persona ocupa **1 cupo de evento** aunque se inscriba a varias sesiones; cada sesión tiene **cupo propio**; ambos límites se validan en la misma transacción; límite exacto permitido (`201`), superarlo `409`.                                     | Evita doble conteo y sobreventa. Descartado: contar cada inscripción a sesión como cupo de evento.                       |
| D3  | Concurrencia                                         | Bloquear **primero `events`** con `SELECT ... FOR UPDATE` y después `sessions`; `READ COMMITTED`; índices únicos como red de seguridad; **sin `advisory locks`**.                                                                                       | Orden idéntico al de `sessions` (evita interbloqueos) y sin convención global de claves.                                |
| D4  | Duplicados y reactivación                            | Una sola inscripción `ACTIVE` por usuario/evento (`session_id IS NULL`) y por usuario/sesión; si existe `CANCELLED`, el `POST` la **reactiva** y responde `200`; duplicado activo `409`.                                                              | Aprovecha el histórico y evita filas duplicadas. Descartado: `409` también en la reactivación y borrado físico.          |
| D5  | Estados del evento                                   | Solo `PUBLISHED` admite inscripción; cancelar el evento **no** anula inscripciones; `DRAFT`/`CANCELLED` → `404 "Evento no encontrado"` para el `ATTENDEE`.                                                                                            | Coherente con `EVT-BR-01`/`EVT-BR-03` y con R5.8 (no enumerar borradores).                                              |
| D6  | Sesiones                                             | Sesión inscribible solo si el evento está `PUBLISHED` y el usuario tiene inscripción activa al evento; sesión llena `409`; **sin** validación de conflicto de horario.                                                                                  | El requisito no pide agenda personal; validar solapes exigiría reglas nuevas no aprobadas.                              |
| D7  | Cancelación                                          | Cancela el `ATTENDEE` dueño, el `ORGANIZER` dueño del evento y el `ADMIN`; **sin plazo**; libera cupo de inmediato; `DELETE` **idempotente** (`204`); `404 "Inscripción no encontrada"` si no existe o no es visible.                                    | Requisito implícito de "gestión de asistentes". Descartado: ventana de cancelación y borrado físico.                     |
| D8  | Roles                                                | Crear solo `ATTENDEE` (`401` anónimo, `403` organizador/admin); `/me` solo propias; organizador ve las de sus eventos; `ADMIN` todas; recurso no visible `404`.                                                                                        | `AUTH-BR-12`/`AUTH-AC-30` y R5.3.                                                                                       |
| D9  | Consultas                                            | `/me` paginado (todas por defecto, filtros `status`/`event_id`, orden `created_at DESC, id DESC`, con resúmenes de evento y sesión); listado por evento paginado con filtro `status`; detalle por `id`; lista vacía `200` con `items: []`.             | Cubre "ver los eventos a los que está registrado" y la gestión del organizador con la convención `PLAT-BR-05`.           |
| D10 | Caché                                                | Cachear **solo** `/me` por usuario (`registrations:me:{user_id}:...`, TTL 60 s); cada escritura invalida `registrations:` del usuario afectado **y** `events:`; listados por evento sin caché; Redis opcional.                                          | Bonus obligatorio de caching con bajo riesgo de inconsistencia (R4.4).                                                  |
| D11 | Contrato                                             | Seis operaciones: alta al evento, alta a sesión, `DELETE`, `/me`, listado por evento y detalle; alta nueva `201`, reactivación `200`.                                                                                                                  | Contrato mínimo que cubre todos los casos de uso.                                                                       |
| D12 | Cascada al cancelar la inscripción al evento         | Cancelar la inscripción al evento cancela **en la misma transacción** las inscripciones `ACTIVE` del usuario a sesiones de ese evento.                                                                                                                  | Evita asistentes "fantasma" en sesiones sin cupo de evento. Descartado: dejar las sesiones activas.                      |
| D13 | Privacidad                                           | El listado por evento expone `user_id`, estado y fechas; **nunca** `full_name` ni `email`; `RegistrationRead` no incluye datos personales del usuario.                                                                                                 | R5.8: solo el `ADMIN` ve perfiles ajenos, y por `auth`.                                                                 |
| D14 | Reactivación                                         | Vuelve a validar capacidad y estado del evento; sin cupo `409` y la fila sigue `CANCELLED`.                                                                                                                                                           | Una reactivación no puede saltarse la invariante de capacidad.                                                          |
| D15 | (Derivada) FKs y borrado físico del padre              | `user_id` es `ON DELETE RESTRICT` y `event_id`/`session_id` son `ON DELETE CASCADE` (la segunda nullable): borrar un evento o una sesión sin inscripciones `ACTIVE` elimina sus inscripciones por cascada y responde `204`, mientras los guards de `EVT-BR-07`/`SES-BR-11` siguen devolviendo `409` cuando hay inscripciones `ACTIVE`. | Sin acoplar `registrations` a los servicios de `events`/`sessions` y sin lógica de purga cruzada; los guards existentes ya protegen el caso activo y el histórico `CANCELLED` desaparece con su padre. Descartado: `RESTRICT` en `event_id`/`session_id` con purga explícita en `delete_event`/`delete_session`. |
| D16 | (Derivada) Código de error del listado por evento   | El listado por evento responde `403` al actor autenticado sin permiso y `404` solo si el evento no existe; el `404` por no visibilidad se reserva a recursos individuales.                                                                              | Coherencia con las escrituras de `sessions` (§13 de `specs/sessions/spec.md`) y con el patrón `get_owned_event_for_write`. Descartado: `404` en el listado, que ocultaría un `403` legítimo de rol. |

### 14.1. Alternativas descartadas

- **Tabla intermedia `event_attendees` + `session_attendees`:** duplica el modelo y complica la atomicidad; una sola tabla con `session_id` nullable cumple el diagrama ER v1.1 §3.4.
- **Contar sesiones dentro del cupo del evento:** rompe la semántica "un cupo por persona" de D2.
- **`SELECT ... FOR UPDATE` sobre la fila de `sessions` antes que `events`:** invierte el orden de `sessions` y arriesga interbloqueos.
- **`pg_advisory_xact_lock`:** serializa, pero introduce una convención global de claves sin necesidad (D3).
- **Restricción `EXCLUDE` o triggers para validar `session.event_id = registration.event_id`:** exige extensiones o lógica en base de datos; se valida en el servicio dentro de la transacción (R4.5).
- **Borrado físico de inscripciones:** impediría la reactivación de D4.
- **Caché del listado por evento:** datos de gestión que deben reflejar el estado inmediato.
- **Validación de conflicto de horario entre sesiones:** fuera de alcance (§2.2).

### 14.2. Decisiones pendientes

Ninguna. El usuario aprobó explícitamente esta spec el 2026-11-01 ("Sí, apruebo") y se inició la implementación (R1.8).

La implementación TDD (`B1..B34`, `F1..F7`) y la validación (`V1..V6`) se completaron el 2026-11-01; el `reviewer` emitió el veredicto `¿pasa? sí` (38/38 criterios `REG-AC` y 14/14 reglas `REG-BR`), por lo que la spec pasa de `En implementación` a `Implementada`.

## 15. Trazabilidad con la prueba técnica

| Requisito (`docs/prueba_tecnica_desarrollador_fullstack.md`)                     | Criterios `REG-AC`                                                                                   |
| -------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| §4 "Permitir al usuario autenticado registrarse a un evento (si hay capacidad)"   | `REG-AC-01`, `REG-AC-02`, `REG-AC-03`, `REG-AC-04`, `REG-AC-09`, `REG-AC-11`                          |
| §4 "Permitir al usuario autenticado ver los eventos a los que está registrado"    | `REG-AC-22`, `REG-AC-23`, `REG-AC-24`, `REG-AC-35`                                                    |
| §4 "Controlar la capacidad de los eventos"                                        | `REG-AC-02`, `REG-AC-03`, `REG-AC-04`, `REG-AC-15`, `REG-AC-16`, `REG-AC-33`                          |
| Bonus "Roles de usuarios" y "Permisos de acceso por rol"                          | `REG-AC-11`, `REG-AC-21`, `REG-AC-24`, `REG-AC-25`, `REG-AC-26`, `REG-AC-27`, `REG-AC-36`, `REG-AC-38` |
| Bonus "Caching de datos (Redis en el backend)"                                    | `REG-AC-28`, `REG-AC-29`                                                                              |
| UI/UX "Loading states y feedback visual"; "Manejo adecuado de errores"            | `REG-AC-30`, `REG-AC-35`, `REG-AC-36`, `REG-AC-37`, `REG-AC-38`                                        |
| Entrega "Documentación API (Swagger/OpenAPI)"                                     | `REG-AC-31`                                                                                           |
| Entrega "Tests unitarios + cobertura"                                             | `REG-AC-01` a `REG-AC-38` (todos con test con su ID)                                                  |

## 16. Impacto en backend y frontend

### 16.1. Backend

- Nuevo módulo `backend/app/registrations/` (`models.py`, `schemas.py`, `dependencies.py`, `service.py`, `router.py`) y registro del router en `app/main.py`.
- Migración `0005_create_registrations` e importación del modelo en `migrations/env.py` para que `SQLModel.metadata` y el `TRUNCATE` de `tests/conftest.py` la incluyan.
- Cambios mínimos y sin cambio de contrato en dominios existentes: solo el cuerpo de `get_registered_count` (`app/events/service.py`) y de `get_session_registered_count` (`app/sessions/service.py`) con el `COUNT(*)` real; `delete_event`/`delete_session` **no** cambian, porque la cascada de las FKs elimina el histórico (D15).
- Sin cambios en `EventRead`, `SessionRead`, rutas ni schemas de `events`/`sessions`.
- Sin dependencias nuevas (R4.2).

### 16.2. Frontend

- `types/api.ts`: `RegistrationStatus`, `RegistrationEventSummary`, `RegistrationSessionSummary`, `RegistrationRead`, `RegistrationListResponse`, `RegistrationListQuery`.
- `services/registrations.ts` con las seis llamadas y `stores/registrations.ts` (`useRegistrationStore`).
- `ProfileView.vue`: sección "Mis inscripciones" con paginación, filtro por estado, cancelación con confirmación y estados de carga/vacío/error.
- `EventDetailView.vue`: sustituye el bloque `registration-placeholder` por la acción de inscripción (solo `ATTENDEE`, solo `PUBLISHED`), añade la inscripción por sesión y, para organizador/`ADMIN`, un listado diferido de inscripciones del evento.
- Sin rutas nuevas, sin librerías nuevas, sin `v-html`, sin cálculo de cupos en el cliente (R2.5, R4.3, R5.9).

## 17. Criterios explícitos de no implementación

1. **No** se implementa ningún endpoint de pago, entrada, QR, check-in, asistencia, certificado, lista de espera ni notificación.
2. **No** se valida conflicto de horario entre sesiones de un mismo asistente; queda documentado como fuera de alcance en §2.2 y §11.
3. **No** se implementa borrado físico de inscripciones ni cambio de `user_id`, `event_id` o `session_id`.
4. **No** se modifica `EventRead`, `SessionRead` ni las rutas de `events`/`sessions`; solo se sustituye el cuerpo de sus hooks de conteo. `delete_event`/`delete_session` no cambian: la cascada de las FKs elimina el histórico (D15).
5. **No** se añaden estados de inscripción distintos de `ACTIVE` y `CANCELLED`.
6. **No** se implementa sobreventa, reserva temporal ni expiración de cupo.
7. **No** se añaden rutas de frontend ni componentes de librerías de UI; `v-html` sigue prohibido.
8. **No** se implementa nada hasta que el usuario apruebe esta spec (R1.8); este documento y sus dos artefactos hermanos son solo especificación.

## 18. Matriz de trazabilidad (`REG-BR-NN` ↔ `REG-AC-NN` ↔ tareas)

| Regla de negocio | Criterios de aceptación                                                        | Tareas TDD asociadas (`specs/registrations/tasks.md`)                   |
| ---------------- | ------------------------------------------------------------------------------ | ----------------------------------------------------------------------- |
| **REG-BR-01**    | `REG-AC-01`, `REG-AC-32`                                                       | `B1`, `B2`, `V1`                                                        |
| **REG-BR-02**    | `REG-AC-12`, `REG-AC-13`, `REG-AC-14`, `REG-AC-37`                             | `B13`, `B14`, `B15`, `F5`                                               |
| **REG-BR-03**    | `REG-AC-01`, `REG-AC-02`, `REG-AC-03`, `REG-AC-04`, `REG-AC-33`, `REG-AC-36`   | `B2`, `B3`, `B4`, `B5`, `B33`, `F3`                                     |
| **REG-BR-04**    | `REG-AC-12`, `REG-AC-15`, `REG-AC-16`, `REG-AC-33`, `REG-AC-37`                | `B13`, `B16`, `B17`, `B33`, `F5`                                        |
| **REG-BR-05**    | `REG-AC-04`, `REG-AC-16`                                                       | `B5`, `B17`, `B19`, `B21`, `V3`                                         |
| **REG-BR-06**    | `REG-AC-05`, `REG-AC-06`, `REG-AC-07`, `REG-AC-08`, `REG-AC-17`                | `B6`, `B7`, `B8`, `B9`, `B18`                                           |
| **REG-BR-07**    | `REG-AC-08`, `REG-AC-09`, `REG-AC-10`, `REG-AC-36`                             | `B9`, `B10`, `B11`, `F3`                                                |
| **REG-BR-08**    | `REG-AC-12`, `REG-AC-13`, `REG-AC-14`, `REG-AC-17`, `REG-AC-37`                 | `B13`, `B14`, `B15`, `B18`, `F5`                                        |
| **REG-BR-09**    | `REG-AC-18`, `REG-AC-19`, `REG-AC-20`, `REG-AC-21`                             | `B19`, `B20`, `B21`, `B22`, `F2`                                        |
| **REG-BR-10**    | `REG-AC-11`, `REG-AC-21`, `REG-AC-24`, `REG-AC-25`, `REG-AC-26`, `REG-AC-27`, `REG-AC-36`, `REG-AC-38` | `B12`, `B22`, `B25`, `B26`, `B27`, `B28`, `F4`, `F6`                    |
| **REG-BR-11**    | `REG-AC-22`, `REG-AC-23`, `REG-AC-24`, `REG-AC-25`, `REG-AC-26`, `REG-AC-35`, `REG-AC-38` | `B23`, `B24`, `B25`, `B26`, `B27`, `F1`, `F2`, `F6`                     |
| **REG-BR-12**    | `REG-AC-28`, `REG-AC-29`                                                       | `B29`, `B30`                                                            |
| **REG-BR-13**    | `REG-AC-25`, `REG-AC-30`, `REG-AC-31`, `REG-AC-35`, `REG-AC-38`                | `B26`, `B31`, `B32`, `F6`, `F7`, `V2`                                  |
| **REG-BR-14**    | `REG-AC-32`, `REG-AC-33`, `REG-AC-34`                                          | `B1`, `B33`, `B34`, `V1`                                                |

Cobertura de criterios por tarea (resumen):

| Tarea | Criterios                | Tarea | Criterios                |
| ----- | ------------------------ | ----- | ------------------------ |
| `B1`  | `REG-AC-32`              | `B19` | `REG-AC-18`              |
| `B2`  | `REG-AC-01`              | `B20` | `REG-AC-19`              |
| `B3`  | `REG-AC-02`              | `B21` | `REG-AC-20`              |
| `B4`  | `REG-AC-03`              | `B22` | `REG-AC-21`              |
| `B5`  | `REG-AC-04`              | `B23` | `REG-AC-22`              |
| `B6`  | `REG-AC-05`              | `B24` | `REG-AC-23`              |
| `B7`  | `REG-AC-06`              | `B25` | `REG-AC-24`              |
| `B8`  | `REG-AC-07`              | `B26` | `REG-AC-25`              |
| `B9`  | `REG-AC-08`              | `B27` | `REG-AC-26`              |
| `B10` | `REG-AC-09`              | `B28` | `REG-AC-27`              |
| `B11` | `REG-AC-10`              | `B29` | `REG-AC-28`              |
| `B12` | `REG-AC-11`              | `B30` | `REG-AC-29`              |
| `B13` | `REG-AC-12`              | `B31` | `REG-AC-30`              |
| `B14` | `REG-AC-13`              | `B32` | `REG-AC-31`              |
| `B15` | `REG-AC-14`              | `B33` | `REG-AC-33`              |
| `B16` | `REG-AC-15`              | `B34` | `REG-AC-34`              |
| `B17` | `REG-AC-16`              | `F1`  | `REG-AC-35`              |
| `B18` | `REG-AC-17`              | `F2`  | `REG-AC-35`              |
| `F3`  | `REG-AC-36`              | `F4`  | `REG-AC-36`              |
| `F5`  | `REG-AC-37`              | `F6`  | `REG-AC-38`              |
| `F7`  | `REG-AC-35`, `REG-AC-38` | `V1`  | `REG-AC-32`              |
| `V2`  | `REG-AC-31`              | `V3`  | `REG-AC-04`, `REG-AC-16` |
| `V4`  | `REG-AC-35` a `REG-AC-38` | `V5` | `REG-AC-01`, `REG-AC-18`, `REG-AC-22`, `REG-AC-36` |
| `V6`  | Todos (`REG-AC-01` a `REG-AC-38`) | — | —                 |

## 19. Historial

| Versión | Fecha      | Cambio                                                                                                                                                             |
| ------- | ---------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 0.1     | 2026-11-01 | Borrador inicial completo del dominio `registrations` (`REG`) con las 14 decisiones aprobadas por el usuario (D1–D14), 2 decisiones derivadas (D15–D16), 14 reglas `REG-BR`, 38 criterios EARS `REG-AC` y el contrato de las 6 operaciones. Pendiente de aprobación explícita (R1.8). |
| 0.1     | 2026-11-01 | Ajustes de revisión: FKs CASCADE en evento/sesión (D15 revisada), reactivación de sesión exige inscripción al evento, cancelación de sesión no afecta al evento y listado por evento solo con inscripciones al evento. |
| 0.1     | 2026-11-01 | Aprobación explícita del usuario ("Sí, apruebo"): Borrador → Aprobada. |
| 0.1     | 2026-11-01 | Inicio de la implementación aprobado en la misma decisión: Aprobada → En implementación (Paso 6, TDD). |
| 0.1     | 2026-11-01 | Implementación TDD completa (B1..B34, F1..F7) y validación (V1..V6) con veredicto ¿pasa? sí del reviewer (38/38 REG-AC): En implementación → Implementada. |

## 20. Referencias normativas

1. `docs/prueba_tecnica_desarrollador_fullstack.md` — §4 "Gestión de asistentes": registrarse a un evento con capacidad, ver los eventos a los que está registrado y controlar la capacidad.
2. `docs/constitution.md` (v1.1.1) — Principios 1–6; en especial R1.5/R1.8/R1.9, R2.5, R3.4/R3.6/R3.7, R4.4/R4.5, R5.2–R5.9, R6.
3. `docs/Analisis-Arquitectonico-Funcional-Plataforma-Mis-Eventos.md` (v1.1) — §3.4 modelo de datos y diagrama ER, §3.5 inscripción atómica, §3.6 caché, §3.7 migraciones, §4 frontend.
4. `specs/README.md` — orden de dominios, dependencias y estado de las specs (§1.4, §2, §5).
5. `specs/platform/spec.md` — formato de error, paginación, fechas UTC y caché.
6. `specs/auth/spec.md` — JWT, RBAC, `AUTH-BR-12` y `AUTH-AC-30` (solo `ATTENDEE` se inscribe).
7. `specs/events/spec.md` — `EVT-BR-04` (capacidad y cupos), `EVT-BR-07` (borrado condicional), `EVT-AC-15`, `EVT-AC-19`.
8. `specs/sessions/spec.md` — §11 (capacidad), §15 (dependencias futuras con `registrations`), `SES-BR-09`, `SES-BR-11`.
