# Plan técnico: Gestión de Eventos y Catálogo (`events`)

| Campo                  | Valor                          |
| ---------------------- | ------------------------------ |
| **ID del dominio**     | `EVT`                          |
| **Spec de referencia** | `specs/events/spec.md` v1.0    |
| **Fecha**              | 2026-10-31                     |

> Este plan describe **cómo** se implementa `specs/events/spec.md`. No añade comportamiento: si algo no está en `spec.md`, primero se agrega allí (R1.1, R1.5). Identificadores en inglés (Principio 6).

## 1. Modelo de datos y migraciones

### 1.1. Tabla `events` y modelo `Event`

Se define en `backend/app/events/models.py` usando `SQLModel` y el enumerado `EventStatus(str, Enum)` con valores `"DRAFT"`, `"PUBLISHED"` y `"CANCELLED"` (R6.1).

| Columna          | Tipo SQL                   | Restricciones (`PK`, `FK`, `CHECK`, `DEFAULT`)                                                                 |
| ---------------- | -------------------------- | -------------------------------------------------------------------------------------------------------------- |
| `id`             | `INTEGER` / `SERIAL`       | `PRIMARY KEY`, autoincremental.                                                                                |
| `organizer_id`   | `INTEGER`                  | `NOT NULL`, `FOREIGN KEY (organizer_id) REFERENCES users(id) ON DELETE RESTRICT`.                              |
| `title`          | `VARCHAR(160)`             | `NOT NULL`; 3–160 caracteres tras `trim`.                                                                      |
| `description`    | `TEXT`                     | `NOT NULL`; 10–5000 caracteres tras `trim`.                                                                    |
| `date`           | `TIMESTAMP WITH TIME ZONE` | `NOT NULL`; almacenado en UTC.                                                                                 |
| `total_capacity` | `INTEGER`                  | `NOT NULL`, `CHECK (total_capacity >= 1)` (`ck_events_total_capacity_positive`).                               |
| `status`         | `VARCHAR(20)`              | `NOT NULL`, `DEFAULT 'DRAFT'`, `CHECK (status IN ('DRAFT', 'PUBLISHED', 'CANCELLED'))` (`ck_events_status`).   |
| `image_key`      | `VARCHAR(64)`              | `NULL`; almacena únicamente el UUID v4 hexadecimal de 32 caracteres (sin ruta ni extensión).                   |
| `created_at`     | `TIMESTAMP WITH TIME ZONE` | `NOT NULL`, `DEFAULT now()`; UTC.                                                                              |
| `updated_at`     | `TIMESTAMP WITH TIME ZONE` | `NOT NULL`, `DEFAULT now()`; UTC; actualizado en la aplicación (`utc_now()`) en cada `PATCH` o subida de imagen. |

### 1.2. Relaciones futuras con `sessions` y `registrations`

- **Con `users` (Dominio 1):** `events.organizer_id -> users.id` (`ON DELETE RESTRICT`; en `users` no existe borrado físico, sino desactivación lógica con `is_active`).
- **Con `sessions` (Dominio 3):** La futura tabla `sessions` tendrá `event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE`, de modo que si se elimina físicamente un evento sin inscritos (`registered_count == 0`), sus sesiones se eliminen en cascada.
- **Con `registrations` (Dominio 4):** La futura tabla `registrations` tendrá `event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE RESTRICT`. El servicio de eventos define desde ya la función `get_registered_count(session: Session, event_id: int) -> int` (que devuelve `0` mientras no exista la tabla `registrations`, o consulta el `COUNT(*)` cuando exista) y deja la fila de `events` lista para `SELECT ... FOR UPDATE` en la transacción de inscripción (R5.4).

### 1.3. Migración Alembic e índices (`pg_trgm`)

