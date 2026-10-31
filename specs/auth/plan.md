# Plan técnico: Autenticación, RBAC y Perfiles (`auth`)

| Campo                  | Valor                          |
| ---------------------- | ------------------------------ |
| **ID del dominio**     | `AUTH`                         |
| **Spec de referencia** | `specs/auth/spec.md` v1.0      |
| **Fecha**              | 2026-10-31                     |

> Este plan describe **cómo** se implementa `specs/auth/spec.md`. No añade comportamiento: si algo no está en `spec.md`, primero se agrega allí (R1.1, R1.5). Identificadores en inglés (Principio 6).

## 1. Modelo de datos y migraciones

### 1.1. Tabla `users`

Se usa la tabla `users` (plural) para evitar la palabra reservada `user` de PostgreSQL.

| Columna         | Tipo SQL                            | Restricciones                                                                 |
| --------------- | ----------------------------------- | ----------------------------------------------------------------------------- |
| `id`            | `INTEGER` / `SERIAL`                | `PRIMARY KEY`, autoincremental.                                               |
| `email`         | `VARCHAR(254)`                      | `NOT NULL`, `UNIQUE` (`uq_users_email`), almacenado en minúsculas y sin espacios exteriores. |
| `password_hash` | `VARCHAR(255)`                      | `NOT NULL`; hash argon2id; nunca se serializa.                                |
| `full_name`     | `VARCHAR(120)`                      | `NOT NULL`; 2–120 caracteres tras `trim`.                                     |
| `role`          | `VARCHAR(20)` + `CHECK`             | `NOT NULL`, `DEFAULT 'ATTENDEE'`; solo `ADMIN`, `ORGANIZER`, `ATTENDEE`.       |
| `is_active`     | `BOOLEAN`                           | `NOT NULL`, `DEFAULT TRUE`.                                                   |
| `created_at`    | `TIMESTAMP WITH TIME ZONE`          | `NOT NULL`, `DEFAULT now()`; UTC.                                             |
| `updated_at`    | `TIMESTAMP WITH TIME ZONE`          | `NOT NULL`, `DEFAULT now()`; UTC; se actualiza **en la aplicación** en cada escritura. |

- **`updated_at`:** PostgreSQL no admite `ON UPDATE now()` en la definición de columna. Se usa `DEFAULT now()` en la migración y los servicios asignan `updated_at = datetime.now(timezone.utc)` en cada `PATCH`; no se añade trigger. `created_at` no cambia tras el alta.
- **Modelo SQLModel:** `backend/app/users/models.py`, con `UserRole(str, Enum)` y `User`.
- **Migración Alembic:** `backend/migrations/versions/0002_create_users.py`, `down_revision = "0001_enable_pg_trgm"`.
  - `upgrade()`: crea la tabla con `server_default=sa.func.now()` en `created_at`/`updated_at`, el `CHECK` de rol, el `UNIQUE` de email y los índices.
  - `downgrade()`: elimina índices, constraints y tabla en orden inverso.
- **Índices:**
  - `uq_users_email` (implícito en el `UNIQUE`) para login y duplicados.
  - `ix_users_role` para el filtro `role` del listado del admin.
  - `ix_users_is_active` para el filtro `is_active`.
- **Importación para Alembic:** `migrations/env.py` debe importar `app.users.models` (o un agregador `app/models.py`) para que `SQLModel.metadata` incluya `User`; la fixture `db_truncate` de `tests/conftest.py` también depende de que el modelo esté importado por `app.main`.
- **Sin tabla de auditoría:** los cambios de rol/estado se registran solo en logs con ids y roles, sin emails ni contraseñas.
- **Sin borrado físico:** `is_active = false` es la desactivación; las FK de `events` y `registrations` se preservan.

## 2. Backend

### 2.1. Estructura de módulos

```text
backend/app/
├── auth/
│   ├── __init__.py
│   ├── schemas.py          # RegisterRequest, LoginRequest, TokenResponse
│   ├── security.py         # hash/verify argon2id, create/decode JWT
│   ├── dependencies.py     # get_current_user, require_roles
│   ├── service.py          # register_user, authenticate_user
│   ├── policies.py         # can_register_for_events(role)
│   └── router.py           # POST /auth/register, POST /auth/login, GET/PATCH /auth/me
├── users/
│   ├── __init__.py
│   ├── models.py           # User, UserRole
│   ├── schemas.py          # UserRead, UpdateMeRequest, AdminUserUpdateRequest, UserListParams
│   ├── service.py          # list/get/update user, protección del último admin
│   ├── bootstrap.py        # ensure_bootstrap_admin
│   └── router.py           # GET /users, GET/PATCH /users/{id}
└── core/
    ├── config.py           # APP_ENV, JWT_EXPIRE_MINUTES, JWT_SECRET_KEY, BOOTSTRAP_ADMIN_*
    ├── exceptions.py       # traducción 422 adicional
    └── pagination.py       # reutilizado sin cambios
```

