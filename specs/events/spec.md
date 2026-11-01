# Spec: Gestión de Eventos y Catálogo (`events`)

| Campo                      | Valor                                                        |
| -------------------------- | ------------------------------------------------------------ |
| **ID del dominio**         | `EVT`                                                        |
| **Versión**                | 1.0                                                          |
| **Estado**                 | Implementada                                                 |
| **Fecha**                  | 2026-10-31                                                   |
| **Dependencias**           | `platform` (Dominio 0, v1.0), `auth` (Dominio 1, v1.0)       |
| **Decisiones bloqueantes** | Ninguna (Decisiones 1–10 resueltas con el usuario)           |

> Esta spec describe **qué** hace el sistema en el dominio `events`, no cómo se implementa. Los detalles técnicos van en `plan.md`. Estado según R1.8 de `docs/constitution.md`: solo el usuario la marca como _Aprobada_.

## 1. Objetivo

Proporcionar el núcleo operativo de gestión de eventos para organizadores y administradores y el escaparate público/autenticado del catálogo para los asistentes: CRUD completo de eventos con control de propiedad por rol, máquina de estados (`DRAFT`, `PUBLISHED`, `CANCELLED`), exposición de capacidad total, inscritos y cupos disponibles calculados exclusivamente por el backend (R2.5), búsqueda por nombre o parte del nombre acelerada con índice trigrama (`pg_trgm`) en PostgreSQL (R3.6), caché de lectura prescindible en Redis invalidada en cada escritura (R4.4), conversión síncrona de imágenes a tres variantes WebP sin metadatos EXIF servidas desde `/api/media/` (Arquitectura v1.1 §3.8), y vistas responsivas en Vue 3 con `useEventStore`, `EventCard.vue` y `EventForm.vue` cargado de forma diferida (`defineAsyncComponent`).

## 2. Alcance

### 2.1. Incluye

- Catálogo paginado de eventos (`GET /api/events`) con autenticación opcional, visibilidad diferenciada por rol, ordenación determinista (`date ASC, id ASC`), búsqueda parcial por título (`search` con `ILIKE` + índice GIN `gin_trgm_ops`), filtro por estado (`status`) y filtro de autoría (`mine=true`).
- Consulta de detalle de evento (`GET /api/events/{id}`) con autenticación opcional y control de visibilidad por estado y propiedad.
- Creación de eventos (`POST /api/events`) por `ORGANIZER` y `ADMIN`, asignando `organizer_id` automáticamente al usuario autenticado.
- Edición parcial y transición de estado (`PATCH /api/events/{id}`) por el `ORGANIZER` propietario o un `ADMIN`, conservando `organizer_id` intacto ante ediciones administrativas.
- Máquina de estados estricta (`DRAFT`, `PUBLISHED`, `CANCELLED`) donde `CANCELLED` es un estado terminal e inmutable y no se permite regresar de `PUBLISHED` a `DRAFT`.
- Exposición en `EventRead` de `total_capacity`, `registered_count` y `available_capacity` calculados exclusivamente en el servidor (R2.5) y bloqueo ante reducciones de `total_capacity` por debajo de `registered_count`.
- Eliminación física condicional (`DELETE /api/events/{id}`) permitida solo cuando `registered_count == 0` (con limpieza de variantes WebP e invalidación de caché) y rechazada con `409` cuando existen inscritos.
- Subida y reemplazo de imagen del evento (`POST /api/events/{id}/image`) validada con Pillow (`JPEG`, `PNG`, `WEBP`, máx. 5 MB), transposición de orientación EXIF, descarte total de metadatos EXIF/ICC/XMP (R5.8), generación síncrona de tres variantes WebP (`400w`, `800w`, `1200w`) sin ampliar imágenes pequeñas (`no upscaling`), borrado de variantes previas y entrega de URLs relativas en `image_urls` (`/api/media/events/...`).
- Caché de lectura en Redis (`GET /api/events` y `GET /api/events/{id}`) con claves aisladas por ámbito de rol (`scope`), TTL de 60 s, invalidación del prefijo `events:` en toda escritura y degradación transparente a PostgreSQL si Redis no responde (R4.4).
- Frontend en Vue 3 + TypeScript ligero: `useEventStore`, servicio `events.ts`, vistas `EventsListView.vue` (`/`), `EventDetailView.vue` (`/events/:id`) y `EventFormView.vue` (`/events/new`, `/events/:id/edit`), componentes reutilizables `EventCard.vue` y `EventForm.vue` (este último cargado con `defineAsyncComponent`), imágenes con `srcset`/`sizes` y estados de carga/alertas en español.

### 2.2. No incluye

- CRUD de sesiones, ponentes ni validación de solapamiento de horarios (pertenecen al Dominio 3: `specs/sessions/`).
- Inscripción de asistentes a eventos/sesiones ni vista "Mis inscripciones" (pertenecen al Dominio 4: `specs/registrations/`).
- Procesamiento asíncrono con colas/workers (prohibido por R4.3), CDN externo, recorte interactivo de imágenes en el navegador o galería de múltiples imágenes por evento.
- Transferencia manual de `organizer_id` entre usuarios o co-organizadores.

## 3. Roles involucrados

| Rol         | Qué puede hacer en este dominio                                                                                                                                                                                                 |
| ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Anónimo     | Listar y buscar eventos en estado `PUBLISHED` (`GET /api/events`), ver el detalle de eventos `PUBLISHED` (`GET /api/events/{id}`) y cargar sus imágenes WebP en `/api/media/events/*`. No puede usar `mine=true` (`401`) ni escribir (`401`). |
| `ATTENDEE`  | Igual que Anónimo: listar y ver el detalle únicamente de eventos `PUBLISHED`. No puede usar `mine=true` (`403`) ni crear, editar, subir imagen o eliminar eventos (`403`).                                                      |
| `ORGANIZER` | Ver todos los eventos `PUBLISHED` (propios y ajenos) más **sus propios eventos** en cualquier estado (`DRAFT`, `PUBLISHED`, `CANCELLED`); filtrar los suyos con `mine=true`; crear eventos (`organizer_id` = su propio id); editar, cambiar estado, subir/reemplazar imagen y eliminar (si `registered_count == 0`) **únicamente sus propios eventos**. Recibe `403` si intenta modificar un evento ajeno y `404` si consulta por ID un evento `DRAFT` o `CANCELLED` ajeno. |
| `ADMIN`     | Visibilidad total de todos los eventos de cualquier organizador en cualquier estado (`DRAFT`, `PUBLISHED`, `CANCELLED`); puede usar `mine=true`; puede crear eventos y editar, cambiar estado, subir/reemplazar imagen o eliminar (si `registered_count == 0`) cualquier evento conservando siempre el `organizer_id` original del evento. |

## 4. Reglas de negocio