- **Archivo de migración:** `backend/migrations/versions/0003_create_events.py` con `revision = "0003_create_events"` y `down_revision = "0002_create_users"`.
- **Extensión `pg_trgm`:** Ya fue habilitada en `0001_enable_pg_trgm.py` (`CREATE EXTENSION IF NOT EXISTS pg_trgm`).
- **Índices creados en `0003_create_events.py`:**
  1. `ix_events_organizer_id`: B-Tree sobre `(organizer_id)` para acelerar `mine=true` y las consultas de eventos propios del `ORGANIZER`.
  2. `ix_events_status`: B-Tree sobre `(status)` para el filtrado por estado (`PUBLISHED`, `DRAFT`, `CANCELLED`).
  3. `ix_events_date`: B-Tree sobre `(date, id)` o `(date)` para la ordenación `ORDER BY date ASC, id ASC`.
  4. `ix_events_title_trgm`: índice **GIN** con la clase de operadores `gin_trgm_ops` de `pg_trgm` sobre `title`:
     ```python
     op.create_index(
         "ix_events_title_trgm",
         "events",
         ["title"],
         unique=False,
         postgresql_using="gin",
         postgresql_ops={"title": "gin_trgm_ops"},
     )
     ```
     *(Verificado con `context7-mcp` sobre la documentación oficial de SQLAlchemy `Index(..., postgresql_using="gin", postgresql_ops=...)`).*
- **Registro en `migrations/env.py` y `app/main.py`:** Se importa `app.events.models` para que tanto Alembic como el truncado de tablas de `tests/conftest.py` incluyan `events`.

## 2. Backend

### 2.1. Estructura de módulos del dominio `events`

```text
backend/app/
├── events/
│   ├── __init__.py
│   ├── models.py           # EventStatus(str, Enum), Event(SQLModel, table=True)
│   ├── schemas.py          # EventImageUrls, EventCreate, EventUpdate, EventRead, EventListParams
│   ├── dependencies.py     # get_optional_current_user, require_event_creator, get_owned_or_admin_event
│   ├── images.py           # process_and_store_event_image, delete_event_image_files, build_image_urls
│   ├── service.py          # list_events, get_event_for_actor, create_event, update_event, delete_event, update_event_image, get_registered_count
│   └── router.py           # GET/POST /api/events, GET/PATCH/DELETE /api/events/{id}, POST /api/events/{id}/image
└── core/
    └── config.py           # añade cache_events_ttl_seconds: int = 60 y max_event_image_bytes: int = 5 * 1024 * 1024
```

`app/main.py` registra `events.router` con prefijo `/api/events` y `tags=["events"]`.

### 2.2. Cadena de dependencias y autorización (R5.2, R5.3)

Se extiende el patrón de `app/auth/dependencies.py` manteniendo una única cadena de dependencias que corta en el primer fallo:

1. **`get_optional_current_user(credentials = Depends(bearer_scheme), session = Depends(get_session)) -> User | None`:**
   - Si no hay cabecera `Authorization`: devuelve `None` (visitante Anónimo).
   - Si hay cabecera `Authorization`: ejecuta exactamente la misma validación que `get_current_user` (esquema `Bearer`, firma HS256, expiración, usuario existente en BD y `is_active == True`); si falla cualquiera de esos pasos, corta con `401` (`"No autenticado o sesión expirada"` y `WWW-Authenticate: Bearer`).
2. **`require_event_creator = require_roles(UserRole.ORGANIZER, UserRole.ADMIN)`:**
   - Para `POST /api/events`: exige token válido (`401`) y rol `ORGANIZER` o `ADMIN` (`403` si es `ATTENDEE`).
3. **`get_owned_or_admin_event(event_id: int, current_user: User = Depends(require_event_creator), session: Session = Depends(get_session)) -> Event`:**
   - Resuelve primero `current_user` validando token (`401`) y rol `ORGANIZER`/`ADMIN` (`403` para `ATTENDEE`).
   - Busca `event = session.get(Event, event_id)`; si no existe, lanza `404` (`"Evento no encontrado"`).
   - Si `current_user.role != UserRole.ADMIN` y `event.organizer_id != current_user.id`, lanza `403` (`"No tienes permisos para realizar esta acción"`).
   - Devuelve la instancia `Event` lista para `PATCH`, `DELETE` o `POST /image`.

### 2.3. Schemas de entrada y salida (R5.5)

Definidos en `backend/app/events/schemas.py`:

- **`EventImageUrls`:** `w400: str`, `w800: str`, `w1200: str`.
- **`EventCreate`:**
  - `model_config = ConfigDict(extra="forbid")` (rechaza `organizer_id`, `registered_count`, `available_capacity`, `image_urls`, etc. con `422` y `"Este campo no está permitido"`).
  - `title: str` (`strip()`, `min_length=3`, `max_length=160`).
  - `description: str` (`strip()`, `min_length=10`, `max_length=5000`).
  - `date: UTCDateTime`.
  - `total_capacity: int = Field(ge=1, le=100000)`.
  - `status: Literal[EventStatus.DRAFT, EventStatus.PUBLISHED] = EventStatus.DRAFT` (enviar `"CANCELLED"` produce `422`).
- **`EventUpdate`:**
  - `model_config = ConfigDict(extra="forbid")`.
  - `title: str | None = None` (`strip()` si se envía, `3..160`).
  - `description: str | None = None` (`strip()` si se envía, `10..5000`).
  - `date: UTCDateTime | None = None`.
  - `total_capacity: int | None = Field(default=None, ge=1, le=100000)`.
  - `status: EventStatus | None = None`.
  - `@model_validator(mode="after")`: verifica `bool(self.model_fields_set)`; si el body está vacío `{}` o todos los campos enviados son `None`, lanza `ValueError("Debes indicar al menos un campo para actualizar")` → `422`.
- **`EventRead`:**
  - `id: int`, `title: str`, `description: str`, `date: UTCDateTime`, `total_capacity: int`, `registered_count: int`, `available_capacity: int`, `status: EventStatus`, `organizer_id: int`, `image_urls: EventImageUrls | None`, `created_at: UTCDateTime`, `updated_at: UTCDateTime`.
- **`EventListParams`:**
  - Dependencia de query que compone `page: int = Query(1, ge=1)`, `size: int = Query(10, ge=1, le=50)`, `search: str | None = Query(default=None)`, `status: EventStatus | None = Query(default=None)`, `mine: bool = Query(default=False)`.
  - Normaliza `search = search.strip() if search is not None else None`; si `search` supera `100` caracteres tras `strip()`, lanza `RequestValidationError` (`string_too_long`, `max_length=100`) para que el handler global devuelva `422` en español. Si queda `""`, lo convierte en `None`.

### 2.4. Lógica de negocio: búsqueda, máquina de estados y capacidad

1. **Escape y búsqueda `ILIKE` con `pg_trgm`:**
   ```python
   def escape_like(term: str) -> str:
       return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
   ```
   Se filtra con `col(Event.title).ilike(f"%{escape_like(search)}%", escape="\\")`, que PostgreSQL resuelve mediante Bitmap Index Scan sobre `ix_events_title_trgm`.
2. **Visibilidad en listado y detalle:**
   - Si `params.mine` es `True`:
     - Si `actor is None` → `401` (`"No autenticado o sesión expirada"`).
     - Si `actor.role == UserRole.ATTENDEE` → `403` (`"No tienes permisos para realizar esta acción"`).
     - Si `actor.role in {UserRole.ORGANIZER, UserRole.ADMIN}` → filtra `Event.organizer_id == actor.id` (y `Event.status == params.status` si se indicó).
   - Si `params.mine` es `False`:
     - Para `Anónimo` o `ATTENDEE`: si `params.status is not None and params.status != EventStatus.PUBLISHED`, devuelve inmediatamente página vacía (`items=[], total=0, pages=0`); en caso contrario filtra `Event.status == EventStatus.PUBLISHED`.
     - Para `ORGANIZER`: filtra `or_(Event.status == EventStatus.PUBLISHED, Event.organizer_id == actor.id)`, más `Event.status == params.status` si se indicó.
     - Para `ADMIN`: sin restricción de propietario; filtra `Event.status == params.status` si se indicó.
   - En `GET /api/events/{id}`: si el evento no existe, o si `event.status != EventStatus.PUBLISHED` y el actor no es `ADMIN` ni el `ORGANIZER` dueño (`actor.id == event.organizer_id`), lanza `404` (`"Evento no encontrado"`).