- `app/main.py` registra `auth.router` con prefijo `/api/auth` y `users.router` con prefijo `/api/users`, ambos con `tags` para OpenAPI.
- El router de `users` no expone perfiles públicos; todas sus rutas salvo las de `auth` exigen `ADMIN`.
- `auth/router.py` usa `UserRead` para `/auth/me` y para el `user` del login; no duplica el schema.

### 2.2. Configuración por entorno

Se amplía `backend/app/core/config.py` (pydantic-settings) con:

| Variable                    | Tipo / valor por defecto                          | Uso                                                                 |
| --------------------------- | ------------------------------------------------- | ------------------------------------------------------------------- |
| `APP_ENV`                   | `development`                                     | Distinguir producción para validar el secreto JWT.                  |
| `JWT_SECRET_KEY`            | placeholder actual, mínimo 32 caracteres          | Firma HS256; validado al arrancar.                                  |
| `JWT_EXPIRE_MINUTES`        | `480`                                             | Expiración del token; `expires_in = minutos * 60`.                  |
| `BOOTSTRAP_ADMIN_EMAIL`     | `None`                                            | Email del primer admin; si falta, no se siembra.                    |
| `BOOTSTRAP_ADMIN_PASSWORD`  | `None`                                            | Contraseña del primer admin; nunca se registra.                     |
| `BOOTSTRAP_ADMIN_FULL_NAME` | `"Administrador"`                                 | Nombre del primer admin.                                            |

- `field_validator("jwt_secret_key")`: exige longitud ≥32; el mensaje de error no incluye el valor.
- `model_validator`: si `app_env == "production"` y la clave es el placeholder conocido o mide menos de 32, lanza un error de configuración en español, sin mostrar el valor.
- `.env.example` se ampliará con `APP_ENV`, `JWT_EXPIRE_MINUTES`, `BOOTSTRAP_ADMIN_EMAIL=`, `BOOTSTRAP_ADMIN_PASSWORD=` y `BOOTSTRAP_ADMIN_FULL_NAME=Administrador`; `JWT_SECRET_KEY` conserva un placeholder, nunca un secreto real.
- `docker-compose.yml` debe pasar estas variables al servicio `api`; no se versiona ningún valor real.

### 2.3. Schemas de entrada y salida (R5.5)

- **`RegisterRequest`:** `email: EmailStr` con `max_length=254`, `password: str` con `min_length=8` y `max_length=128`, `full_name: str` con `min_length=2` y `max_length=120`; `model_config = ConfigDict(extra="forbid")`.
  - Validador `email` en modo `before`: `strip().lower()`.
  - Validador `full_name`: `strip()` y rechazo si queda vacío.
  - Validador `password`: rechazo si es solo espacios; no se aplica `trim`.
- **`LoginRequest`:** `email` y `password`; `extra="forbid"`; el email se normaliza igual.
- **`TokenResponse`:** `access_token: str`, `token_type: Literal["bearer"]`, `expires_in: int`, `user: UserRead`.
- **`UserRead`:** `id`, `email`, `full_name`, `role`, `is_active`, `created_at`, `updated_at`; `from_attributes=True`; nunca incluye `password_hash`.
- **`UpdateMeRequest`:** solo `full_name`; `extra="forbid"`; body vacío rechazado.
- **`AdminUserUpdateRequest`:** `full_name`, `role` e `is_active` opcionales; `extra="forbid"` (por tanto `email` se rechaza); validador que exige al menos un campo.
- **`UserListParams`:** hereda o compone `PaginationParams` de `app/core/pagination.py` y añade `role: UserRole | None` e `is_active: bool | None`.
- Los endpoints declaran `response_model=UserRead` o `PaginatedResponse[UserRead]`; no se devuelve el modelo `User` directamente.

### 2.4. Hashing de contraseñas