- **EVT-BR-01 (Visibilidad pública y por rol):** Los endpoints de lectura (`GET /api/events` y `GET /api/events/{id}`) aceptan autenticación opcional; los usuarios Anónimos y `ATTENDEE` solo pueden ver eventos en estado `PUBLISHED` (recibiendo `404 "Evento no encontrado"` al consultar por ID un evento `DRAFT` o `CANCELLED` y un listado vacío `items: []` si filtran por un estado distinto de `PUBLISHED`); el `ORGANIZER` ve todos los eventos `PUBLISHED` más sus propios eventos en cualquier estado (`DRAFT`, `PUBLISHED`, `CANCELLED`, recibiendo `404` si solicita por ID un evento no publicado de otro organizador); el `ADMIN` ve todos los eventos en cualquier estado; el parámetro `mine=true` en `GET /api/events` restringe el resultado a `organizer_id == current_user.id` para `ORGANIZER` y `ADMIN`, devolviendo `401` a usuarios Anónimos y `403` a `ATTENDEE` (R5.3, R5.6, R5.8).
- **EVT-BR-02 (Propiedad del recurso y administración):** Solo los roles `ORGANIZER` y `ADMIN` pueden crear eventos (`POST /api/events`); el campo `organizer_id` se asigna automáticamente en el servidor al `id` del creador autenticado y está prohibido enviarlo en el cuerpo de entrada (`422`); solo el `ORGANIZER` dueño del evento (`event.organizer_id == current_user.id`) o un `ADMIN` pueden modificarlo (`PATCH`), subir su imagen (`POST /image`) o eliminarlo (`DELETE`), devolviendo `403 "No tienes permisos para realizar esta acción"` a cualquier otro usuario autenticado; cuando un `ADMIN` actualiza un evento ajeno, `organizer_id` se conserva intacto (R5.2, R5.3).
- **EVT-BR-03 (Máquina de estados e inmutabilidad de `CANCELLED`):** El estado del evento (`status`) toma únicamente los valores `DRAFT`, `PUBLISHED` o `CANCELLED` en inglés (R6.1, traducidos en la UI como `Borrador`, `Publicado` y `Cancelado`); al crear un evento el estado por defecto es `DRAFT` y solo se admite crear en `DRAFT` o `PUBLISHED` (enviar `CANCELLED` en el alta responde `422`); en `PATCH /api/events/{id}` las únicas transiciones válidas son `DRAFT → PUBLISHED`, `DRAFT → CANCELLED`, `PUBLISHED → CANCELLED` y mantener el mismo estado (`DRAFT → DRAFT`, `PUBLISHED → PUBLISHED`); intentar pasar de `PUBLISHED → DRAFT` responde `409` con `"No se puede regresar un evento publicado a borrador"`, y cualquier intento de cambiar el estado, editar campos o subir imagen de un evento que ya está en `CANCELLED` responde `409` con `"Un evento cancelado no puede cambiar de estado ni editarse"`.
- **EVT-BR-04 (Capacidad calculada por el backend y límite ante reducción):** La capacidad total (`total_capacity`) es un entero obligatorio entre `1` y `100000` (`CHECK (total_capacity >= 1)` en PostgreSQL); toda respuesta `EventRead` expone `total_capacity`, `registered_count` y `available_capacity = max(0, total_capacity - registered_count)` calculados exclusivamente por el backend (R2.5, estando prohibido recalcular cupos en el frontend); si en `PATCH /api/events/{id}` se envía un `total_capacity` menor que `registered_count`, el sistema rechaza la actualización con código `409` y `detail = "No se puede reducir la capacidad total por debajo del número de inscritos actuales"`.
- **EVT-BR-05 (Fechas en UTC y frontera con sesiones):** Los campos `date`, `created_at` y `updated_at` del evento se normalizan, almacenan en PostgreSQL (`TIMESTAMP WITH TIME ZONE`) y serializan en UTC en formato ISO 8601 con sufijo `Z` (`PLAT-BR-06`); `date` no se rechaza por estar en el pasado respecto al reloj del servidor para garantizar el determinismo de las pruebas (R3.7) y establece la frontera temporal para el dominio `sessions` (las sesiones de un evento deberán celebrarse en la misma fecha UTC del evento con `session.start_time >= event.date`).
- **EVT-BR-06 (Búsqueda trigrama `pg_trgm`, filtrado y paginación):** `GET /api/events` aplica la convención de paginación `PLAT-BR-05` (`page` por defecto `1`, `size` por defecto `10` y máximo `50`), ordena los resultados de forma determinista por `date ASC, id ASC` y permite filtrar por `search` (`trim`, hasta `100` caracteres; vacío tras `trim` no filtra) mediante búsqueda de subcadena insensible a mayúsculas/minúsculas sobre `title` (`ILIKE '%<escaped>%'` escapando `%`, `_` y `\`) respaldada por un índice GIN `gin_trgm_ops` en PostgreSQL (R3.6), combinable con `status` y `mine`.
- **EVT-BR-07 (Eliminación física condicional):** `DELETE /api/events/{id}` solo está permitido al `ORGANIZER` propietario o a un `ADMIN`; cuando `registered_count == 0`, elimina físicamente el registro del evento en PostgreSQL, borra del volumen `media` sus tres archivos WebP si tenía imagen asociada, invalida la caché Redis y responde `204 No Content`; cuando `registered_count > 0`, impide el borrado físico y responde `409` con `"No se puede eliminar un evento con asistentes inscritos; cancélalo en su lugar"`.
- **EVT-BR-08 (Imágenes optimizadas WebP con Pillow y 3 variantes):** `POST /api/events/{id}/image` acepta un archivo en `multipart/form-data` (`file`) de hasta 5 MB (`> 5 MB` responde `413` con `"La imagen no debe superar los 5 MB"`, `0 bytes` responde `400` con `"El archivo de imagen está vacío"`), decodifica y verifica el contenido binario real con Pillow admitiendo únicamente `JPEG`, `PNG` y `WEBP` (cualquier otro formato o archivo corrupto responde `400` con `"Formato de imagen no soportado. Usa JPEG, PNG o WebP"`), corrige la orientación con `ImageOps.exif_transpose`, elimina todos los metadatos EXIF/ICC/XMP (R5.8), genera síncronamente tres variantes WebP (`quality=80`) para los anchos máximos `400`, `800` y `1200` px manteniendo la proporción y sin ampliar imágenes de menor ancho (`no upscaling`), las escribe en `{MEDIA_ROOT}/events/{image_key}_{400|800|1200}w.webp` usando un UUID v4 nuevo, elimina las variantes anteriores si el evento ya tenía imagen y expone en `EventRead.image_urls` las rutas relativas `/api/media/events/...` (`null` si no tiene imagen) para que el frontend nunca construya rutas de archivos (R2.3, Arquitectura v1.1 §3.8).
- **EVT-BR-09 (Caché Redis prescindible e invalidación por escritura):** Las lecturas de `GET /api/events` y `GET /api/events/{id}` se almacenan en Redis bajo el prefijo `events:` con un TTL de 60 segundos incluyendo en la clave el ámbito de visibilidad del actor (`public`, `org:{user_id}` o `admin`) para evitar fugas de eventos no publicados entre roles (R5.8); toda operación de escritura (`POST /api/events`, `PATCH /api/events/{id}`, `DELETE /api/events/{id}`, `POST /api/events/{id}/image`, además de futuras escrituras en `sessions` y `registrations`) invalida el prefijo `events:`; si Redis no está disponible o falla, la API responde desde PostgreSQL sin propagar error (R4.4).
- **EVT-BR-10 (Validación de esquemas, errores en español y UX responsiva/lazy en frontend):** Los esquemas de entrada aplican `extra="forbid"`, validan `title` (`trim`, 3–160 caracteres) y `description` (`trim`, 10–5000 caracteres), rechazan cuerpos vacíos en `PATCH` (`422` con `"Debes indicar al menos un campo para actualizar"`) y formatean todos los errores en español según `PLAT-BR-04`; el frontend gestiona el estado con `useEventStore`, presenta imágenes WebP responsivas con `srcset`, `sizes`, `loading="lazy"` y `decoding="async"`, carga `EventForm.vue` mediante `defineAsyncComponent` y prohíbe `v-html` con contenido de usuario (R5.9, Principio 6).

## 5. Modelo observable, máquina de estados, capacidad, imágenes y caché

### 5.1. `EventRead` y `EventImageUrls`

Toda respuesta que devuelve un evento (tanto en `GET /api/events/{id}`, `POST`, `PATCH`, `POST /image` como dentro de `items[]` en `GET /api/events`) utiliza el esquema `EventRead`:

| Campo                | Tipo                       | Reglas y descripción                                                                                                  |
| -------------------- | -------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `id`                 | entero                     | Identificador único del evento.                                                                                       |
| `title`              | texto                      | Obligatorio, recortado (`trim`), entre 3 y 160 caracteres.                                                            |
| `description`        | texto                      | Obligatorio, recortado (`trim`), entre 10 y 5000 caracteres.                                                          |
| `date`               | fecha y hora UTC           | Obligatorio, ISO 8601 en UTC terminado en `Z` (PLAT-BR-06).                                                           |
| `total_capacity`     | entero                     | Obligatorio, entre `1` y `100000`.                                                                                    |
| `registered_count`   | entero                     | Solo lectura, calculado por el backend (`>= 0`). En este dominio vale `0` por defecto hasta que existan inscripciones. |
| `available_capacity` | entero                     | Solo lectura, calculado por el backend como `max(0, total_capacity - registered_count)` (R2.5).                       |
| `status`             | enumerado                  | `DRAFT`, `PUBLISHED` o `CANCELLED` (en inglés en API/BD según R6.1; traducido solo en la UI).                         |
| `organizer_id`       | entero                     | `id` del usuario creador/propietario del evento (`FK users.id`).                                                      |
| `image_urls`         | `EventImageUrls \| null`   | `null` si el evento no tiene imagen, o diccionario con las 3 URLs relativas WebP (`w400`, `w800`, `w1200`).           |
| `created_at`         | fecha y hora UTC           | Solo lectura, ISO 8601 en UTC (`Z`).                                                                                  |
| `updated_at`         | fecha y hora UTC           | Solo lectura, actualizado en cada modificación (`PATCH` o subida de imagen), ISO 8601 en UTC (`Z`).                   |

Estructura de `EventImageUrls` cuando el evento posee imagen (`image_key` presente en BD):

```json
{
  "w400": "/api/media/events/a1b2c3d4e5f64789a1b2c3d4e5f64789_400w.webp",
  "w800": "/api/media/events/a1b2c3d4e5f64789a1b2c3d4e5f64789_800w.webp",
  "w1200": "/api/media/events/a1b2c3d4e5f64789a1b2c3d4e5f64789_1200w.webp"
}
```

La clave interna `image_key` no requiere ser interpretada ni concatenada por el frontend: el cliente usa directamente `image_urls.w400`, `image_urls.w800` e `image_urls.w1200` (R2.3).

### 5.2. Máquina de estados del evento

```text
           ┌───────────────────────────────┐
           │                               ▼
[Alta] ──► DRAFT ──────(publicar)────► PUBLISHED ──(cancelar)──► CANCELLED (terminal / inmutable)
           │                                                       ▲
           └──────────────────────(cancelar)───────────────────────┘
```

| Estado actual | Estado solicitado en `PATCH` | ¿Permitido? | Resultado / Código HTTP y `detail`                                                                |
| ------------- | ---------------------------- | :---------: | ------------------------------------------------------------------------------------------------- |
| _(Nuevo)_     | `DRAFT` (por defecto)        |      ✓      | `201 Created` con `status = "DRAFT"`.                                                             |
| _(Nuevo)_     | `PUBLISHED`                  |      ✓      | `201 Created` con `status = "PUBLISHED"`.                                                         |
| _(Nuevo)_     | `CANCELLED`                  |      —      | `422 Unprocessable Entity` (`detail` genérico + error de validación en `status`).                 |
| `DRAFT`       | `DRAFT` (o sin `status`)     |      ✓      | `200 OK` (idempotente; permite editar campos en borrador).                                        |
| `DRAFT`       | `PUBLISHED`                  |      ✓      | `200 OK` con `status = "PUBLISHED"`.                                                              |
| `DRAFT`       | `CANCELLED`                  |      ✓      | `200 OK` con `status = "CANCELLED"`.                                                              |
| `PUBLISHED`   | `PUBLISHED` (o sin `status`) |      ✓      | `200 OK` (idempotente; permite editar campos permitidos del evento publicado).                    |
| `PUBLISHED`   | `DRAFT`                      |      —      | `409 Conflict` — `detail: "No se puede regresar un evento publicado a borrador"`.                 |
| `PUBLISHED`   | `CANCELLED`                  |      ✓      | `200 OK` con `status = "CANCELLED"`.                                                              |
| `CANCELLED`   | Cualquier `PATCH` o `/image` |      —      | `409 Conflict` — `detail: "Un evento cancelado no puede cambiar de estado ni editarse"`.          |

### 5.3. Reglas de capacidad y frontera con `registrations`

1. En base de datos, `events.total_capacity` tiene `CHECK (total_capacity >= 1)`. En los schemas `EventCreate` y `EventUpdate`, `total_capacity` valida `ge=1` y `le=100000`.
2. El servicio de eventos obtiene `registered_count` mediante un helper de dominio (`get_registered_count(session, event_id) -> int`), que devuelve `0` mientras no existan registros en `registrations` y que en el Dominio 4 consultará el conteo real de inscritos (y permitirá inyectar valores en pruebas unitarias/integración para verificar los bordes `total_capacity < registered_count` y eliminación con inscritos).
3. `available_capacity` se calcula siempre en el backend como `max(0, total_capacity - registered_count)`.
4. En `PATCH /api/events/{id}`, si se incluye `total_capacity` y `new_total_capacity < registered_count`, la operación se aborta con `409 Conflict` y `detail = "No se puede reducir la capacidad total por debajo del número de inscritos actuales"`.

### 5.4. Reglas de búsqueda trigrama (`pg_trgm`), filtrado y paginación

1. **Paginación:** `page` (defecto `1`, `>= 1`) y `size` (defecto `10`, `1..50`) utilizando `PaginationParams` y `build_paginated_response` de `app/core/pagination.py` (`PLAT-BR-05`).
2. **Ordenación determinista:** `ORDER BY events.date ASC, events.id ASC`.
3. **Búsqueda (`search`):**
   - Si se envía `search`, se recorta con `.strip()`.
   - Si tras recortar mide más de `100` caracteres, se rechaza con `422` (`errors[].field = "search"`, mensaje de longitud máxima en español).
   - Si tras recortar queda vacío (`""`), se ignora y no aplica filtro de texto.
   - Si no está vacío, se escapan los caracteres especiales de `LIKE` (`\` → `\\`, `%` → `\%`, `_` → `\_`) y se aplica `Event.title.ilike(f"%{escaped}%", escape="\\")`, aprovechando el índice GIN `ix_events_title_trgm` (`USING gin (title gin_trgm_ops)`).
4. **Filtro `mine`:**
   - `mine=false` o ausente: aplica las reglas normales de visibilidad según el rol del usuario.
   - `mine=true`:
     - Si el usuario es Anónimo → `401` (`"No autenticado o sesión expirada"`).
     - Si el usuario es `ATTENDEE` → `403` (`"No tienes permisos para realizar esta acción"`).
     - Si el usuario es `ORGANIZER` o `ADMIN` → filtra `events.organizer_id == current_user.id` (permitiendo combinarlo con `status` y `search`).
5. **Filtro `status`:**
   - Si no se especifica: Anónimo y `ATTENDEE` ven `status == PUBLISHED`; `ORGANIZER` ve `(status == PUBLISHED OR organizer_id == current_user.id)`; `ADMIN` ve todos los estados.
   - Si se especifica `status`:
     - Para Anónimo y `ATTENDEE`: si `status != PUBLISHED`, devuelve `200 OK` con `items: [], total: 0, pages: 0`.
     - Para `ORGANIZER`: si `status == PUBLISHED`, devuelve los `PUBLISHED` (o solo los suyos si `mine=true`); si `status` es `DRAFT` o `CANCELLED`, devuelve únicamente los eventos con ese estado donde `organizer_id == current_user.id`.
     - Para `ADMIN`: devuelve todos los eventos con ese `status` (o los suyos si además envía `mine=true`).

### 5.5. Reglas de procesamiento de imágenes WebP

1. **Entrada:** `POST /api/events/{id}/image` con `multipart/form-data` y campo `file`.
2. **Lectura acotada:** se leen hasta `5 * 1024 * 1024 + 1` bytes (`5_242_881` bytes).
   - Si `len(data) == 0` → `400 Bad Request` con `detail = "El archivo de imagen está vacío"`.
   - Si `len(data) > 5 * 1024 * 1024` → `413 Content Too Large` con `detail = "La imagen no debe superar los 5 MB"`.
3. **Decodificación y verificación de formato real con Pillow:**
   - Se abre el buffer con `Image.open(BytesIO(data))` y se comprueba `image.format in {"JPEG", "PNG", "WEBP"}` (forzando `image.load()` para detectar imágenes truncadas o corruptas). No se confía en `file.filename` ni en `file.content_type`.
   - Si falla la apertura, está corrupta o el formato real no es `JPEG`, `PNG` ni `WEBP` → `400 Bad Request` con `detail = "Formato de imagen no soportado. Usa JPEG, PNG o WebP"`.
4. **Orientación y limpieza de metadatos (R5.8):**
   - Se ejecuta `ImageOps.exif_transpose(image)`.
   - Se convierte a `RGBA` (si tiene canal alfa/transparencia) o `RGB`, creando una imagen limpia sin copiar diccionario `exif`, `icc_profile` ni `xmp`.
5. **Generación de 3 variantes WebP (`400w`, `800w`, `1200w`):**
   - Para cada ancho objetivo `target_w` en `(400, 800, 1200)`:
     - Si `orig_width > target_w`: se redimensiona proporcionalmente a `(target_w, max(1, round(orig_height * target_w / orig_width)))` con filtro `Image.Resampling.LANCZOS`.
     - Si `orig_width <= target_w`: **no se amplía** (`no upscaling`); se conserva `(orig_width, orig_height)`.
     - Se guarda en `{MEDIA_ROOT}/events/{new_key}_{target_w}w.webp` con `format="WEBP", quality=80, method=4`.
6. **Reemplazo y limpieza atómica:**
   - Una vez escritos los 3 archivos del nuevo `new_key` y actualizado `event.image_key = new_key` en la base de datos, si existía un `old_key` previo, se eliminan del disco los 3 archivos `{old_key}_{400|800|1200}w.webp` (ignorando `FileNotFoundError`).

### 5.6. Reglas de caché Redis (`R4.4`)

1. **Ámbito (`scope`) en la clave de caché:**
   - Usuario Anónimo o `ATTENDEE` → `scope = "public"`.
   - Usuario `ORGANIZER` → `scope = f"org:{current_user.id}"`.
   - Usuario `ADMIN` → `scope = f"admin:{current_user.id}"` (para aislar también `mine=true` por administrador).
2. **Formato de claves:**
   - Listado: `events:list:scope={scope}:page={page}:size={size}:search={search_norm}:status={status_norm}:mine={mine_norm}`.
   - Detalle: `events:detail:id={event_id}:scope={scope}`.
3. **TTL:** `settings.cache_events_ttl_seconds` (por defecto `60` segundos).
4. **Invalidación:** `cache_client.invalidate_prefix("events:")` se invoca tras hacer `commit` en `create_event`, `update_event`, `delete_event` y `upload_event_image`.

## 6. Contrato de API

Todas las rutas cuelgan de `/api/events`. Los errores siguen el formato de `specs/platform/spec.md` (`{"detail": "<mensaje en español>"}` y, en `422`, `detail = "Error de validación en los datos enviados"` más `errors: [{"field", "message"}]` en español). Todas las fechas se serializan en UTC ISO 8601 con sufijo `Z`.

### 6.1. `GET /api/events`

- **Descripción:** Lista paginada de eventos con búsqueda parcial por título y filtros opcionales de estado y autoría, sujeta a visibilidad por rol.
- **Autenticación / rol requerido:** Público con autenticación Bearer opcional (`Anónimo`, `ATTENDEE`, `ORGANIZER`, `ADMIN`).
- **Parámetros Query:**
  - `page`: entero opcional, por defecto `1`, restricción `>= 1`.
  - `size`: entero opcional, por defecto `10`, restricción `>= 1` y `<= 50`.
  - `search`: texto opcional (`trim`, máximo `100` caracteres).
  - `status`: enumerado opcional (`DRAFT`, `PUBLISHED`, `CANCELLED`).
  - `mine`: booleano opcional (`true` o `false`, por defecto `false`).
- **Response `200 OK`:**

```json
{
  "items": [
    {
      "id": 1,
      "title": "Conferencia Python Colombia",
      "description": "Encuentro anual de desarrollo con FastAPI y Vue.",
      "date": "2026-11-15T14:00:00Z",
      "total_capacity": 120,
      "registered_count": 0,
      "available_capacity": 120,
      "status": "PUBLISHED",
      "organizer_id": 2,
      "image_urls": {
        "w400": "/api/media/events/9b1deb4d3b7d4bad9bdd2b0d7b3dcb6d_400w.webp",
        "w800": "/api/media/events/9b1deb4d3b7d4bad9bdd2b0d7b3dcb6d_800w.webp",
        "w1200": "/api/media/events/9b1deb4d3b7d4bad9bdd2b0d7b3dcb6d_1200w.webp"
      },
      "created_at": "2026-10-31T15:00:00Z",
      "updated_at": "2026-10-31T15:05:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "size": 10,
  "pages": 1
}
```

- **Errores:**

| Código | Cuándo                                                                                   | `detail` (español)                              |
| ------ | ---------------------------------------------------------------------------------------- | ----------------------------------------------- |
| 401    | Se envía un token Bearer inválido/expirado/inactivo, o un usuario Anónimo envía `mine=true` | `"No autenticado o sesión expirada"`            |
| 403    | Un usuario con rol `ATTENDEE` envía `mine=true`                                          | `"No tienes permisos para realizar esta acción"` |
| 422    | `page < 1`, `size < 1`, `size > 50`, `search` > 100 caracteres, `status` o `mine` inválidos | `"Error de validación en los datos enviados"` + `errors[].message` en español |

### 6.2. `POST /api/events`

- **Descripción:** Crea un nuevo evento asignando `organizer_id` al usuario autenticado.
- **Autenticación / rol requerido:** Autenticado con rol `ORGANIZER` o `ADMIN`.
- **Request:**

```json
{
  "title": "Conferencia Python Colombia",
  "description": "Encuentro anual de desarrollo con FastAPI y Vue.",
  "date": "2026-11-15T14:00:00Z",
  "total_capacity": 120,
  "status": "DRAFT"
}
```

*(El campo `status` es opcional; por defecto es `"DRAFT"`. Solo se admiten `"DRAFT"` o `"PUBLISHED"` en la creación).*

- **Response `201 Created`:** `EventRead` con `organizer_id = current_user.id`, `registered_count = 0`, `available_capacity = total_capacity` e `image_urls = null`.
- **Errores:**

| Código | Cuándo                                                                                               | `detail` (español)                              | `errors[].message` (español)                            |
| ------ | ---------------------------------------------------------------------------------------------------- | ----------------------------------------------- | ------------------------------------------------------- |
| 401    | Token ausente, inválido, expirado o usuario inactivo                                                 | `"No autenticado o sesión expirada"`            | —                                                       |
| 403    | Usuario autenticado con rol `ATTENDEE`                                                               | `"No tienes permisos para realizar esta acción"` | —                                                       |
| 422    | `title` fuera de 3–160 tras `trim`, `description` fuera de 10–5000 tras `trim`, `date` inválida o `total_capacity` fuera de 1..100000 | `"Error de validación en los datos enviados"`   | Mensaje de validación correspondiente en español        |
| 422    | `status` igual a `"CANCELLED"` o valor fuera de `"DRAFT"` / `"PUBLISHED"`                            | `"Error de validación en los datos enviados"`   | Mensaje de estado permitido en español                  |
| 422    | Se incluye `organizer_id`, `registered_count`, `available_capacity`, `image_urls` u otro campo extra | `"Error de validación en los datos enviados"`   | `"Este campo no está permitido"`                        |

### 6.3. `GET /api/events/{id}`

- **Descripción:** Obtiene el detalle de un evento por su identificador si el solicitante tiene visibilidad sobre él.
- **Autenticación / rol requerido:** Público con autenticación Bearer opcional (`Anónimo`, `ATTENDEE`, `ORGANIZER`, `ADMIN`).
- **Response `200 OK`:** `EventRead`.
- **Errores:**

| Código | Cuándo                                                                                                      | `detail` (español)                   |
| ------ | ----------------------------------------------------------------------------------------------------------- | ------------------------------------ |
| 401    | Se envía una cabecera `Authorization` con un token inválido, expirado o de usuario inactivo                 | `"No autenticado o sesión expirada"` |
| 404    | El evento no existe, o está en `DRAFT`/`CANCELLED` y el solicitante no es su `ORGANIZER` propietario ni `ADMIN` | `"Evento no encontrado"`             |
| 422    | `id` no es un número entero válido                                                                          | `"Error de validación en los datos enviados"` + `errors[].message` |

### 6.4. `PATCH /api/events/{id}`

- **Descripción:** Actualiza parcialmente los datos y/o el estado (`status`) de un evento existente.
- **Autenticación / rol requerido:** `ORGANIZER` propietario del evento (`event.organizer_id == current_user.id`) o `ADMIN`.
- **Request:** Al menos uno de los campos `title`, `description`, `date`, `total_capacity`, `status`:

```json
{
  "title": "Conferencia Python Colombia 2026",
  "total_capacity": 150,
  "status": "PUBLISHED"
}
```

- **Response `200 OK`:** `EventRead` actualizado (con `organizer_id` intacto).
- **Errores:**

| Código | Cuándo                                                                                          | `detail` (español)                                                                  | `errors[].message` (español)                            |
| ------ | ----------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- | ------------------------------------------------------- |
| 401    | Token ausente, inválido, expirado o usuario inactivo                                            | `"No autenticado o sesión expirada"`                                                | —                                                       |
| 403    | El usuario es `ATTENDEE` o es un `ORGANIZER` distinto del propietario del evento                | `"No tienes permisos para realizar esta acción"`                                    | —                                                       |
| 404    | El evento no existe                                                                             | `"Evento no encontrado"`                                                            | —                                                       |
| 409    | El evento ya está en estado `CANCELLED`                                                         | `"Un evento cancelado no puede cambiar de estado ni editarse"`                      | —                                                       |
| 409    | El evento está en `PUBLISHED` y se solicita `status = "DRAFT"`                                  | `"No se puede regresar un evento publicado a borrador"`                             | —                                                       |
| 409    | Se solicita `total_capacity < registered_count`                                                 | `"No se puede reducir la capacidad total por debajo del número de inscritos actuales"` | —                                                       |
| 422    | Body vacío `{}` o sin ningún campo actualizable                                                 | `"Error de validación en los datos enviados"`                                       | `"Debes indicar al menos un campo para actualizar"`     |
| 422    | Campos con valores fuera de rango (`title`, `description`, `date`, `total_capacity`, `status`)  | `"Error de validación en los datos enviados"`                                       | Mensaje de validación en español                        |
| 422    | Campo no permitido (`organizer_id`, `image_key`, `available_capacity`, etc.)                    | `"Error de validación en los datos enviados"`                                       | `"Este campo no está permitido"`                        |

### 6.5. `DELETE /api/events/{id}`

- **Descripción:** Elimina físicamente un evento cuando no tiene asistentes inscritos (`registered_count == 0`), borrando sus variantes WebP del volumen `media` e invalidando la caché Redis.
- **Autenticación / rol requerido:** `ORGANIZER` propietario del evento o `ADMIN`.
- **Response `204 No Content`:** Sin cuerpo de respuesta.
- **Errores:**

| Código | Cuándo                                                                           | `detail` (español)                                                            |
| ------ | -------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| 401    | Token ausente, inválido, expirado o usuario inactivo                             | `"No autenticado o sesión expirada"`                                          |
| 403    | El usuario es `ATTENDEE` o es un `ORGANIZER` distinto del propietario del evento | `"No tienes permisos para realizar esta acción"`                              |
| 404    | El evento no existe                                                              | `"Evento no encontrado"`                                                      |
| 409    | El evento tiene asistentes inscritos (`registered_count > 0`)                    | `"No se puede eliminar un evento con asistentes inscritos; cancélalo en su lugar"` |

### 6.6. `POST /api/events/{id}/image`

- **Descripción:** Sube o reemplaza la imagen principal del evento, validándola con Pillow, eliminando metadatos EXIF y generando síncronamente tres variantes WebP (`400w`, `800w`, `1200w`).
- **Autenticación / rol requerido:** `ORGANIZER` propietario del evento o `ADMIN`.
- **Request:** `multipart/form-data` con campo `file` (`UploadFile`).
- **Response `200 OK`:** `EventRead` con `image_urls` poblado con las nuevas rutas `/api/media/events/<image_key>_{400|800|1200}w.webp`.
- **Errores:**

| Código | Cuándo                                                                           | `detail` (español)                                               |
| ------ | -------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| 400    | El archivo subido tiene `0` bytes                                                | `"El archivo de imagen está vacío"`                              |
| 400    | El contenido binario no es una imagen válida o su formato real no es JPEG/PNG/WebP | `"Formato de imagen no soportado. Usa JPEG, PNG o WebP"`         |
| 401    | Token ausente, inválido, expirado o usuario inactivo                             | `"No autenticado o sesión expirada"`                             |
| 403    | El usuario es `ATTENDEE` o es un `ORGANIZER` distinto del propietario del evento | `"No tienes permisos para realizar esta acción"`                 |
| 404    | El evento no existe                                                              | `"Evento no encontrado"`                                         |
| 409    | El evento está en estado `CANCELLED`                                             | `"Un evento cancelado no puede cambiar de estado ni editarse"`   |
| 413    | El archivo supera los 5 MB (`5 * 1024 * 1024` bytes)                             | `"La imagen no debe superar los 5 MB"`                           |
| 422    | Falta el campo `file` en el formulario `multipart/form-data`                     | `"Error de validación en los datos enviados"` + `errors[].message` |

## 7. Matriz de autorización RBAC del dominio `events`

| Acción / Endpoint                                          | Anónimo | `ATTENDEE` | `ORGANIZER` (propio) | `ORGANIZER` (ajeno) | `ADMIN` |
| ---------------------------------------------------------- | :-----: | :--------: | :------------------: | :-----------------: | :-----: |
| `GET /api/events` (eventos `PUBLISHED`)                    |    ✓    |     ✓      |          ✓           |          ✓          |    ✓    |
| `GET /api/events` (eventos `DRAFT` / `CANCELLED`)          |    —    |     —      |          ✓           |          —          |    ✓    |
| `GET /api/events?mine=true`                                |  `401`  |   `403`    |          ✓           |          —          |    ✓    |
| `GET /api/events/{id}` (`PUBLISHED`)                       |    ✓    |     ✓      |          ✓           |          ✓          |    ✓    |
| `GET /api/events/{id}` (`DRAFT` / `CANCELLED`)             |  `404`  |   `404`    |          ✓           |        `404`        |    ✓    |
| `POST /api/events`                                         |  `401`  |   `403`    |          ✓           |          ✓          |    ✓    |
| `PATCH /api/events/{id}`                                   |  `401`  |   `403`    |          ✓           |        `403`        |    ✓    |
| `DELETE /api/events/{id}` (`registered_count == 0`)        |  `401`  |   `403`    |          ✓           |        `403`        |    ✓    |
| `POST /api/events/{id}/image`                              |  `401`  |   `403`    |          ✓           |        `403`        |    ✓    |

## 8. Criterios de aceptación (EARS)

Cada criterio tiene al menos un test cuyo nombre incluye su ID (R1.5, R1.9).

| ID            | Criterio (Notación EARS en español)                                                                                                                                                                                                                                                                                                 | Reglas                  |
| ------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------- |
| **EVT-AC-01** | Cuando un usuario con rol `ORGANIZER` o `ADMIN` envía `POST /api/events` con datos válidos, el sistema debe crear el evento asignando `organizer_id` al usuario autenticado, `status = "DRAFT"` por defecto (o `"PUBLISHED"` si se solicitó), `registered_count = 0`, `available_capacity = total_capacity`, `image_urls = null` y responder `201` con `EventRead`. | EVT-BR-02, EVT-BR-04    |
| **EVT-AC-02** | Si una petición a `POST /api/events`, `PATCH /api/events/{id}`, `DELETE /api/events/{id}` o `POST /api/events/{id}/image` carece de token válido, entonces el sistema debe responder `401` con `"No autenticado o sesión expirada"` y `WWW-Authenticate: Bearer`; y si proviene de un usuario con rol `ATTENDEE`, entonces el sistema debe responder `403` con `"No tienes permisos para realizar esta acción"`. | EVT-BR-02               |
| **EVT-AC-03** | Si el cuerpo de `POST /api/events` o `PATCH /api/events/{id}` incluye `organizer_id`, `registered_count`, `available_capacity`, `image_urls` u otro campo no permitido, o si en `POST /api/events` se solicita `status = "CANCELLED"`, entonces el sistema debe rechazar la petición con código `422`, `detail = "Error de validación en los datos enviados"` y `errors[].message` en español. | EVT-BR-02, EVT-BR-03, EVT-BR-10 |
| **EVT-AC-04** | Si un cliente envía `title` fuera de 3–160 caracteres tras `trim`, `description` fuera de 10–5000 caracteres tras `trim`, `total_capacity` fuera de 1..100000 o un body vacío `{}` en `PATCH /api/events/{id}`, entonces el sistema debe responder `422` con `detail = "Error de validación en los datos enviados"` y el mensaje específico en español en `errors[].message`. | EVT-BR-04, EVT-BR-10    |
| **EVT-AC-05** | Cuando un visitante Anónimo o un usuario `ATTENDEE` consulta `GET /api/events`, el sistema debe devolver únicamente eventos con `status = "PUBLISHED"` ordenados por `date ASC, id ASC` dentro del sobre de paginación `PLAT-BR-05`; y si filtra con `status=DRAFT` o `status=CANCELLED`, debe devolver `200` con `items: []` y `total: 0`. | EVT-BR-01, EVT-BR-06    |
| **EVT-AC-06** | Si un visitante Anónimo o un usuario `ATTENDEE` solicita `GET /api/events/{id}` de un evento en estado `DRAFT` o `CANCELLED` (o un `ORGANIZER` solicita un evento `DRAFT` o `CANCELLED` perteneciente a otro organizador), entonces el sistema debe responder `404` con `detail = "Evento no encontrado"`.                               | EVT-BR-01               |
| **EVT-AC-07** | Cuando un `ORGANIZER` consulta `GET /api/events` o `GET /api/events/{id}`, el sistema debe permitirle ver todos los eventos `PUBLISHED` más sus propios eventos en estado `DRAFT` o `CANCELLED`; y cuando envía `GET /api/events?mine=true`, el sistema debe devolver únicamente los eventos donde `organizer_id == current_user.id`.       | EVT-BR-01               |
| **EVT-AC-08** | Si un visitante Anónimo solicita `GET /api/events?mine=true`, entonces el sistema debe responder `401`; y si un usuario `ATTENDEE` solicita `GET /api/events?mine=true`, entonces el sistema debe responder `403` con `"No tienes permisos para realizar esta acción"`.                                                                    | EVT-BR-01               |
| **EVT-AC-09** | Cuando un `ADMIN` consulta `GET /api/events` o `GET /api/events/{id}`, el sistema debe permitirle ver todos los eventos de cualquier organizador en cualquier estado (`DRAFT`, `PUBLISHED`, `CANCELLED`).                                                                                                                            | EVT-BR-01               |
| **EVT-AC-10** | Cuando el `ORGANIZER` propietario o un `ADMIN` envía `PATCH /api/events/{id}` con cambios válidos, el sistema debe actualizar el evento y `updated_at`, conservando intacto el `organizer_id` original incluso cuando quien edita es el `ADMIN`.                                                                                           | EVT-BR-02               |
| **EVT-AC-11** | Si un `ORGANIZER` intenta editar (`PATCH`), cambiar estado, subir imagen (`POST /image`) o eliminar (`DELETE`) un evento cuyo `organizer_id` pertenece a otro usuario, entonces el sistema debe rechazar la petición con código `403` y `detail = "No tienes permisos para realizar esta acción"`.                                         | EVT-BR-02               |
| **EVT-AC-12** | Cuando el `ORGANIZER` propietario o un `ADMIN` solicita en `PATCH /api/events/{id}` las transiciones `DRAFT → PUBLISHED`, `DRAFT → CANCELLED` o `PUBLISHED → CANCELLED` (o mantiene el estado actual en `DRAFT` o `PUBLISHED`), el sistema debe aplicar la transición y responder `200` con el nuevo `status`.                             | EVT-BR-03               |
| **EVT-AC-13** | Si se intenta cambiar el estado de un evento de `PUBLISHED` a `DRAFT` mediante `PATCH /api/events/{id}`, entonces el sistema debe rechazar la petición con código `409` y `detail = "No se puede regresar un evento publicado a borrador"`.                                                                                                | EVT-BR-03               |
| **EVT-AC-14** | Mientras un evento se encuentre en estado `CANCELLED`, si cualquier usuario intenta editar sus campos, cambiar su estado o subir una imagen, entonces el sistema debe rechazar la petición con código `409` y `detail = "Un evento cancelado no puede cambiar de estado ni editarse"`.                                                      | EVT-BR-03               |
| **EVT-AC-15** | El sistema debe exponer en toda respuesta `EventRead` los campos `total_capacity`, `registered_count` y `available_capacity = max(0, total_capacity - registered_count)` calculados en el backend; y si en `PATCH /api/events/{id}` se solicita un `total_capacity < registered_count`, entonces debe responder `409` con `detail = "No se puede reducir la capacidad total por debajo del número de inscritos actuales"`. | EVT-BR-04               |
| **EVT-AC-16** | El sistema debe almacenar `date`, `created_at` y `updated_at` en PostgreSQL como `TIMESTAMP WITH TIME ZONE` en UTC, normalizar entradas con zona horaria a UTC y serializar las tres fechas en formato ISO 8601 terminado en `Z` sin rechazar fechas pasadas en pruebas deterministas.                                                     | EVT-BR-05               |
| **EVT-AC-17** | Cuando un cliente envía `GET /api/events?search=<texto>`, el sistema debe recortar espacios exteriores, buscar coincidencias parciales insensibles a mayúsculas/minúsculas sobre `title` escapando `%`, `_` y `\` sobre el índice GIN `ix_events_title_trgm` (`gin_trgm_ops`), ignorar `search` si queda vacío tras `trim` y responder `422` si supera 100 caracteres. | EVT-BR-06               |
| **EVT-AC-18** | Cuando el `ORGANIZER` propietario o un `ADMIN` envía `DELETE /api/events/{id}` para un evento con `registered_count == 0`, el sistema debe eliminar físicamente el evento de PostgreSQL, borrar del disco sus tres variantes WebP si tenía imagen, invalidar la caché Redis y responder `204 No Content`.                                  | EVT-BR-07               |
| **EVT-AC-19** | Si se envía `DELETE /api/events/{id}` para un evento que tiene asistentes inscritos (`registered_count > 0`), entonces el sistema debe impedir el borrado físico y responder `409` con `detail = "No se puede eliminar un evento con asistentes inscritos; cancélalo en su lugar"`.                                                         | EVT-BR-07               |
| **EVT-AC-20** | Cuando el `ORGANIZER` propietario o un `ADMIN` sube una imagen válida (`JPEG`, `PNG` o `WEBP` de hasta 5 MB) a `POST /api/events/{id}/image`, el sistema debe aplicar `exif_transpose`, eliminar los metadatos EXIF, generar síncronamente las tres variantes WebP (`400w`, `800w`, `1200w`) sin ampliar imágenes cuyo ancho original sea menor al objetivo, guardarlas en `{MEDIA_ROOT}/events/` y responder `200` con `image_urls` poblado. | EVT-BR-08               |
| **EVT-AC-21** | Cuando se reemplaza la imagen de un evento que ya tenía `image_key` mediante `POST /api/events/{id}/image`, el sistema debe generar un nuevo `image_key` UUID, actualizar `image_urls` con las nuevas rutas y eliminar del disco las tres variantes WebP correspondientes al `image_key` anterior.                                          | EVT-BR-08               |
| **EVT-AC-22** | Si en `POST /api/events/{id}/image` se sube un archivo vacío (`0` bytes), un archivo corrupto o un archivo cuyo formato binario real no sea `JPEG`, `PNG` ni `WEBP` (aunque su nombre o `Content-Type` aparenten serlo), entonces el sistema debe responder `400` con `"El archivo de imagen está vacío"` o `"Formato de imagen no soportado. Usa JPEG, PNG o WebP"`; y si supera 5 MB, debe responder `413` con `"La imagen no debe superar los 5 MB"`. | EVT-BR-08               |
| **EVT-AC-23** | Cuando se consulta `GET /api/events` o `GET /api/events/{id}` repetidamente con los mismos parámetros y ámbito de rol (`scope`), el sistema debe servir la respuesta desde la caché Redis; y cuando ocurre cualquier escritura (`POST`, `PATCH`, `DELETE` o subida de imagen), el sistema debe invalidar el prefijo `events:` para que la siguiente lectura refleje los datos actualizados. | EVT-BR-09               |
| **EVT-AC-24** | Si Redis no está disponible o lanza un error durante `GET /api/events`, `GET /api/events/{id}` o durante la invalidación posterior a una escritura, entonces el sistema debe degradar de forma transparente sin propagar error y responder desde PostgreSQL; además, la caché debe aislar las claves por `scope` para nunca entregar borradores de un organizador a un usuario Anónimo o `ATTENDEE`. | EVT-BR-09               |
| **EVT-AC-25** | El sistema debe crear en PostgreSQL la tabla `events` mediante la migración Alembic `0003_create_events` con las restricciones `CHECK (status IN ('DRAFT', 'PUBLISHED', 'CANCELLED'))`, `CHECK (total_capacity >= 1)`, `FOREIGN KEY (organizer_id) REFERENCES users(id)` y los índices `ix_events_organizer_id`, `ix_events_status`, `ix_events_date` e `ix_events_title_trgm` (`GIN gin_trgm_ops`), y exponer todos los endpoints y esquemas en `/api/openapi.json`. | EVT-BR-04, EVT-BR-06, EVT-BR-10 |
| **EVT-AC-26** | Cuando el frontend invoca las acciones de `useEventStore`, el store debe consumir `/api/events` actualizando el listado paginado, los filtros (`page`, `size`, `search`, `status`, `mine`), `currentEvent` y `isLoading`, y sus DTOs en `types/api.ts` deben coincidir con `EventRead` sin recalcular `available_capacity` en el cliente. | EVT-BR-04, EVT-BR-10    |
| **EVT-AC-27** | El componente `EventCard.vue` debe mostrar el título, fecha formateada, estado traducido al español (`Borrador`, `Publicado`, `Cancelado`), los cupos disponibles entregados por la API (`event.available_capacity` / `event.total_capacity`) y, cuando `image_urls` exista, una etiqueta `<img>` con `srcset` (`400w`, `800w`, `1200w`), `sizes`, `loading="lazy"` y `decoding="async"`, sin usar `v-html`. | EVT-BR-04, EVT-BR-08, EVT-BR-10 |
| **EVT-AC-28** | Cuando un usuario navega a `/` (`EventsListView.vue`), el frontend debe mostrar estados de carga (`BaseSkeleton`/`BaseSpinner`), permitir buscar por nombre (`search`), cambiar de página, filtrar por estado o "Mis eventos" cuando el rol sea `ORGANIZER` o `ADMIN`, y mostrar el enlace de creación de evento solo a `ORGANIZER` y `ADMIN`. | EVT-BR-01, EVT-BR-06, EVT-BR-10 |
| **EVT-AC-29** | Cuando un usuario navega a `/events/:id` (`EventDetailView.vue`), el frontend debe mostrar el detalle completo del evento con su imagen WebP responsiva, estado en español y cupos desde la API; mostrar los controles de editar, cambiar estado, subir imagen y eliminar únicamente al `ORGANIZER` dueño o `ADMIN`; y no mostrar el botón de inscripción a `ORGANIZER` ni `ADMIN`. | EVT-BR-01, EVT-BR-02, EVT-BR-10 |
| **EVT-AC-30** | Cuando un `ORGANIZER` o `ADMIN` navega a `/events/new` o `/events/:id/edit` (`EventFormView.vue`), la vista debe cargar `EventForm.vue` de forma diferida mediante `defineAsyncComponent`, permitir crear o actualizar el evento y subir su imagen mostrando errores de validación o conflicto en español, mientras que los guards del router redirigen a `/login` a usuarios no autenticados y a `/` a usuarios con rol `ATTENDEE`. | EVT-BR-02, EVT-BR-08, EVT-BR-10 |

## 9. Casos límite

- **Búsqueda con caracteres comodín SQL (`%`, `_`, `\`):** Buscar `search=100%` o `search=a_b` escapa los caracteres antes de construir el patrón `ILIKE`, buscando literalmente el símbolo `%` o `_` sin coincidir con todos los títulos.
- **Búsqueda compuesta solo por espacios (`search="   "`):** Tras `.strip()` queda vacía `""`, por lo que se ignora y devuelve el listado paginado normal sin error.
- **Página solicitada fuera de rango (`page > pages`):** Devuelve `200 OK` con `items: []`, `total` real y `pages` calculado conforme a `PLAT-BR-05`.
- **Imagen pequeña (p. ej. `300x200` px) subida a `POST /api/events/{id}/image`:** Las tres variantes (`400w`, `800w`, `1200w`) se generan en WebP manteniendo el tamaño `300x200` px sin ampliar (`no upscaling`).
- **Imagen con metadatos EXIF de cámara/GPS y rotación (Orientation = 6):** Pillow aplica `ImageOps.exif_transpose` dejando la imagen enderezada y guarda las tres variantes WebP sin metadatos EXIF ni GPS (R5.8).
- **Archivo `.txt` o `.exe` renombrado a `foto.jpg` con `Content-Type: image/jpeg`:** Pillow falla al identificar/cargar la imagen y el endpoint devuelve `400` con `"Formato de imagen no soportado. Usa JPEG, PNG o WebP"`.
- **Imagen PNG con transparencia (modo `RGBA` o `P`):** Se convierte preservando la transparencia (`RGBA`) a WebP sin fallar por modo de color.
- **Transición idempotente (`PATCH` enviando `status: "PUBLISHED"` cuando ya está en `PUBLISHED`):** Es válida y permite que el formulario de edición envíe el estado actual junto con otros campos modificados sin producir `409`.
- **Intento de `PATCH` o subida de imagen sobre un evento `CANCELLED`:** Aunque los datos del formulario sean válidos y el usuario sea el dueño o `ADMIN`, el servicio comprueba primero el estado actual y corta con `409` (`"Un evento cancelado no puede cambiar de estado ni editarse"`).
- **Edición de un evento por un `ADMIN`:** El `organizer_id` sigue siendo el del `ORGANIZER` original; el `ORGANIZER` original no pierde la propiedad de su evento.

## 10. Seguridad y privacidad

- **Cadena única de dependencias (R5.2):** En los endpoints de escritura (`POST`, `PATCH`, `DELETE`, `POST /image`), la verificación sigue estrictamente el orden: token presente → firma HS256 → expiración → usuario existente → usuario activo (`401`) → rol permitido (`403`) → propiedad del evento (`403` si `current_user.role != ADMIN` y `event.organizer_id != current_user.id`).
- **No filtración de borradores ni eventos cancelados ajenos (R5.8):** Cuando un usuario Anónimo, `ATTENDEE` u otro `ORGANIZER` consulta `GET /api/events/{id}` de un evento `DRAFT` o `CANCELLED` ajeno, recibe `404 "Evento no encontrado"` (no `403`), evitando enumerar borradores privados por ID. En cambio, en las operaciones de escritura (`PATCH`, `DELETE`, `POST /image`), si el evento existe y el usuario autenticado no es dueño ni `ADMIN`, recibe `403 "No tienes permisos para realizar esta acción"` (R5.6).
- **Privacidad en imágenes (R5.8):** Todas las imágenes subidas pierden sus metadatos EXIF (ubicación GPS, serie del dispositivo, autor) al recodificarse a WebP y se renombran con un UUID v4 aleatorio, sin exponer jamás el nombre de archivo original del usuario.
- **Aislamiento de caché por rol (R5.8):** Las claves de caché Redis incluyen el `scope` del solicitante (`public`, `org:{id}`, `admin:{id}`) para que la respuesta cacheada de un organizador o administrador nunca se entregue a un visitante anónimo o asistente.
- **Prevención de XSS (R5.9):** `title` y `description` se interpolan siempre con `{{ ... }}` en Vue; queda prohibido el uso de `v-html`.

## 11. Dependencias e integración entre dominios

- **Con `platform` (Dominio 0):** Reutiliza `PaginationParams`, `PaginatedResponse`, `build_paginated_response`, `UTCDateTime`, `CacheClient`, `settings.media_root`, los manejadores globales de excepciones en español y la ubicación `/api/media/` del gateway Nginx.
- **Con `auth` (Dominio 1):** Reutiliza `User`, `UserRole`, `bearer_scheme`, `get_current_user` y `require_roles`, añadiendo en `events` la dependencia `get_optional_current_user` (para lecturas con Bearer opcional) y la validación de propiedad del evento.
- **Hacia `sessions` (Dominio 3):** La tabla `events` es la entidad padre (`Session.event_id -> events.id ON DELETE CASCADE`). Queda establecida la frontera de que las sesiones de un evento deberán celebrarse en la fecha UTC del evento (`session.start_time >= event.date`) y que no se podrán crear ni editar sesiones de un evento en estado `CANCELLED`.
- **Hacia `registrations` (Dominio 4):** `EventRead` ya incluye `registered_count` y `available_capacity` a través de `get_registered_count(session, event_id)`, y la tabla `events` queda lista para bloquearse con `SELECT ... FOR UPDATE` durante la inscripción atómica e invalidar el prefijo `events:` en Redis tras cada inscripción.

## 12. Decisiones resueltas y pendientes

### 12.1. Decisiones resueltas

Todas las decisiones bloqueantes (1–10) fueron consultadas y resueltas con el usuario el **2026-10-31**:

| Fecha      | Decisión                                  | Resolución adoptada                                                                                                                                                                     | Motivo                                                                                                   |
| ---------- | ----------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| 2026-10-31 | #1 Visibilidad pública y por rol          | Opción A: `GET` con Bearer opcional; Anónimo/`ATTENDEE` solo `PUBLISHED` (`404` en detalle de `DRAFT`/`CANCELLED`); `ORGANIZER` ve `PUBLISHED` + propios (`mine=true` disponible); `ADMIN` ve todos. | Escaparate público para asistentes y aislamiento de borradores (R5.3, R5.8).                             |
| 2026-10-31 | #2 Propiedad y administración             | Opción A: Crean `ORGANIZER` y `ADMIN` (`organizer_id = current_user.id` automático); modifican dueño o `ADMIN` (`403` si ajeno); `ADMIN` conserva `organizer_id` original al editar.    | Cumple la cadena R5.2 y R5.3 sin transferencia compleja de autoría (R4.5).                               |
| 2026-10-31 | #3 Máquina de estados                     | Opción A: Alta en `DRAFT` (o `PUBLISHED`); transiciones `DRAFT → PUBLISHED`, `DRAFT → CANCELLED`, `PUBLISHED → CANCELLED`; `PUBLISHED → DRAFT` y editar `CANCELLED` devuelven `409`.   | Máquina de estados dirigida, predecible y con `CANCELLED` terminal e inmutable (R3.4).                   |
| 2026-10-31 | #4 Capacidad y cupos disponibles          | Opción A: `total_capacity` (`1..100000`), `EventRead` expone `total_capacity`, `registered_count` y `available_capacity` desde el backend; reducir `< registered_count` devuelve `409`. | Cumple R2.5 (el frontend nunca resta cupos) y prepara el terreno para `registrations`.                   |
| 2026-10-31 | #5 Fechas del evento                      | Opción A: Un único campo `date: UTCDateTime` (`TIMESTAMP WITH TIME ZONE` UTC, ISO 8601 `Z`), sin bloqueo contra el reloj actual en schema/BD; frontera documentada para `sessions`.     | Fiel al diagrama ER v1.1 §3.4 y garantiza tests 100 % deterministas (R3.7).                              |
| 2026-10-31 | #6 Búsqueda trigrama y filtros            | Opción A: `search` (`trim`, máx. 100) con `ILIKE '%<escaped>%'` + índice GIN `ix_events_title_trgm` (`gin_trgm_ops`), combinable con `page`, `size`, `status` y `mine`.                 | Cumple "búsqueda por nombre o parte del nombre" sobre PostgreSQL con `pg_trgm` (R3.6).                   |
| 2026-10-31 | #7 Eliminación vs Cancelación             | Opción A: `DELETE /api/events/{id}` realiza borrado físico (`204`) + limpieza WebP si `registered_count == 0`, y rechaza con `409` si `registered_count > 0`.                           | Completa el CRUD protegiendo la integridad cuando existan asistentes inscritos.                          |
| 2026-10-31 | #8 Imágenes WebP con Pillow               | Opción A: `POST /api/events/{id}/image` (`file`, máx. 5 MB → `413`), Pillow valida JPEG/PNG/WebP reales (`400`), `exif_transpose` + sin EXIF, 3 variantes `400w`/`800w`/`1200w` sin upscaling, `image_urls` en `EventRead`. | Implementa el diseño exacto de la Arquitectura v1.1 §3.8 y R2.3/R5.8.                                    |
| 2026-10-31 | #9 Caché Redis e invalidación             | Opción A: Cachear listado y detalle bajo `events:` con `scope` en la clave (`TTL=60s`), invalidar con `invalidate_prefix("events:")` en toda escritura y degradar a PostgreSQL si cae. | Cumple el bonus obligatorio de caching y R4.4 sin riesgo de fuga entre roles.                            |
| 2026-10-31 | #10 Contrato de API y rutas/componentes Vue | Opción A: Orden `date ASC, id ASC`; `PATCH` parcial; rutas `/`, `/events/new`, `/events/:id`, `/events/:id/edit`; `EventCard.vue` y `EventForm.vue` con `defineAsyncComponent`.         | Alinea el contrato OpenAPI con el frontend y cubre el bonus de lazy loading de componentes pesados.      |

### 12.2. Decisiones pendientes

Ninguna.

## 13. Fuera de alcance

- Creación, listado, edición o borrado de sesiones de un evento (`specs/sessions/`).
- Inscripción o anulación de inscripción de asistentes y consulta de "Mis inscripciones" (`specs/registrations/`).
- Almacenamiento de imágenes en servicios cloud externos (S3, GCS) o procesamiento en segundo plano con Celery/workers (prohibido por R4.3).
- Eliminación aislada de la imagen de un evento sin reemplazarla o sin eliminar el evento.
- Búsqueda por texto completo sobre `description` (el requisito de la prueba y la arquitectura v1.1 §3.4 especifican búsqueda por nombre o parte del nombre sobre `title`).

## 14. Matriz de trazabilidad (`EVT-BR-NN` ↔ `EVT-AC-NN` ↔ Tests en `tasks.md`)

| Regla de negocio | Criterios de aceptación (`EARS`)                     | Tareas TDD asociadas (`specs/events/tasks.md`)              |
| ---------------- | ---------------------------------------------------- | ----------------------------------------------------------- |
| **EVT-BR-01**    | `EVT-AC-05`, `EVT-AC-06`, `EVT-AC-07`, `EVT-AC-08`, `EVT-AC-09`, `EVT-AC-28`, `EVT-AC-29` | `B5`, `B6`, `B7`, `B8`, `B9`, `F4`, `F5` |
| **EVT-BR-02**    | `EVT-AC-01`, `EVT-AC-02`, `EVT-AC-03`, `EVT-AC-10`, `EVT-AC-11`, `EVT-AC-29`, `EVT-AC-30` | `B1`, `B2`, `B3`, `B10`, `B11`, `F3`, `F5`, `F6` |
| **EVT-BR-03**    | `EVT-AC-03`, `EVT-AC-12`, `EVT-AC-13`, `EVT-AC-14`   | `B3`, `B12`, `B13`, `B14`                                   |
| **EVT-BR-04**    | `EVT-AC-01`, `EVT-AC-04`, `EVT-AC-15`, `EVT-AC-25`, `EVT-AC-26`, `EVT-AC-27` | `B1`, `B4`, `B15`, `B25`, `F1`, `F2`      |
| **EVT-BR-05**    | `EVT-AC-16`                                          | `B16`                                                       |
| **EVT-BR-06**    | `EVT-AC-05`, `EVT-AC-17`, `EVT-AC-25`, `EVT-AC-28`   | `B5`, `B17`, `B25`, `F4`                                    |
| **EVT-BR-07**    | `EVT-AC-18`, `EVT-AC-19`                             | `B18`, `B19`                                                |
| **EVT-BR-08**    | `EVT-AC-20`, `EVT-AC-21`, `EVT-AC-22`, `EVT-AC-27`, `EVT-AC-30` | `B20`, `B21`, `B22`, `F2`, `F3`, `F6`            |
| **EVT-BR-09**    | `EVT-AC-23`, `EVT-AC-24`                             | `B23`, `B24`                                                |
| **EVT-BR-10**    | `EVT-AC-03`, `EVT-AC-04`, `EVT-AC-25`, `EVT-AC-26`, `EVT-AC-27`, `EVT-AC-28`, `EVT-AC-29`, `EVT-AC-30` | `B3`, `B4`, `B25`, `F1..F6`, `V1..V4` |

## 15. Historial

| Versión | Fecha      | Cambio                                                                                                              |
| ------- | ---------- | ------------------------------------------------------------------------------------------------------------------- |
| 0.1     | 2026-10-31 | Borrador inicial completo del dominio `events` (`EVT`) con las 10 decisiones funcionales resueltas por el usuario.  |
| 1.0     | 2026-10-31 | Aprobación explícita del usuario ("Apruebo la spec de events, proceda"): Borrador → Aprobada.                       |
| 1.0     | 2026-10-31 | Autorización del usuario para iniciar la implementación: Aprobada → En implementación (Paso 6, TDD).                |
| 1.0     | 2026-10-31 | Implementación TDD completa (B1..B25, F1..F6) y validación del `reviewer` (`¿pasa? sí`, 30/30 criterios `EVT-AC-01..30` verificados): `En implementación → Implementada`. |
| 1.0     | 2026-11-01 | Armonización de versiones con la entrega v1.0.0 por decisión del usuario (`DLV-D3`): se mantiene la versión `1.0`; sin cambios de contenido, reglas, criterios ni estado. |