3. **Máquina de estados en `update_event`:**
   - Primero comprueba si `event.status == EventStatus.CANCELLED`: si es así, lanza `HTTPException(409, detail="Un evento cancelado no puede cambiar de estado ni editarse")`.
   - Si `payload.status is not None`:
     - Si `event.status == EventStatus.PUBLISHED and payload.status == EventStatus.DRAFT`: lanza `HTTPException(409, detail="No se puede regresar un evento publicado a borrador")`.
4. **Capacidad y `get_registered_count`:**
   - `get_registered_count(session: Session, event_id: int) -> int`: devuelve `0` en el Dominio 2 (y puede ser sustituido por monkeypatch en tests para simular un evento con inscritos, p. ej. `registered_count = 25`, verificando las reglas `EVT-BR-04` y `EVT-BR-07`; en el Dominio 4 ejecutará `SELECT COUNT(id) FROM registrations WHERE event_id = :event_id`).
   - En `update_event`: si `payload.total_capacity is not None` y `payload.total_capacity < registered_count`, lanza `HTTPException(409, detail="No se puede reducir la capacidad total por debajo del número de inscritos actuales")`.
   - `to_event_read(event: Event, registered_count: int) -> EventRead`: construye el DTO con `available_capacity = max(0, event.total_capacity - registered_count)` e `image_urls = build_image_urls(event.image_key)`.

### 2.5. Procesamiento de imágenes WebP con Pillow y entrega por Nginx

Definido en `backend/app/events/images.py` (verificado con `context7-mcp` sobre `/python-pillow/pillow`):

1. **Validación de estado previo:** Antes de procesar la imagen en `POST /api/events/{id}/image`, si `event.status == EventStatus.CANCELLED`, corta inmediatamente con `409` (`"Un evento cancelado no puede cambiar de estado ni editarse"`).
2. **Lectura y validación de tamaño:**
   - Se lee `raw = await upload_file.read(settings.max_event_image_bytes + 1)` (donde `max_event_image_bytes = 5 * 1024 * 1024`).
   - Si `len(raw) == 0` → `HTTPException(400, detail="El archivo de imagen está vacío")`.
   - Si `len(raw) > settings.max_event_image_bytes` → `HTTPException(413, detail="La imagen no debe superar los 5 MB")`.
3. **Apertura, verificación de formato y limpieza EXIF con Pillow:**
   - Se abre con `Image.open(BytesIO(raw))` dentro de un bloque `try ... except (UnidentifiedImageError, OSError, ValueError)`.
   - Se verifica `img.format in {"JPEG", "PNG", "WEBP"}` y se ejecuta `img.load()`. Si no cumple o falla, lanza `HTTPException(400, detail="Formato de imagen no soportado. Usa JPEG, PNG o WebP")`.
   - Se aplica `transposed = ImageOps.exif_transpose(img)`.
   - Se normaliza el modo de color descartando metadatos: si `transposed.mode in ("RGBA", "LA") or (transposed.mode == "P" and "transparency" in transposed.info)`, se convierte a `"RGBA"`, y en caso contrario a `"RGB"`, copiando solo los píxeles a un `Image.new(mode, transposed.size)` (o guardando sin `exif`, `icc_profile` ni `xmp`) para garantizar cero metadatos residuales (R5.8).
4. **Generación de las 3 variantes (`400w`, `800w`, `1200w`) sin upscaling:**
   - Se genera `image_key = uuid.uuid4().hex`.
   - Directorio destino: `events_media_dir = Path(settings.media_root) / "events"`, creado con `mkdir(parents=True, exist_ok=True)`.
   - Para cada `target_width` en `(400, 800, 1200)`:
     - Si `clean_img.width > target_width`:
       `target_height = max(1, round(clean_img.height * target_width / clean_img.width))`
       `variant = clean_img.resize((target_width, target_height), Image.Resampling.LANCZOS)`
     - Si `clean_img.width <= target_width`:
       `variant = clean_img.copy()`
     - Se guarda en `events_media_dir / f"{image_key}_{target_width}w.webp"` con `format="WEBP", quality=80, method=4`.
5. **Reemplazo y borrado de variantes antiguas:**
   - Se guarda `old_key = event.image_key`, se actualiza `event.image_key = image_key` y `event.updated_at = utc_now()`, se hace `session.commit()`, y luego si `old_key` existía se invoca `delete_event_image_files(old_key)` que elimina `{old_key}_{400|800|1200}w.webp` con `missing_ok=True`.