- `app/auth/security.py` usa `argon2.PasswordHasher` con los parámetros por defecto (argon2id, sal por defecto).
- `hash_password(password: str) -> str` y `verify_password(password: str, password_hash: str) -> bool`.
- `verify_password` captura `VerifyMismatchError` e `InvalidHashError` y devuelve `False`; no propaga detalles al cliente.
- `needs_rehash(password_hash) -> bool` se consulta tras un login correcto; si es `True`, se rehashea y se actualiza `password_hash` en la misma transacción.
- **Hash ficticio:** constante `DUMMY_PASSWORD_HASH` válida (generada con el mismo hasher, no es un secreto). Si el email no existe, se ejecuta `verify_password(password, DUMMY_PASSWORD_HASH)` para igualar el coste y luego se devuelve `401` genérico.
- **Tests:** se inyecta un `PasswordHasher` de bajo coste (`time_cost=1`, `memory_cost=1024`, `parallelism=1`) mediante una fixture o monkeypatch de la fábrica `get_password_hasher()`, para que la suite no sea lenta. Producción usa los parámetros por defecto.

### 2.5. JWT

- `create_access_token(user: User) -> tuple[str, int]`:
  - `now = datetime.now(timezone.utc)`.
  - Payload: `{"sub": str(user.id), "role": user.role.value, "iat": now, "exp": now + timedelta(minutes=settings.jwt_expire_minutes)}`.
  - `jwt.encode(payload, settings.jwt_secret_key, algorithm="HS256")`.
  - Devuelve el token y `expires_in = settings.jwt_expire_minutes * 60`.
- `decode_access_token(token: str) -> dict`:
  - `jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"], options={"require": ["exp", "iat", "sub"]})`.
  - El allow-list explícito impide confusión de algoritmo; no se acepta `alg = none` ni HS512.
  - Captura `ExpiredSignatureError`, `InvalidTokenError` y `MissingRequiredClaimError`; todas se traducen a `401` genérico.
  - `sub` se convierte a `int`; si no es numérico, `401`.
- El claim `role` se conserva por observabilidad, pero **no** se usa para autorizar; el rol se lee del `User` cargado.
- Sin `jti`, `iss`, `aud`, refresh, rotación ni revocación.

### 2.6. Cadena única de dependencias FastAPI (R5.2)

- `bearer_scheme = HTTPBearer(auto_error=False)` para controlar el `detail` y la cabecera en español.
- `get_current_user(credentials = Depends(bearer_scheme), session = Depends(get_session)) -> User`:
  1. Si `credentials is None`, lanza `HTTPException(401, detail="No autenticado o sesión expirada", headers={"WWW-Authenticate": "Bearer"})`.
  2. Decodifica el token con `decode_access_token`; cualquier error → `401` con la misma cabecera.
  3. Carga `User` por `sub`; si no existe → `401`.
  4. Si `is_active` es `False` → `401`.
  5. Devuelve el `User` con el rol de la base de datos.
- `require_roles(*roles: UserRole)` devuelve una dependencia que:
  - Resuelve `current_user = Depends(get_current_user)`.
  - Si `current_user.role not in roles`, lanza `HTTPException(403, detail="No tienes permisos para realizar esta acción")`.
- `require_admin = require_roles(UserRole.ADMIN)` para el router de `users`.
- La propiedad del recurso se añadirá en `events`, `sessions` y `registrations` como una dependencia adicional dentro de la misma cadena; `auth` deja el patrón preparado.
- **`WWW-Authenticate`:** se adjunta en cada `HTTPException` 401; el manejador global de `core/exceptions.py` pasa `headers=exc.headers`, por lo que la cabecera se conserva al traducir el `detail`.
- **`policies.py`:** `can_register_for_events(role: UserRole) -> bool` devuelve `True` solo para `ATTENDEE`. `registrations` lo reutilizará; se prueba aquí (AUTH-AC-30).

### 2.7. Servicios y endpoints