6. **Servido por Nginx:**
   - El contenedor `gateway` ya sirve `location /api/media/ { alias /var/www/media/; ... }` desde el volumen `media:ro`. Por tanto, `{MEDIA_ROOT}/events/{key}_400w.webp` queda inmediatamente accesible en `/api/media/events/{key}_400w.webp` con cabecera `Cache-Control: public, max-age=31536000, immutable`.

### 2.6. Caché Redis e invalidación (R4.4)

Se utiliza `CacheClient` (`backend/app/core/cache.py`):

- **Cálculo de `scope`:**
  ```python
  def resolve_cache_scope(actor: User | None) -> str:
      if actor is None or actor.role == UserRole.ATTENDEE:
          return "public"
      if actor.role == UserRole.ORGANIZER:
          return f"org:{actor.id}"
      return f"admin:{actor.id}"
  ```
- **Claves:**
  - Listado: `f"events:list:scope={scope}:page={params.page}:size={params.size}:search={params.search or ''}:status={params.status.value if params.status else ''}:mine={int(params.mine)}"`
  - Detalle: `f"events:detail:id={event_id}:scope={scope}"`
- **Lectura (`get`) y escritura (`set`):**
  - En `GET /api/events` y `GET /api/events/{id}`, antes de consultar PostgreSQL se consulta `cache.get(key)`. Si devuelve un diccionario válido, se reconstruye `PaginatedResponse[EventRead].model_validate(cached)` o `EventRead.model_validate(cached)`.
  - Tras consultar PostgreSQL, se serializa con `.model_dump(mode="json")` y se guarda con `cache.set(key, payload, ttl_seconds=settings.cache_events_ttl_seconds)`.
- **Invalidación:**
  - En `create_event`, `update_event`, `delete_event` y `update_event_image`, después de `session.commit()` se llama a `cache.invalidate_prefix("events:")`.
  - Si Redis está caído, `CacheClient` captura `RedisError`, registra un `warning` en inglés en logs y retorna `None`/`False` sin interrumpir la petición (R4.4).

## 3. Frontend

### 3.1. Tipos, servicio HTTP y Store de Pinia (`useEventStore`)

1. **`frontend/src/types/api.ts`:**
   - Añade `export type EventStatus = 'DRAFT' | 'PUBLISHED' | 'CANCELLED'`.
   - Añade `EventImageUrls`, `EventRead`, `EventCreatePayload`, `EventUpdatePayload` y `EventListQuery`.
2. **`frontend/src/services/events.ts`:**
   - Funciones tipadas que usan la instancia `apiClient` (`baseURL: '/api'`):
     - `fetchEventsApi(params?: EventListQuery): Promise<PaginatedResponse<EventRead>>`
     - `fetchEventByIdApi(id: number): Promise<EventRead>`
     - `createEventApi(payload: EventCreatePayload): Promise<EventRead>`
     - `updateEventApi(id: number, payload: EventUpdatePayload): Promise<EventRead>`
     - `deleteEventApi(id: number): Promise<void>`
     - `uploadEventImageApi(id: number, file: File): Promise<EventRead>` (enviando `FormData` con el campo `file`).
3. **`frontend/src/stores/events.ts` (`useEventStore`):**
   - **Estado:** `items: ref<EventRead[]>([])`, `total: ref(0)`, `page: ref(1)`, `size: ref(10)`, `pages: ref(0)`, `search: ref('')`, `statusFilter: ref<EventStatus | ''>('')`, `mineOnly: ref(false)`, `currentEvent: ref<EventRead | null>(null)`, `isLoading: ref(false)`, `isSubmitting: ref(false)`.
   - **Acciones:** `fetchEvents(overrides?)`, `fetchEventById(id)`, `createEvent(payload)`, `updateEvent(id, payload)`, `deleteEvent(id)`, `uploadEventImage(id, file)`, `resetFilters()`.
   - **Prohibición R2.5:** El store y los componentes leen directamente `event.available_capacity`, `event.registered_count` y `event.total_capacity` del DTO recibido; nunca calculan `total_capacity - registered_count`.

### 3.2. Rutas (lazy loading) y guards en Vue Router