- **`register_user`:** normaliza email, comprueba existencia, hashea, inserta con `role=ATTENDEE`, `is_active=True`, hace `commit`; captura `IntegrityError` por concurrencia, hace `rollback` y devuelve conflicto `409`.
- **`authenticate_user`:** normaliza email, busca por email; si no existe, verifica el hash ficticio y devuelve `None`; si existe, verifica la contraseña, comprueba `is_active` y rehashea si hace falta; devuelve el usuario o `None`.
- **`POST /api/auth/register`:** schema `RegisterRequest`, respuesta `201 UserRead`; no emite token.
- **`POST /api/auth/login`:** schema `LoginRequest`, respuesta `200 TokenResponse`; si `authenticate_user` devuelve `None`, `401` con `"Credenciales inválidas"` y `WWW-Authenticate: Bearer`.
- **`GET /api/auth/me`:** `Depends(get_current_user)`, respuesta `UserRead`.
- **`PATCH /api/auth/me`:** `Depends(get_current_user)`, `UpdateMeRequest`, actualiza solo `full_name`, `updated_at`; respuesta `UserRead`.
- **`GET /api/users`:** `Depends(require_admin)`, `PaginationParams` + filtros `role`/`is_active`, `select` ordenado por `id` asc, `count` para el total, `build_paginated_response`; respuesta `PaginatedResponse[UserRead]`.
- **`GET /api/users/{id}`:** `Depends(require_admin)`, carga o `404` con `"Usuario no encontrado"`.
- **`PATCH /api/users/{id}`:** `Depends(require_admin)`, `AdminUserUpdateRequest`:
  - Si el objetivo no existe → `404`.
  - Si el objetivo es el propio admin y el payload incluye `role` → `400 "No puedes cambiar tu propio rol"`.
  - Si el objetivo es el propio admin y el payload incluye `is_active` → `400 "No puedes desactivar tu propia cuenta"`.
  - Si se cambia el rol de un `ADMIN` activo o se desactiva, se comprueba que quede al menos un `ADMIN` activo; si no → `409 "Debe existir al menos un administrador activo"`.
  - Actualiza los campos presentes y `updated_at`; respuesta `UserRead`.
- **`can_register_for_events`:** helper puro, sin base de datos; `ATTENDEE → True`, `ORGANIZER/ADMIN → False`.

### 2.8. Transacciones y bloqueos

- **Registro:** `INSERT` con `UNIQUE(email)`; el `IntegrityError` por concurrencia se traduce a `409` tras `rollback`.
- **Último admin:** dentro de una transacción, se bloquean todas las filas de administradores activos con `SELECT ... FOR UPDATE ORDER BY id` antes de contar. Así dos peticiones concurrentes que intenten degradar o desactivar administradores distintos no pueden dejar el sistema sin ningún `ADMIN` activo. Se actualiza el objetivo en la misma transacción y se hace `commit` al final.
- **Bootstrap:** `INSERT` idempotente; si dos réplicas arrancan a la vez, el `UNIQUE(email)` decide y la perdedora captura `IntegrityError`, hace `rollback` y continúa como “ya existe”.
- **Sin caché Redis:** `auth` no cachea perfiles ni sesiones; toda lectura va a PostgreSQL (R4.4 no aplica aquí).

### 2.9. Bootstrap del primer admin

- `ensure_bootstrap_admin(session, email, password, full_name) -> User | None`:
  - Normaliza el email.
  - Si el email ya existe, devuelve el usuario existente **sin** modificar rol ni contraseña; registra un aviso genérico sin email.
  - Si no existe, valida la contraseña con la misma política, hashea e inserta `role=ADMIN`, `is_active=True`; captura `IntegrityError` y trata el caso como “ya existe”.
  - Nunca registra `password` ni `password_hash`.
- `app/main.py` usa un `lifespan`:
  - Si `BOOTSTRAP_ADMIN_EMAIL` y `BOOTSTRAP_ADMIN_PASSWORD` están ambos definidos, abre una sesión con `Session(engine)` y llama a `ensure_bootstrap_admin`.
  - Si solo uno está definido, lanza `RuntimeError("Configuración incompleta del administrador inicial")` sin secretos.
  - Si ninguno está definido, no hace nada.
- **Orden:** en Docker, `alembic upgrade head` se ejecuta antes de Uvicorn; el `lifespan` corre después, con la tabla `users` ya creada. En local, el README indica ejecutar `uv run alembic upgrade head` antes de `uvicorn`.
- **Aislamiento en tests:** las variables de bootstrap no se definen en el entorno de prueba; el test de bootstrap llama directamente a `ensure_bootstrap_admin` con una sesión y valores falsos. El `TestClient` no debe sembrar datos por un `.env` local; si fuera necesario, la fixture limpia/monkeypatchea `settings.bootstrap_admin_*`.

### 2.10. Errores y traducción 422

Se amplía `app/core/exceptions.py` sin cambiar el contrato de `platform`. **Regla única:** en todo `422` de validación Pydantic, `detail` es el resumen genérico `"Error de validación en los datos enviados"` (o `"El cuerpo de la petición no es un JSON válido"` si el body no parsea) y el mensaje específico va en `errors[].message`; nunca se usa un mensaje específico como `detail` de un `422`.

Cómo se consigue:

- `extra_forbidden` → `errors[].message = "Este campo no está permitido"`.
- `value_error` cuyo mensaje o `ctx.error` haga referencia a email → `errors[].message = "El correo electrónico no es válido"`.
- `string_pattern_mismatch` → `errors[].message = "El formato del campo no es válido"` (preparado para validaciones de nombre).
- `string_too_short` y `string_too_long` ya existen y cubren 8/128 y 2/120; se traducen a mensajes de longitud en español dentro de `errors[].message`.
- `bool_parsing`/`bool_type`, `enum` e `int_parsing` ya existen; se traducen a mensajes de tipo/enumeración en español dentro de `errors[].message`.
- Los validadores personalizados (`full_name` vacío, contraseña solo espacios, body vacío) lanzan `ValueError` con mensaje en español; el traductor lo copia a `errors[].message` y deja `detail` genérico. Para el body vacío se usa un `model_validator` que lanza `"Debes indicar al menos un campo para actualizar"`.
- El `field` se mantiene en notación punto (`body.email`, `body.role`, etc.).
- Los `HTTPException` 400/401/403/404/409 usan los `detail` exactos de la spec (`"Credenciales inválidas"`, `"No autenticado o sesión expirada"`, `"No tienes permisos para realizar esta acción"`, `"Usuario no encontrado"`, `"Debe existir al menos un administrador activo"`, etc.); el handler conserva `headers`.

### 2.11. OpenAPI y logs

- `HTTPBearer` añade el esquema de seguridad HTTP Bearer (`HTTPBearer`) a `components.securitySchemes` de `/api/openapi.json`; Swagger permite pegar el token.
- `UserRead` es el único schema de salida de usuario; no hay `password_hash` en componentes.
- `POST /api/auth/register`, `POST /api/auth/login`, `GET/PATCH /api/auth/me`, `GET /api/users`, `GET/PATCH /api/users/{id}` aparecen con sus códigos y `tags`.
- Logs: solo `user_id`, `role` y resultado; nunca email, contraseña, hash, token ni cuerpo de la petición. El logger de acceso de Uvicorn no registra cuerpos.

## 3. Frontend

### 3.1. Tipos y servicios

- `frontend/src/types/api.ts`:
  - `UserRole` se mantiene.
  - `AuthUser` pasa a `{ id, email, full_name: string, role, is_active, created_at, updated_at }`; `full_name` deja de ser opcional.
  - `LoginResponse = { access_token, token_type: 'bearer', expires_in, user: AuthUser }`.
  - `RegisterPayload`, `LoginPayload`, `UpdateProfilePayload`, `AdminUserUpdatePayload`, `UserListParams`, `UserListResponse = PaginatedResponse<AuthUser>`.
- `frontend/src/services/auth.ts`: `register(payload)`, `login(payload)`, `getMe()`, `updateMe(payload)` usando `apiClient`; DTO tipados.
- `frontend/src/services/users.ts`: `listUsers(params)`, `getUser(id)`, `updateUser(id, payload)`; solo se usan desde la vista de administración.

### 3.2. `useAuthStore`

- Estado: `token: string | null`, `user: AuthUser | null`, `initialized: boolean`, `initializing: Promise<void> | null`.
- Getters: `isAuthenticated` (token y user), `role`, `isAdmin` (`role === 'ADMIN'`).
- Claves: `mis_eventos.auth.token` y `mis_eventos.auth.user`.
- `setSession(token, user)`: asigna estado, escribe `sessionStorage` y llama a `resetUnauthorizedState()` del interceptor.
- `clearSession()`: limpia estado y ambas claves de `sessionStorage`.
- `login(payload)`: llama a `services/auth.login`, `setSession`, devuelve el usuario.
- `register(payload)`: llama a `services/auth.register`; no crea sesión.
- `fetchMe()`: llama a `GET /api/auth/me`, actualiza `user` y `sessionStorage`; si recibe `401`, `clearSession` (el interceptor también lo hace).
- `initialize()`: si no hay token, marca `initialized`; si hay token, hidrata el usuario guardado (si es JSON válido) y llama a `fetchMe()` para refrescar rol/estado. Si `/me` devuelve `401`, limpia; si falla la red, conserva el token y deja que las peticiones posteriores resuelvan.
- `updateProfile(payload)`: llama a `PATCH /api/auth/me` y actualiza `user`/`sessionStorage`.
- `logout()`: `clearSession` y redirección a login desde la vista.
- `initialize()` se ejecuta una sola vez y se reutiliza la misma promesa para que los guards no lancen peticiones duplicadas.

### 3.3. Interceptor Axios y single-flight

- Se conserva la semántica de `platform`: `401` fuera de login limpia sesión, avisa y redirige con `query.redirect`; `403` mantiene sesión y avisa; `404`/`409` muestran `detail`; `422` muestra el `detail` genérico y el primer `errors[].message` en español; `5xx`/red muestran mensaje genérico.
- Se añade un estado de módulo `unauthorizedHandled: boolean`:
  - En el primer `401` fuera de login: `authStore.clearSession()`, aviso `"Tu sesión ha expirado. Inicia sesión nuevamente."`, `configureApiNavigation` redirige a `login` con `redirect`, y `unauthorizedHandled = true`.
  - En `401` posteriores mientras el flag esté activo: se rechaza la promesa sin duplicar aviso ni redirección.
  - `401` del login: no toca el flag, no redirige y muestra `"Credenciales inválidas"` (o el `detail`).
  - `resetUnauthorizedState()` se exporta y se llama al hacer login correcto y al limpiar manualmente la sesión; así una nueva sesión vuelve a manejar 401 normalmente.
- `configureApiNavigation` no cambia; se mantiene la captura de la ruta actual para `query.redirect`.
- No se reintenta la petición ni se refresca el token; el usuario vuelve a iniciar sesión.

### 3.4. Router y guards

- Rutas lazy:
  - `/login` → `LoginView.vue`.
  - `/register` → `RegisterView.vue`.
  - `/profile` → `ProfileView.vue`, `meta.requiresAuth: true`.
  - `/admin/users` → `AdminUsersView.vue`, `meta.requiresAuth: true`, `meta.roles: ['ADMIN']`.
  - `/admin` puede redirigir a `/admin/users` o mantenerse como vista de administración.
- El guard existente se conserva; se añade la espera de `authStore.initialize()` antes de evaluar `requiresAuth`/`roles`, para que una recarga con `sessionStorage` no redirija erróneamente al login.
- `query.redirect` se valida: solo rutas internas que empiecen por `/` y no por `//`; si no, se ignora y se va a `home`.
- Tras login correcto, `LoginView` navega a `route.query.redirect` si es válido; si no, a `home`.
- `403` de backend: el guard puede redirigir a `home` si el rol local no coincide; el interceptor mantiene la sesión y muestra el aviso.

### 3.5. Vistas y componentes

- **`LoginView.vue`:** `BaseInput` email/password, `BaseButton` con `isLoading`, `BaseAlert` para error; envía `login`; en éxito redirige a `redirect` o `home`; en `401` muestra `"Credenciales inválidas"` sin redirigir; enlace a registro.
- **`RegisterView.vue`:** `BaseInput` `full_name`, email, password; `BaseButton`; valida longitudes en cliente como ayuda de UX; en `201` muestra aviso de éxito y redirige a login (sin auto-login); en `409` muestra el `detail`; en `422` muestra el `errors[].message` en español; enlace a login.
- **`ProfileView.vue`:** muestra email, rol y estado como solo lectura; `full_name` editable con `BaseInput`; `BaseButton` guardar; `BaseAlert` de éxito/error; botón de logout; sin `v-html`.
- **`AdminUsersView.vue`:** tabla responsive con email, nombre, rol, estado, fechas; filtros `role`/`is_active`; paginación `page`/`size`; edición de `full_name`, `role` e `is_active`; sin botón de borrado; confirmación para desactivar; mensajes en español.
- Se reutilizan `BaseInput`, `BaseButton`, `BaseSpinner`, `BaseSkeleton` y `BaseAlert`; estados de carga y vacío.
- No se usa `v-html` con contenido de usuario (R5.9).

### 3.6. `main.ts`

- Orden: crear app y Pinia, crear router, `configureApiNavigation`, obtener `useAuthStore(pinia)`, `await authStore.initialize()`, `app.use(router)`, `app.mount('#app')`.
- Si `initialize()` recibe `401`, el interceptor ya limpia y redirige; la app monta en login. Si falla la red, se conserva la sesión y se monta; la primera petición protegida reintenta la validación.
- No se cambia el `baseURL: '/api'` ni se habilita CORS.

## 4. Librerías de soporte (R4.2)

| Librería          | Lado    | Componente del stack al que sirve | Motivo                                                                                       |
| ----------------- | ------- | --------------------------------- | -------------------------------------------------------------------------------------------- |
| `PyJWT`           | Backend | JWT (R4.1)                        | Codifica/decodifica HS256 con allow-list de algoritmos, `exp` y claims obligatorios; compatible con Python 3.14. |
| `argon2-cffi`     | Backend | Hashing (R5.1)                    | Argon2id con sal, `PasswordHasher.hash/verify/check_needs_rehash`; sin límite de 72 bytes.   |
| `email-validator` | Backend | Validación Pydantic (`EmailStr`)  | Validación de email usada por `EmailStr`; formato y longitud antes de persistir.              |