Se actualiza `frontend/src/router/index.ts`:

| Path                | Name           | Componente (lazy import)                        | `meta`                                                |
| ------------------- | -------------- | ----------------------------------------------- | ----------------------------------------------------- |
| `/`                 | `home`         | `() => import('@/views/EventsListView.vue')`    | Público                                               |
| `/events/new`       | `event-create` | `() => import('@/views/EventFormView.vue')`     | `{ requiresAuth: true, roles: ['ORGANIZER', 'ADMIN'] }` |
| `/events/:id`       | `event-detail` | `() => import('@/views/EventDetailView.vue')`   | Público                                               |
| `/events/:id/edit`  | `event-edit`   | `() => import('@/views/EventFormView.vue')`     | `{ requiresAuth: true, roles: ['ORGANIZER', 'ADMIN'] }` |

*(Importante: `/events/new` se declara antes de `/events/:id` en la tabla de rutas para evitar colisiones de coincidencia).*

### 3.3. Componentes y Vistas (R6.2 y bonus obligatorios)

1. **`frontend/src/components/events/EventCard.vue`:**
   - Recibe `defineProps<{ event: EventRead }>()`.
   - Muestra la imagen del evento si `event.image_urls` no es `null`:
     ```html
     <img
       :src="event.image_urls.w800"
       :srcset="`${event.image_urls.w400} 400w, ${event.image_urls.w800} 800w, ${event.image_urls.w1200} 1200w`"
       sizes="(max-width: 640px) 400px, (max-width: 1024px) 800px, 1200px"
       :alt="event.title"
       width="800"
       height="450"
       loading="lazy"
       decoding="async"
     />
     ```
   - Si `event.image_urls` es `null`, muestra un bloque visual de reemplazo en Tailwind sin peticiones rotas.
   - Traduce `event.status` al español (`DRAFT` → `"Borrador"`, `PUBLISHED` → `"Publicado"`, `CANCELLED` → `"Cancelado"`).
   - Muestra `event.available_capacity` y `event.total_capacity` directamente desde la API y enlaza a `/events/${event.id}`.
2. **`frontend/src/components/events/EventForm.vue`:**
   - Componente reutilizable de formulario para crear y editar eventos, más selector de archivo (`input type="file" accept="image/jpeg,image/png,image/webp"`) para subir/reemplazar la imagen.
   - Utiliza `BaseInput.vue`, `BaseButton.vue` y `BaseAlert.vue`, mostrando errores por campo (`errors[]` del `422`) y el `detail` de `400`/`409`/`413` en español.
3. **`frontend/src/views/EventFormView.vue`:**
   - Carga `EventForm.vue` mediante **`defineAsyncComponent(() => import('@/components/events/EventForm.vue'))`** con `BaseSpinner` como componente de carga, cumpliendo el bonus obligatorio de lazy loading de componentes pesados (Arquitectura v1.1 §4.6).
4. **`frontend/src/views/EventsListView.vue`:**
   - Barra de búsqueda por nombre (`search`), controles de filtro por `status` y checkbox `"Mis eventos"` (`mine`) visibles para `ORGANIZER` y `ADMIN`, botón `"Crear evento"` visible solo para `ORGANIZER` y `ADMIN`, estado de carga con `BaseSkeleton.vue`, grilla responsiva de `EventCard.vue` y controles de paginación (`Página X de Y`).
5. **`frontend/src/views/EventDetailView.vue`:**
   - Detalle del evento con imagen WebP (`srcset` + `sizes`), descripción, fecha UTC formateada en español, cupos (`available_capacity` / `total_capacity`), estado traducido y botones de acción (`Editar`, `Publicar`, `Cancelar evento`, `Eliminar`) visibles solo si `authStore.role === 'ADMIN' || (authStore.role === 'ORGANIZER' && authStore.user?.id === event.organizer_id)`.
   - Si el rol es `ORGANIZER` o `ADMIN`, no renderiza botón de inscripción (preparando la integración limpia con `registrations` y cumpliendo la pauta de Vitest de la Arquitectura v1.1 §5).

## 4. Librerías de soporte (R4.2)

| Librería           | Componente del stack al que sirve                    | Motivo                                                                                                             |
| ------------------ | ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| `pillow`           | Backend FastAPI — Procesador de imágenes WebP (§3.8) | Decodificación segura de JPEG/PNG/WebP, `ImageOps.exif_transpose`, eliminación de EXIF y conversión a 3 variantes WebP. |
| `python-multipart` | Backend FastAPI — Subida `multipart/form-data`       | Requerido por FastAPI/Starlette para recibir `UploadFile` (`File(...)`) en `POST /api/events/{id}/image`.          |

Ambas librerías ya están autorizadas en `MEMORY.md` (entrada del `2026-10-30`) y se añaden a `backend/pyproject.toml` y `backend/uv.lock` al iniciar la tarea correspondiente.

## 5. Estrategia de pruebas (TDD)

- **Backend (`pytest` contra PostgreSQL en contenedor, R3.6):**
  - Archivo principal de pruebas: `backend/tests/test_events.py`.
  - Se ejecuta contra `mis_eventos_test` en PostgreSQL 17 aplicando la migración `0003_create_events`.
  - **Inspección de esquema e índices (`EVT-AC-25`):** verifica con `sqlalchemy.inspect` y catálogo `pg_indexes` que existen `events`, `ck_events_status`, `ck_events_total_capacity_positive` y el índice GIN `ix_events_title_trgm` con `gin_trgm_ops`.
  - **Imágenes (`EVT-AC-20..22`):** se inyecta `tmp_path` en `settings.media_root` mediante fixture para no ensuciar el sistema de archivos local; se generan imágenes en memoria con Pillow (incluyendo una con etiqueta EXIF `Orientation=6` y datos GPS, una pequeña de `300x200` para probar `no upscaling`, una grande de `1600x900` para probar las 3 variantes `400w`/`800w`/`1200w`, un archivo corrupto y un payload de `> 5 MB`).
  - **Caché Redis (`EVT-AC-23..24`):** se prueba con un doble/espía de `CacheClient` y con simulación de caída de Redis (`RedisError`) verificando hits de caché, aislamiento por `scope`, invalidación `events:` en escrituras y degradación transparente a PostgreSQL.
- **Frontend (`Vitest`):**
  - `frontend/src/__tests__/events.store.spec.ts`: pruebas de `useEventStore` y servicio `events.ts`.
  - `frontend/src/__tests__/events.components.spec.ts`: pruebas de `EventCard.vue` (`srcset`, traducción de estados, cupos de la API) y `EventForm.vue` (validación y subida de archivo).
  - `frontend/src/__tests__/events.views.spec.ts`: pruebas de `EventsListView.vue`, `EventDetailView.vue` y `EventFormView.vue` (incluyendo permisos de UI por rol y carga diferida con `defineAsyncComponent`).

## 6. Riesgos y mitigaciones

- **Riesgo 1: Fuga de eventos `DRAFT` o `CANCELLED` entre roles a través de Redis.**
  - *Mitigación:* La clave de caché incluye obligatoriamente `scope` (`public`, `org:{id}`, `admin:{id}`) y toda escritura invalida el prefijo `events:`. Se incluye un test específico (`test_evt_ac_24_...`) que verifica que un borrador cacheado para su organizador no sea visible para un asistente o anónimo.
- **Riesgo 2: Archivos WebP huérfanos en el volumen `media` o contaminación entre tests.**
  - *Mitigación:*En los tests de `pytest` se redirige `settings.media_root` a `tmp_path`. En producción, el reemplazo de imagen y el `DELETE` del evento invocan `delete_event_image_files(old_key)` con `missing_ok=True`.
- **Riesgo 3: Comodines `%` o `_` en la búsqueda `search` alterando el resultado de `ILIKE`.**
  - *Mitigación:* `escape_like` escapa `\`, `%` y `_` y pasa `escape="\\"` a `.ilike(...)`. Se verifica con un test dedicado en `EVT-AC-17`.
- **Riesgo 4: Colisión de rutas en Vue Router entre `/events/new` y `/events/:id`.**
  - *Mitigación:* Declarar `/events/new` antes de `/events/:id` y validar en `EventDetailView` que `Number(route.params.id)` sea entero positivo.