- Las tres se registran en `MEMORY.md` con su motivo al aprobarse la spec (R4.2).
- **No se añaden:** `python-jose` (se prefiere PyJWT), `passlib` (sin mantenimiento), refresh tokens, cookies, ORM alternativo, UI kit, workers ni `python-multipart` para `auth` (el login es JSON puro).
- **Verificación en Python 3.14:** ejecutar `uv add PyJWT argon2-cffi email-validator` y comprobar que `uv.lock` y la imagen `python:3.14-slim` instalan wheels compatibles. Si `argon2-cffi`/`cffi` fallara, el fallback es `bcrypt` con pre-hash SHA-256 o límite de 72 bytes; el fallback requiere enmienda de la spec porque cambia la política de longitud.
- `python-multipart` sigue previsto para la subida de imágenes de `events`; no se usa en `auth`.

## 5. Estrategia de pruebas

### 5.1. Backend (`pytest` contra PostgreSQL en contenedor)

- **Fixtures existentes:** `db_session` (SAVEPOINT + rollback), `db_truncate` (concurrencia y bootstrap con varias conexiones) y `client` (override de `get_session`). Toda la suite corre contra `mis_eventos_test` (R3.6).
- **Archivos previstos:**
  - `backend/tests/test_auth.py`: registro, login, JWT, perfil propio, 401/403, RBAC.
  - `backend/tests/test_users.py`: listado/detalle/actualización por admin, último admin, auto-cambio.
  - `backend/tests/test_bootstrap.py`: idempotencia, email existente, configuración parcial, concurrencia.
  - `backend/tests/test_auth_openapi.py`: OpenAPI, `Bearer`, ausencia de `password_hash`, logs.
- **Datos de prueba:** emails `attendee@example.com`, `organizer@example.com`, `admin@example.com`; contraseñas falsas como `Test1234!`; nunca credenciales reales. Un helper `create_user(...)` hashea con el hasher de bajo coste de test.
- **Seguridad:** hash no expuesto; login genérico; token manipulado/expirado/`alg=none`/sin `exp`/`sub` no numérico; usuario inactivo/eliminado; rol cambiado; último admin; `WWW-Authenticate`; logs sin `password`/`password_hash`/`JWT_SECRET_KEY`.
- **Concurrencia del último admin:** test con dos conexiones/sesiones reales y `db_truncate`; no usar SQLite. Se bloquean los administradores activos con `FOR UPDATE` y se comprueba que al menos una operación falla con `409`.
- **Bootstrap:** llamada directa a `ensure_bootstrap_admin` con una sesión de test; dos llamadas seguidas; usuario existente con rol `ATTENDEE`; configuración parcial a nivel de helper de arranque; `IntegrityError` simulado o concurrencia con dos sesiones.
- **Contrato/OpenAPI:** `client.get("/api/openapi.json")`; verificar `components.securitySchemes` con `HTTPBearer`, paths, `UserRead` sin `password_hash`; `client.get("/api/docs")` responde `200`.
- **Cobertura:** `uv run pytest --cov=app --cov-report=xml --cov-report=term-missing`; no se escriben tests triviales (R3.9). Mantener la cobertura global existente y cubrir los caminos de seguridad.
- **Validación funcional:** cuando el entorno esté disponible, `chrome-devtools-mcp` para registro, login, perfil, administración y recarga con `sessionStorage`.

### 5.2. Frontend (`Vitest`)

- **Archivos previstos:**
  - `src/__tests__/auth.store.spec.ts`: persistencia, hidratación, `initialize`, `clearSession`, `logout`, `isAdmin`.
  - `src/__tests__/api.interceptor.spec.ts`: single-flight 401, login 401, 403, `redirect`, `resetUnauthorizedState`.
  - `src/__tests__/router.guards.spec.ts`: `requiresAuth`, `roles`, retorno a `redirect`, destino externo.
  - `src/__tests__/auth.views.spec.ts`: login, registro, perfil.
  - `src/__tests__/admin.users.spec.ts`: listado, filtros, paginación y actualización.
- **Mocks:** `apiClient`/servicios con `vi.mock`; `sessionStorage` de jsdom; router en memoria (`createMemoryHistory`).
- **Cobertura:** `npx vitest run --coverage`; `npx vue-tsc --noEmit`; `npm run build`.
- **Compatibilidad:** los tests existentes de `platform` deben seguir pasando; el cambio de `AuthUser.full_name` a obligatorio se refleja en fixtures y mocks.

### 5.3. Comandos verificables

Tomados de `AGENTS.md` y de los READMEs; no se inventan:

- Backend (desde `backend/`):
  - `uv run pytest`
  - `uv run pytest --cov=app --cov-report=xml --cov-report=term-missing`
  - `uv run alembic current`
  - `uv run alembic history`
- Frontend (desde `frontend/`):
  - `npm run test -- --run`
  - `npx vitest run --coverage`
  - `npx vue-tsc --noEmit`
  - `npm run build`
- Infraestructura (desde la raíz):
  - `docker compose up -d --build`
  - `docker compose ps`

## 6. Riesgos y mitigaciones

- **Traducción 422 de `EmailStr`/`extra_forbidden`:** Pydantic puede devolver mensajes en inglés. Mitigación: ampliar `core/exceptions.py` y probar `detail`/`errors` en español antes de implementar los endpoints.
- **Último admin concurrente:** un `count` ingenuo permite dejar cero admins. Mitigación: bloquear todas las filas de administradores activos con `FOR UPDATE` y probar con dos conexiones.
- **Bootstrap en tests:** el `lifespan` puede sembrar datos si el `.env` local define las variables. Mitigación: no definirlas en el entorno de prueba; test directo de `ensure_bootstrap_admin`; fixture que limpia/monkeypatchea settings si hace falta.
- **Single-flight de 401:** varias peticiones en vuelo pueden duplicar avisos/redirecciones. Mitigación: flag de módulo, `resetUnauthorizedState` al login correcto y test con promesas concurrentes.
- **`sessionStorage` y XSS:** el token es legible por JavaScript. Mitigación: `sessionStorage`, prohibición de `v-html` (R5.9), no persistir datos sensibles adicionales; CSP queda fuera de alcance.
- **`argon2-cffi` en Python 3.14:** `cffi` puede no tener wheel para la versión exacta. Mitigación: `uv add` y build de Docker antes de aprobar; fallback `bcrypt` con pre-hash/límite, que exigiría enmienda de la spec.
- **`email-validator`:** añade una dependencia de soporte; si no se acepta, validación regex con mensajes en español (menos robusta). Mitigación: registrar y verificar la instalación.
- **Claim `role` obsoleto:** un token viejo puede llevar un rol distinto. Mitigación: autorizar siempre con `current_user.role` de la base de datos; probar el cambio de rol con token vigente.
- **Placeholder de `JWT_SECRET_KEY`:** `.env.example` y `docker-compose.yml` contienen el placeholder. Mitigación: validación de longitud y de producción; no mostrar el valor en errores.
- **`WWW-Authenticate`:** el handler global podría perder la cabecera. Mitigación: `HTTPException(headers=...)` y test específico.
- **Contrato OpenAPI/frontend:** `full_name` pasa de opcional a obligatorio y se añaden fechas/estado. Mitigación: actualizar `types/api.ts`, mocks y tests de contrato; `vue-tsc` en el build.
- **Coste del hashing en tests:** argon2 con parámetros por defecto puede hacer lenta la suite. Mitigación: hasher de bajo coste inyectado en tests; producción con defaults.
- **Contraseña del bootstrap sin rotación:** no hay cambio de contraseña en v1.0. Mitigación: documentar como limitación; el operador puede cambiarla en la base de datos o se abordará en una versión posterior.
- **Open redirect:** `query.redirect` podría apuntar a un dominio externo. Mitigación: aceptar solo rutas internas que empiecen por `/` y no por `//`; test explícito.
- **Datos personales en logs:** el email es PII. Mitigación: logs solo con ids/roles; no registrar cuerpos ni emails.

## 7. Orden de implementación sugerido

1. Migración y modelo `users`; schemas `UserRead`/`RegisterRequest`.
2. Hashing y JWT (`security.py`); pruebas unitarias de hash/token.
3. Registro y login; dependency chain; 401/403 y `WWW-Authenticate`.
4. Perfil propio y administración de usuarios; último admin y concurrencia.
5. Bootstrap y validación de configuración.
6. Traducción 422, OpenAPI y pruebas de contrato.
7. Store, servicios, interceptor single-flight, guards y vistas.
8. Suite completa, cobertura, `vue-tsc`, build y validación con el gateway.

Este orden respeta TDD: cada tarea de `tasks.md` escribe primero el test en rojo y después la implementación mínima.
