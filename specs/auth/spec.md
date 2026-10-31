# Spec: Autenticación, RBAC y Perfiles (`auth`)

| Campo                      | Valor                                                                  |
| -------------------------- | ---------------------------------------------------------------------- |
| **ID del dominio**         | `AUTH`                                                                 |
| **Versión**                | 1.0                                                                    |
| **Estado**                 | **Implementada**                                                       |
| **Fecha**                  | 2026-10-31                                                             |
| **Dependencias**           | `platform` (Dominio 0, v1.0)                                           |
| **Decisiones bloqueantes** | Ninguna (A–G, hashing y política resueltas)                            |

> Esta spec describe **qué** hace el sistema, no cómo se implementa. Los detalles técnicos van en `plan.md`. Estado según R1.8 de `docs/constitution.md`: solo el usuario la marca como _Aprobada_.

## 1. Objetivo

Definir la identidad de los actores de "Mis Eventos" y los límites de acceso de cada uno: registro de usuarios, inicio de sesión, emisión y validación de JWT, contraseñas almacenadas con hash adaptativo con sal, perfil propio, gestión de perfiles por el `ADMIN` y una matriz RBAC única que los dominios posteriores reutilizan. El dominio debe impedir que un usuario vea o modifique datos de otro, que un rol sin privilegios acceda a la administración y que una cuenta desactivada siga operando con un token vigente.

## 2. Alcance

### 2.1. Incluye

- Registro público de usuarios con rol fijo `ATTENDEE`, sin alta directa de organizadores.
- Login con email y contraseña, con respuesta genérica ante credenciales inválidas.
- JWT de acceso único, firmado con HS256, con `sub` = id del usuario, `role` informativo, `iat` y `exp`.
- Cadena única de dependencias de FastAPI para autenticación y autorización (R5.2).
- Perfil propio (`GET` y `PATCH /api/auth/me`) y gestión de perfiles por `ADMIN` (listado paginado, detalle, rol y activación).
- Bootstrap idempotente del primer `ADMIN` desde variables de entorno.
- Persistencia de sesión en el frontend, guards de UX, interceptor 401/403 y vistas de login, registro, perfil y administración de usuarios.
- Frontera cerrada para `registrations`: solo `ATTENDEE` puede inscribirse a eventos.

### 2.2. No incluye

Refresh tokens, revocación de tokens, cookies HttpOnly, recuperación o cambio de contraseña, verificación de email, MFA, rate limiting, auditoría persistente, borrado físico de usuarios, login social y la lógica funcional de eventos, sesiones o inscripciones. El detalle está en §11.

## 3. Roles involucrados

| Rol         | Qué puede hacer en este dominio                                                                 |
| ----------- | ----------------------------------------------------------------------------------------------- |
| Anónimo     | Registrarse e iniciar sesión. No puede consultar perfiles ni ejecutar acciones protegidas.       |
| `ATTENDEE`  | Consultar y actualizar su propio `full_name`; podrá inscribirse a eventos en `registrations`.    |
| `ORGANIZER` | Consultar y actualizar su propio `full_name`; no puede inscribirse a eventos; gestionará sus eventos en `events`. |
| `ADMIN`     | Consultar y actualizar su propio `full_name`; listar, consultar y modificar perfiles ajenos; cambiar roles y activar/desactivar cuentas, con las restricciones de §4. |

No existen perfiles públicos: un usuario solo ve el suyo y el `ADMIN` ve todos.

## 4. Reglas de negocio

- **AUTH-BR-01 (Registro público y rol fijo):** cualquier visitante puede registrarse con email, contraseña y nombre; el rol asignado es siempre `ATTENDEE` y el cliente no puede elegir ni enviar `role` (R5.3, R6.1).
- **AUTH-BR-02 (Email normalizado y único):** el email se recorta, se convierte a minúsculas, se valida y se almacena normalizado; la unicidad se garantiza con una restricción de base de datos y el login compara sin distinguir mayúsculas (R5.5).
- **AUTH-BR-03 (Contraseña segura):** la contraseña se almacena con hash adaptativo con sal argon2id, nunca en texto plano ni en logs; cumple la política de 8–128 caracteres, no se recorta y `password_hash` no aparece en ninguna respuesta (R5.1, R5.5).
- **AUTH-BR-04 (Login genérico):** el login valida email y contraseña y responde `401` con `"Credenciales inválidas"` tanto si el email no existe, como si la contraseña es incorrecta o el usuario está inactivo; no revela el estado de la cuenta y verifica un hash ficticio cuando el email no existe (R5.8).
- **AUTH-BR-05 (JWT):** se emite un JWT HS256 firmado con `JWT_SECRET_KEY`, con `sub` = id del usuario en texto, `role` informativo, `iat` y `exp`; la expiración es `JWT_EXPIRE_MINUTES` (480 minutos por defecto); no hay `jti`, `iss`, `aud`, refresh, rotación ni revocación. La clave debe medir al menos 32 caracteres y no puede ser el placeholder en `APP_ENV=production` (R4.5, R5.2, R5.7).
- **AUTH-BR-06 (Cadena única de dependencias):** toda petición protegida ejecuta, antes de la lógica de negocio, token presente → firma → expiración → usuario existente → usuario activo → rol → propiedad; el primer fallo corta la petición con `401` (los cinco primeros pasos) o `403` (rol o propiedad) (R5.2, R5.6).
- **AUTH-BR-07 (Rol desde la base de datos):** la autorización usa el rol actual del usuario en la base de datos, no el claim del token; un cambio de rol o una desactivación surten efecto inmediato aunque el token siga vigente (R5.2, R5.3).
- **AUTH-BR-08 (Perfil propio):** el usuario autenticado consulta su perfil y solo puede modificar su `full_name`; email, rol e `is_active` no son editables por él (R5.8).
- **AUTH-BR-09 (Gestión de perfiles por el Admin):** solo `ADMIN` lista, consulta y modifica perfiles ajenos (`full_name`, `role`, `is_active`); no hay borrado físico; no puede cambiar su propio rol ni desactivarse; debe quedar al menos un `ADMIN` activo (R5.3, R5.8).
- **AUTH-BR-10 (Bootstrap idempotente):** el primer `ADMIN` se crea desde `BOOTSTRAP_ADMIN_EMAIL`, `BOOTSTRAP_ADMIN_PASSWORD` y `BOOTSTRAP_ADMIN_FULL_NAME` al arrancar, después de las migraciones; si el email ya existe no se modifica su rol ni su contraseña; una configuración parcial falla el arranque con un mensaje genérico en español y los secretos nunca se registran (R5.7).
- **AUTH-BR-11 (Sesión del frontend):** el token se envía como `Bearer` y se persiste junto al usuario en `sessionStorage` con las claves `mis_eventos.auth.token` y `mis_eventos.auth.user`; al arrancar se valida la sesión con `GET /api/auth/me`; `clearSession` y todo `401` fuera del login borran el almacenamiento; el interceptor y los guards son ayudas de UX, no controles de seguridad (R2.5, R5.6, R5.9).
- **AUTH-BR-12 (Frontera con inscripciones):** solo el rol `ATTENDEE` puede inscribirse a eventos; `ORGANIZER` y `ADMIN` reciben `403` en `registrations` (R5.3).

## 5. Modelo observable del usuario y ciclos

### 5.1. `UserRead`

Toda respuesta que devuelve un usuario usa este modelo observable:

| Campo        | Tipo              | Reglas                                                                 |
| ------------ | ----------------- | ---------------------------------------------------------------------- |
| `id`         | entero            | Identificador estable; es el valor de `sub` del JWT en texto.          |
| `email`      | texto             | Normalizado a minúsculas, sin espacios exteriores, máximo 254; único.  |
| `full_name`  | texto             | Obligatorio, `trim`, entre 2 y 120 caracteres.                         |
| `role`       | enumerado         | `ADMIN`, `ORGANIZER` o `ATTENDEE`; valores en inglés (R6.1).           |
| `is_active`  | booleano          | `true` por defecto; una cuenta inactiva no puede autenticarse.         |
| `created_at` | fecha y hora UTC  | Solo lectura, ISO 8601 con `Z` o `+00:00` (PLAT-BR-06).                |
| `updated_at` | fecha y hora UTC  | Solo lectura, se actualiza en cada cambio, ISO 8601 (PLAT-BR-06).      |

`password_hash` es un dato interno y **nunca** se incluye en `UserRead`, en el login, en el listado del admin, en OpenAPI ni en logs. Tampoco se exponen trazas, SQL ni nombres internos.

### 5.2. Ciclo de registro

1. El cliente envía `email`, `password` y `full_name` a `POST /api/auth/register`.
2. El backend recorta y convierte el email a minúsculas, valida el formato y la longitud; recorta el nombre y valida 2–120 caracteres; valida la contraseña (8–128, sin `trim`, rechazo si es solo espacios).
3. Si el email ya existe, responde `409` con `"Ya existe una cuenta con este correo electrónico"`.
4. Si no existe, calcula el hash argon2id con sal y crea el usuario con `role = ATTENDEE` e `is_active = true`.
5. Responde `201` con `UserRead`. **No emite token**; el frontend redirige al login con un aviso de éxito.

### 5.3. Ciclo de login

1. El cliente envía `email` y `password` a `POST /api/auth/login`.
2. El backend normaliza el email y busca al usuario.
3. Si no existe, verifica la contraseña contra un hash ficticio para no filtrar por tiempos y responde `401` genérico.
4. Si existe, verifica la contraseña; si es incorrecta, responde `401` genérico.
5. Si el usuario está inactivo, responde `401` genérico aunque la contraseña sea correcta.
6. Si todo es válido, emite el JWT y responde `200` con `access_token`, `token_type: "bearer"`, `expires_in` en segundos y `user` (`UserRead`).

### 5.4. Ciclo de validación JWT

Toda petición protegida recorre exactamente este orden, y el primer fallo corta la petición (R5.2):

1. **Token presente:** se lee `Authorization: Bearer <token>`; si falta, `401` con `"No autenticado o sesión expirada"` y `WWW-Authenticate: Bearer`.
2. **Firma:** se valida con HS256 y `JWT_SECRET_KEY`, con el algoritmo permitido explícitamente; una firma inválida, un algoritmo distinto o un token manipulado devuelven `401`.
3. **Expiración:** se valida `exp`; un token expirado devuelve `401`.
4. **Usuario existente:** se busca el usuario por `sub`; si no existe o fue eliminado, `401`.
5. **Usuario activo:** si `is_active` es `false`, `401` genérico, nunca `403`.
6. **Rol:** se evalúa el rol **de la base de datos** contra la matriz RBAC; si no tiene permiso, `403` con `"No tienes permisos para realizar esta acción"`. El claim `role` del token es informativo y no autoriza.
7. **Propiedad del recurso:** en los dominios que la requieran (`events`, `sessions`, `registrations`), se comprueba que el usuario sea dueño del recurso; si no, `403`. `auth` fija esta etapa como parte de la cadena, pero no la implementa para recursos que aún no existen.

### 5.5. Formato del token

- Algoritmo: `HS256`.
- Claims: `sub` (id del usuario como texto), `role` (rol en el momento de emisión, informativo), `iat` y `exp` (UTC).
- Sin `jti`, `iss` ni `aud`.
- Expiración por defecto: 480 minutos (`JWT_EXPIRE_MINUTES`), configurable.
- El token se envía solo en la cabecera `Authorization: Bearer`; no se acepta por query string ni por cookie.
- No hay refresh, rotación ni lista de revocación. El logout es local: el frontend borra el token.

## 6. Matriz RBAC

| Acción / endpoint                                      | Anónimo | `ATTENDEE` | `ORGANIZER` | `ADMIN` |
| ------------------------------------------------------ | :-----: | :--------: | :---------: | :-----: |
| `POST /api/auth/register`                              |    ✓    |     ✓      |      ✓      |    ✓    |
| `POST /api/auth/login`                                 |    ✓    |     ✓      |      ✓      |    ✓    |
| `GET /api/auth/me`                                     |    —    |     ✓      |      ✓      |    ✓    |
| `PATCH /api/auth/me`                                   |    —    |     ✓      |      ✓      |    ✓    |
| `GET /api/users`                                       |    —    |     —      |      —      |    ✓    |
| `GET /api/users/{id}`                                  |    —    |     —      |      —      |    ✓    |
| `PATCH /api/users/{id}`                                |    —    |     —      |      —      |    ✓    |
| Inscribirse a evento (`registrations`, futuro)         |    —    |     ✓      |      —      |    —    |
| CRUD de eventos (`events`, futuro)                     |    —    |     —      |      ✓      |    ✓    |
| Gestión de perfiles ajenos                             |    —    |     —      |      —      |    ✓    |

En `events`, el `ORGANIZER` gestiona solo sus propios eventos y el `ADMIN` tiene visibilidad total. Las filas de `events` y `registrations` son fronteras que este dominio deja cerradas; no se implementan aquí. La autorización real siempre está en el backend (R2.5).

## 7. Contrato de API

Todas las rutas cuelgan de `/api`. Los errores siguen el formato de `specs/platform/spec.md`: `{"detail": "<string en español>"}` y, en `422`, `errors: [{"field", "message"}]`. En los `422` derivados de validación Pydantic, `detail` es siempre el resumen genérico `"Error de validación en los datos enviados"` (o `"El cuerpo de la petición no es un JSON válido"` cuando el body no es JSON) y el mensaje específico va en `errors[].message`; los `400/401/403/404/409` conservan su `detail` específico. Las fechas se serializan en UTC ISO 8601. `password_hash` nunca se devuelve.

### 7.1. `POST /api/auth/register`

- **Descripción:** alta pública de una cuenta con rol `ATTENDEE`.
- **Autenticación / rol requerido:** público.
- **Request:**

```json
{
  "email": "ana@example.com",
  "password": "Secreto123",
  "full_name": "Ana Pérez"
}
```

- **Response `201 Created`:** `UserRead` con `role: "ATTENDEE"` e `is_active: true`. No incluye token ni `password_hash`.
- **Errores:**

| Código | Cuándo                                                                 | `detail` (español)                                                              | `errors[].message` (español)                          |
| ------ | ---------------------------------------------------------------------- | ------------------------------------------------------------------------------- | ----------------------------------------------------- |
| 409    | El email ya existe, aunque cambien mayúsculas o espacios               | `"Ya existe una cuenta con este correo electrónico"`                            | —                                                     |
| 422    | Email inválido                                                         | `"Error de validación en los datos enviados"`                                   | `"El correo electrónico no es válido"`                |
| 422    | Contraseña fuera de 8–128, solo espacios o tipo incorrecto            | `"Error de validación en los datos enviados"`                                   | Mensaje de longitud o de contraseña en español        |
| 422    | `full_name` fuera de 2–120 o vacío después de `trim`                  | `"Error de validación en los datos enviados"`                                   | Mensaje de longitud o de nombre en español            |
| 422    | Campo no permitido, por ejemplo `role`, `is_active` o `created_at`    | `"Error de validación en los datos enviados"`                                   | `"Este campo no está permitido"`                      |

### 7.2. `POST /api/auth/login`

- **Descripción:** autenticación y emisión del JWT.
- **Autenticación / rol requerido:** público.
- **Request:**

```json
{
  "email": "ana@example.com",
  "password": "Secreto123"
}
```

- **Response `200 OK`:**

```json
{
  "access_token": "<jwt>",
  "token_type": "bearer",
  "expires_in": 28800,
  "user": {
    "id": 1,
    "email": "ana@example.com",
    "full_name": "Ana Pérez",
    "role": "ATTENDEE",
    "is_active": true,
    "created_at": "2026-10-31T12:00:00Z",
    "updated_at": "2026-10-31T12:00:00Z"
  }
}
```

- **Errores:**

| Código | Cuándo                                                                 | `detail` (español)                                   |
| ------ | ---------------------------------------------------------------------- | ---------------------------------------------------- |
| 401    | Email inexistente, contraseña incorrecta o usuario inactivo            | `"Credenciales inválidas"`                           |
| 422    | Faltan campos, tipos incorrectos o campos no permitidos                | `"Error de validación en los datos enviados"` + `errors[].message` en español |

La respuesta `401` incluye `WWW-Authenticate: Bearer`. No se distingue el motivo para no revelar si el email existe. En el `422`, un campo no permitido lleva `errors[].message = "Este campo no está permitido"`.

### 7.3. `GET /api/auth/me`

- **Descripción:** perfil del usuario autenticado.
- **Autenticación / rol requerido:** cualquier usuario autenticado.
- **Response `200 OK`:** `UserRead`.
- **Errores:**

| Código | Cuándo                                                             | `detail` (español)                       |
| ------ | ------------------------------------------------------------------ | ---------------------------------------- |
| 401    | Token ausente, inválido, expirado, usuario inexistente o inactivo  | `"No autenticado o sesión expirada"`     |

### 7.4. `PATCH /api/auth/me`

- **Descripción:** actualización del propio `full_name`.
- **Autenticación / rol requerido:** cualquier usuario autenticado.
- **Request:**

```json
{ "full_name": "Ana María Pérez" }
```

- **Response `200 OK`:** `UserRead` actualizado.
- **Errores:**

| Código | Cuándo                                                                 | `detail` (español)                                                              | `errors[].message` (español)                                  |
| ------ | ---------------------------------------------------------------------- | ------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| 401    | Token ausente, inválido, expirado, usuario inexistente o inactivo      | `"No autenticado o sesión expirada"`                                            | —                                                             |
| 422    | `full_name` fuera de 2–120 o vacío después de `trim`                  | `"Error de validación en los datos enviados"`                                   | Mensaje de longitud o de nombre en español                    |
| 422    | Body vacío o sin `full_name`                                           | `"Error de validación en los datos enviados"`                                   | `"Debes indicar al menos un campo para actualizar"`           |
| 422    | Campo no permitido (`email`, `role`, `is_active`, etc.)                | `"Error de validación en los datos enviados"`                                   | `"Este campo no está permitido"`                              |

### 7.5. `GET /api/users`

- **Descripción:** listado paginado de perfiles para el `ADMIN`.
- **Autenticación / rol requerido:** `ADMIN`.
- **Query:** `page` (defecto 1, mínimo 1), `size` (defecto 10, mínimo 1, máximo 50), `role` opcional (`ADMIN`, `ORGANIZER`, `ATTENDEE`), `is_active` opcional (`true` o `false`).
- **Response `200 OK`:** sobre de paginación de `PLAT-BR-05`, ordenado por `id` ascendente:

```json
{
  "items": [
    {
      "id": 1,
      "email": "ana@example.com",
      "full_name": "Ana Pérez",
      "role": "ATTENDEE",
      "is_active": true,
      "created_at": "2026-10-31T12:00:00Z",
      "updated_at": "2026-10-31T12:00:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "size": 10,
  "pages": 1
}
```

- **Errores:**

| Código | Cuándo                                              | `detail` (español)                                      |
| ------ | --------------------------------------------------- | ------------------------------------------------------- |
| 401    | Token ausente, inválido o expirado                  | `"No autenticado o sesión expirada"`                                    |
| 403    | El usuario autenticado no es `ADMIN`                | `"No tienes permisos para realizar esta acción"`                        |
| 422    | `page`, `size`, `role` o `is_active` inválidos      | `"Error de validación en los datos enviados"` + `errors[].message` en español |

Si `page > pages`, se devuelve `200` con `items: []`, el `total` real y `pages` calculado (PLAT-BR-05).

### 7.6. `GET /api/users/{id}`

- **Descripción:** detalle de un perfil para el `ADMIN`.
- **Autenticación / rol requerido:** `ADMIN`.
- **Response `200 OK`:** `UserRead`.
- **Errores:**

| Código | Cuándo                                  | `detail` (español)                               |
| ------ | --------------------------------------- | ------------------------------------------------ |
| 401    | Token ausente, inválido o expirado      | `"No autenticado o sesión expirada"`             |
| 403    | El usuario autenticado no es `ADMIN`    | `"No tienes permisos para realizar esta acción"` |
| 404    | El usuario no existe                    | `"Usuario no encontrado"`                        |

### 7.7. `PATCH /api/users/{id}`

- **Descripción:** actualización de `full_name`, `role` e `is_active` por el `ADMIN`.
- **Autenticación / rol requerido:** `ADMIN`.
- **Request:** al menos uno de los campos; `email` no está permitido.

```json
{
  "full_name": "Ana Pérez",
  "role": "ORGANIZER",
  "is_active": true
}
```

- **Response `200 OK`:** `UserRead` actualizado.
- **Errores:**

| Código | Cuándo                                                                 | `detail` (español)                                                              | `errors[].message` (español)                                  |
| ------ | ---------------------------------------------------------------------- | ------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| 400    | El `ADMIN` intenta cambiar su propio rol                               | `"No puedes cambiar tu propio rol"`                                             | —                                                             |
| 400    | El `ADMIN` intenta desactivarse a sí mismo                             | `"No puedes desactivar tu propia cuenta"`                                       | —                                                             |
| 401    | Token ausente, inválido, expirado o usuario inactivo                   | `"No autenticado o sesión expirada"`                                            | —                                                             |
| 403    | El usuario autenticado no es `ADMIN`                                   | `"No tienes permisos para realizar esta acción"`                                | —                                                             |
| 404    | El usuario no existe                                                   | `"Usuario no encontrado"`                                                       | —                                                             |
| 409    | Se intenta degradar o desactivar al último `ADMIN` activo              | `"Debe existir al menos un administrador activo"`                               | —                                                             |
| 422    | Body vacío o sin ningún campo actualizable                              | `"Error de validación en los datos enviados"`                                   | `"Debes indicar al menos un campo para actualizar"`           |
| 422    | `role` con valor fuera de `ADMIN`/`ORGANIZER`/`ATTENDEE` o `is_active` no booleano | `"Error de validación en los datos enviados"`                                   | Mensaje de enumeración o de tipo en español                   |
| 422    | `email` u otro campo no permitido                                       | `"Error de validación en los datos enviados"`                                   | `"Este campo no está permitido"`                              |

El `ADMIN` puede actualizar el `full_name` de cualquier usuario, incluido el suyo; los campos `role` e `is_active` sobre sí mismo se rechazan con `400`.

### 7.8. Endpoints no expuestos

No existen en este dominio: `POST /api/auth/logout`, `POST /api/auth/refresh`, `DELETE /api/users/{id}`, `POST /api/users`, cambio o recuperación de contraseña y verificación de email. El logout es local en el frontend.

### 7.9. Convenciones de respuesta

- Ninguna ruta devuelve `204 No Content`: no hay borrado físico y toda actualización devuelve el recurso actualizado (`UserRead`) con `200`.
- Los errores usan el formato de `specs/platform/spec.md` (`detail` en español y, en `422`, `errors[].message`); las respuestas de error nunca incluyen `password_hash` ni detalles internos.
- En los `422` de validación, `detail` es el resumen genérico `"Error de validación en los datos enviados"` y el mensaje concreto va en `errors[].message`; si el body no es JSON, `detail = "El cuerpo de la petición no es un JSON válido"`.
- Los `401` incluyen `WWW-Authenticate: Bearer`; los `403` no revelan datos del recurso.

## 8. Criterios de aceptación (EARS)

Cada criterio tiene al menos un test cuyo nombre incluye su ID (R1.5, R1.9).

| ID               | Criterio                                                                                                                                                                                                                                                                                                                                 | Reglas                    |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------- |
| **AUTH-AC-01**   | Cuando un visitante envía un registro válido con email, contraseña y nombre, el sistema debe responder `201` con `UserRead`, `role = "ATTENDEE"`, `is_active = true`, sin token y sin `password_hash`.                                                                                                                                      | AUTH-BR-01, AUTH-BR-03    |
| **AUTH-AC-02**   | Si el email de registro ya existe, incluso con mayúsculas o espacios diferentes, entonces el sistema debe responder `409` con `"Ya existe una cuenta con este correo electrónico"` y no debe crear una segunda fila.                                                                                                                        | AUTH-BR-02                |
| **AUTH-AC-03**   | Si el cuerpo del registro incluye `role`, `is_active` u otro campo no permitido, entonces el sistema debe responder `422` con `detail = "Error de validación en los datos enviados"` y `errors[].message = "Este campo no está permitido"`, y no debe crear ningún usuario; un registro sin esos campos crea el usuario con `role = "ATTENDEE"`.                                                              | AUTH-BR-01                |
| **AUTH-AC-04**   | Cuando se registra un email con espacios exteriores o mayúsculas, el sistema debe almacenarlo recortado y en minúsculas; si el email es inválido o el `full_name` queda fuera de 2–120 tras `trim`, entonces debe responder `422` con `detail = "Error de validación en los datos enviados"` y `errors[].message` en español (`"El correo electrónico no es válido"` o el mensaje de longitud).          | AUTH-BR-02, AUTH-BR-03    |
| **AUTH-AC-05**   | Cuando la contraseña mide exactamente 8 o 128 caracteres, el sistema debe aceptarla; si mide 7 o 129, o está compuesta solo por espacios, entonces debe responder `422` con `detail` genérico y `errors[].message` en español; la contraseña no se recorta y se almacena con hash argon2id con sal.                                                                                                         | AUTH-BR-03                |
| **AUTH-AC-06**   | Cuando un usuario activo inicia sesión con credenciales válidas, el sistema debe responder `200` con `access_token`, `token_type = "bearer"`, `expires_in` en segundos, `user` y un JWT HS256 cuyos claims sean `sub`, `role`, `iat` y `exp`, sin `jti`, `iss` ni `aud`.                                                                | AUTH-BR-04, AUTH-BR-05    |
| **AUTH-AC-07**   | Si el email no existe, la contraseña es incorrecta o el usuario está inactivo, entonces el sistema debe responder `401` con `"Credenciales inválidas"` y no debe revelar cuál de las tres condiciones ocurrió, verificando un hash ficticio cuando el email no existe.                                                                   | AUTH-BR-04                |
| **AUTH-AC-08**   | Si una petición protegida no incluye token, entonces el sistema debe responder `401` con `"No autenticado o sesión expirada"` y conservar la cabecera `WWW-Authenticate: Bearer`.                                                                                                                                                          | AUTH-BR-06                |
| **AUTH-AC-09**   | Si el token tiene firma inválida, fue manipulado, usa un algoritmo distinto de HS256 o declara `alg = none`, entonces el sistema debe responder `401` sin aceptar el token.                                                                                                                                                               | AUTH-BR-06                |
| **AUTH-AC-10**   | Si el token está expirado, entonces el sistema debe responder `401` con `"No autenticado o sesión expirada"` aunque la firma sea válida.                                                                                                                                                                                                 | AUTH-BR-06                |
| **AUTH-AC-11**   | Si el token es válido pero el usuario de `sub` no existe o fue eliminado de la base de datos, entonces el sistema debe responder `401`.                                                                                                                                                                                                  | AUTH-BR-06, AUTH-BR-07    |
| **AUTH-AC-12**   | Si el token es válido pero el usuario tiene `is_active = false`, entonces el sistema debe responder `401` genérico, nunca `403`, y el frontend debe limpiar la sesión.                                                                                                                                                                     | AUTH-BR-06, AUTH-BR-07    |
| **AUTH-AC-13**   | Cuando el rol del usuario cambia en la base de datos o el claim `role` del token no coincide con la base de datos, el sistema debe autorizar usando el rol actual de la base de datos y no el claim.                                                                                                                                      | AUTH-BR-07                |
| **AUTH-AC-14**   | Cuando un usuario autenticado consulta `GET /api/auth/me`, el sistema debe devolver su propio `UserRead`; cuando actualiza `full_name`, debe aceptarlo; si intenta cambiar `email`, `role` o `is_active`, entonces debe responder `422` con `detail = "Error de validación en los datos enviados"` y `errors[].message = "Este campo no está permitido"`.                                                 | AUTH-BR-08                |
| **AUTH-AC-15**   | Cuando un `ADMIN` lista usuarios con `page`, `size`, `role` e `is_active`, el sistema debe devolver el sobre de paginación con `UserRead`; cuando consulta o actualiza el `full_name`, `role` o `is_active` de otro usuario, debe responder `200` con el perfil actualizado.                                                               | AUTH-BR-09                |
| **AUTH-AC-16**   | Si un `ATTENDEE` u `ORGANIZER` intenta listar, consultar o modificar perfiles ajenos, entonces el sistema debe responder `403` con `"No tienes permisos para realizar esta acción"` y el frontend debe mantener la sesión.                                                                                                                | AUTH-BR-06, AUTH-BR-09    |
| **AUTH-AC-17**   | Si un `ADMIN` intenta cambiar su propio rol o desactivar su propia cuenta, entonces el sistema debe responder `400` con `"No puedes cambiar tu propio rol"` o `"No puedes desactivar tu propia cuenta"`, respectivamente.                                                                                                                  | AUTH-BR-09                |
| **AUTH-AC-18**   | Si se intenta degradar o desactivar al único `ADMIN` activo, entonces el sistema debe responder `409` con `"Debe existir al menos un administrador activo"`; si dos peticiones lo intentan a la vez, al menos una debe fallar y debe quedar un `ADMIN` activo.                                                                             | AUTH-BR-09                |
| **AUTH-AC-19**   | Si el `ADMIN` envía un body vacío a `PATCH /api/users/{id}`, entonces el sistema debe responder `422` con `detail` genérico y `errors[].message = "Debes indicar al menos un campo para actualizar"`; si el rol es inválido, `422` con `detail` genérico y `errors[].message` en español; si el usuario no existe, `404` con `"Usuario no encontrado"`.                                                     | AUTH-BR-09                |
| **AUTH-AC-20**   | Cuando el sistema arranca con `BOOTSTRAP_ADMIN_EMAIL` y `BOOTSTRAP_ADMIN_PASSWORD` válidos y el email no existe, debe crear un único `ADMIN`; cuando vuelve a arrancar, no debe duplicarlo ni modificar su rol o contraseña.                                                                                                                | AUTH-BR-10                |
| **AUTH-AC-21**   | Si el email de bootstrap ya existe con un rol distinto de `ADMIN`, entonces el sistema no debe modificar su rol ni su contraseña, no debe duplicarlo y debe continuar sin escalar privilegios por entorno.                                                                                                                                  | AUTH-BR-10                |
| **AUTH-AC-22**   | Si solo se define una de `BOOTSTRAP_ADMIN_EMAIL` o `BOOTSTRAP_ADMIN_PASSWORD`, entonces el arranque debe fallar con un mensaje genérico en español y sin incluir la contraseña ni la clave en el error.                                                                                                                                     | AUTH-BR-10                |
| **AUTH-AC-23**   | Si `JWT_SECRET_KEY` mide menos de 32 caracteres o, con `APP_ENV=production`, conserva el placeholder, entonces el arranque debe fallar sin mostrar el valor; el repositorio y `.env.example` no deben contener secretos reales.                                                                                                             | AUTH-BR-05                |
| **AUTH-AC-24**   | Cuando el frontend inicia sesión, debe persistir token y usuario en `sessionStorage` con las claves `mis_eventos.auth.token` y `mis_eventos.auth.user`; al arrancar debe validar con `GET /api/auth/me`; `clearSession` y el logout deben borrar ambas claves.                                                                              | AUTH-BR-11                |
| **AUTH-AC-25**   | Si varias peticiones en vuelo reciben `401` fuera del login, entonces el frontend debe limpiar la sesión, mostrar un solo aviso y redirigir una sola vez al login conservando `query.redirect`; si el `401` proviene del login, no debe redirigir y debe mostrar `"Credenciales inválidas"`.                                                | AUTH-BR-06, AUTH-BR-11    |
| **AUTH-AC-26**   | Si una petición recibe `403`, entonces el frontend debe mantener la sesión y mostrar un aviso en español; si recibe `401` fuera del login, debe limpiar la sesión y redirigir; si recibe `401` en el login, debe mostrar el mensaje de credenciales sin redirigir.                                                                          | AUTH-BR-06, AUTH-BR-11    |
| **AUTH-AC-27**   | Cuando un usuario no autenticado navega a una ruta con `requiresAuth`, el guard debe redirigirlo al login con `query.redirect`; tras autenticarse debe volver a esa ruta; si el rol no coincide con `meta.roles` o el destino es externo, debe redirigir a `home` o ignorarlo.                                                              | AUTH-BR-11                |
| **AUTH-AC-28**   | Cuando se consulta `/api/openapi.json`, el contrato debe exponer el esquema de seguridad HTTP Bearer (`HTTPBearer`) en `components.securitySchemes`, todos los endpoints de §7 y `UserRead` sin `password_hash`; los DTO del frontend deben coincidir con ese contrato.                                                                       | AUTH-BR-05                |
| **AUTH-AC-29**   | El sistema no debe incluir `password`, `password_hash`, `JWT_SECRET_KEY` ni datos personales en respuestas, logs, mensajes de error ni en el repositorio; los errores no deben exponer trazas, SQL ni nombres internos.                                                                                                                     | AUTH-BR-03, AUTH-BR-06    |
| **AUTH-AC-30**   | Cuando se evalúa la política de inscripción, solo el rol `ATTENDEE` debe poder inscribirse a eventos; `ORGANIZER` y `ADMIN` deben recibir `403` en `registrations`, conforme a la frontera fijada aquí.                                                                                                                                    | AUTH-BR-12                |
| **AUTH-AC-31**   | Cuando un `ADMIN` lista usuarios con parámetros válidos, el sistema debe devolver el sobre de `PLAT-BR-05`; con `page < 1`, `size < 1`, `size > 50`, `role` inválido o `is_active` no booleano debe responder `422` con `detail` genérico y `errors[].message` en español; con `page > pages` debe responder `200` con `items: []`; y `GET /api/users/{id}` con id inexistente debe responder `404` con `"Usuario no encontrado"`. | AUTH-BR-09                |

## 9. Casos límite

- Email con mayúsculas y espacios exteriores: se normaliza y no crea duplicados; el login funciona con cualquier combinación de mayúsculas.
- Contraseña de exactamente 8 caracteres: válida; exactamente 128: válida; 7 o 129: `422`; contraseña de solo espacios: `422`; contraseña con espacios interiores: válida y sin `trim`.
- `full_name` con espacios exteriores: se recorta; con 1 o 121 caracteres: `422`; con acentos, guiones o apóstrofos: válido.
- Registro con `role` en el body: `422` con `detail` genérico y `errors[].message = "Este campo no está permitido"`; no se crea ningún usuario.
- Email duplicado por concurrencia: la restricción única decide; una petición recibe `409` y no se crean dos filas.
- Login con email inexistente, contraseña incorrecta o usuario inactivo: mismo `401` y mismo `detail`; el tiempo de respuesta no debe permitir distinguir el caso.
- Token ausente, con firma manipulada, con `alg = none`, con algoritmo distinto de HS256, sin `exp`, con `sub` no numérico o expirado: `401`.
- Token válido de un usuario desactivado después de la emisión: `401`; el frontend limpia la sesión.
- Token válido de un usuario cuyo rol cambió después de la emisión: la autorización usa el rol nuevo de la base de datos.
- Token válido de un usuario eliminado manualmente de la base de datos: `401`.
- Varias peticiones en vuelo que reciben `401`: un solo aviso y una sola redirección; no se reintenta automáticamente.
- `401` del login: no redirige; muestra `"Credenciales inválidas"`.
- `403` en una vista de administración: la sesión se conserva y se muestra el aviso; el guard puede redirigir a `home`.
- `page > pages`: `200` con `items: []`, `total` real y `pages` calculado; `page < 1`, `size < 1`, `size > 50`, `role` inválido o `is_active` no booleano: `422` con `detail` genérico y `errors[].message` en español.
- `GET /api/users/{id}` con id inexistente: `404` con `"Usuario no encontrado"`.
- `PATCH /api/users/{id}` con body vacío: `422` con `errors[].message = "Debes indicar al menos un campo para actualizar"`; con `email`: `422` con `errors[].message = "Este campo no está permitido"`; con rol inválido: `422`; con id inexistente: `404`.
- Bootstrap con email ya existente y rol distinto: no se modifica ni se duplica; bootstrap con una sola variable: falla el arranque con mensaje genérico.
- Concurrencia en la degradación/desactivación de administradores: al menos una petición falla y queda un `ADMIN` activo.
- `WWW-Authenticate: Bearer` se conserva aunque el manejador global traduzca el `detail`.
- `422` de `EmailStr` y de campo no permitido: `detail` genérico y `errors[].message` en español, sin mensajes en inglés de Pydantic; un body que no es JSON usa `"El cuerpo de la petición no es un JSON válido"`.
- `JWT_SECRET_KEY` corta o placeholder en producción: fallo de arranque sin mostrar el valor.
- `sessionStorage` con JSON corrupto o token huérfano: el store limpia la sesión y redirige al login.

## 10. Privacidad y seguridad

- R5.8: el login no revela si el email existe; solo el `ADMIN` ve perfiles ajenos; no se registran emails, contraseñas, hashes ni datos personales en logs.
- R5.1: las contraseñas se almacenan con argon2id y sal; `password_hash` nunca se serializa, se registra ni se expone en OpenAPI.
- R5.5: todas las entradas usan schemas de validación; las respuestas usan `UserRead` explícito.
- R5.6: `401` para token ausente, inválido, expirado o usuario inactivo; `403` para usuario autenticado sin permisos.
- R5.7: `JWT_SECRET_KEY` y las credenciales de bootstrap solo viven en variables de entorno; `.env` no se versiona y `.env.example` no contiene valores reales.
- R5.9: el token es accesible desde JavaScript; queda prohibido `v-html` con contenido de usuario. `sessionStorage` reduce la persistencia frente a `localStorage`, pero no elimina el riesgo de XSS.
- El token solo se acepta en la cabecera `Authorization: Bearer`; no se acepta por query string ni por cookie, por lo que no se introduce CSRF.
- Los errores no exponen trazas, SQL, nombres internos ni el valor de la clave.

## 11. Fuera de alcance

- Refresh tokens, rotación, revocación, lista negra y cookies HttpOnly.
- Recuperación o cambio de contraseña, verificación de email, MFA y login social.
- Rate limiting, bloqueo por intentos fallidos y captcha.
- Auditoría persistente en tabla; solo logs sin datos personales.
- Borrado físico de usuarios; se usa `is_active`.
- Edición de email por el usuario o por el `ADMIN`; el email es inmutable en v1.0.
- Alta directa de organizadores o de usuarios por el `ADMIN`; solo registro + promoción.
- `POST /api/auth/logout`, `POST /api/auth/refresh`, `DELETE /api/users/{id}` y `POST /api/users`.
- Lógica funcional de `events`, `sessions` y `registrations`; solo se fija aquí la frontera de qué rol puede inscribirse.
- CORS abierto, WebSockets, colas, workers, ORM alternativo o UI kit.
- Cambio de la semántica 401/403 del interceptor ya validado en `platform`.

## 12. Decisiones resueltas

Todas las decisiones se resolvieron con el usuario el **2026-10-31** y se aplican en esta spec.

| Fecha      | Pregunta                                 | Decisión                                                                                                                                                                                                                           | Motivo                                                                                          |
| ---------- | ---------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| 2026-10-31 | A. Estrategia de JWT                     | Token único de acceso HS256; `sub = str(user.id)`, `role` informativo, `iat`, `exp`; expiración 480 min configurable; sin `jti`, `iss`, `aud`, refresh, rotación, revocación ni cookies; logout local; autorización con rol de BD. | R4.5 y plazo de 5 días; el interceptor 401 ya resuelve la reautenticación; sin infraestructura de refresh. |
| 2026-10-31 | A. Clave y expiración                    | `JWT_SECRET_KEY` ≥32 caracteres; `JWT_EXPIRE_MINUTES=480`; fallo en `APP_ENV=production` si se usa el placeholder, sin mostrar el valor.                                                                                            | R5.7 y prevención de arranques con clave conocida.                                              |
| 2026-10-31 | B. Bootstrap del primer Admin            | Variables `BOOTSTRAP_ADMIN_EMAIL`, `BOOTSTRAP_ADMIN_PASSWORD`, `BOOTSTRAP_ADMIN_FULL_NAME`; al arrancar tras migraciones; idempotente; email existente no se modifica; configuración parcial falla; `IntegrityError` = ya existe. | Sin secretos en el repo y sin pasos manuales; evita escalada por entorno.                       |
| 2026-10-31 | C. Creación de organizadores y roles     | Todo registro nace `ATTENDEE`; solo `ADMIN` promueve por `PATCH /api/users/{id}`; sin alta directa; sin auto-cambio de rol ni auto-desactivación; último admin protegido con `409`; sin auditoría persistente.                    | Único camino de alta, menos superficie y protección del acceso administrativo.                  |
| 2026-10-31 | D. Perfil                                | `id`, `email` inmutable, `full_name` obligatorio 2–120, `role`, `is_active`, `created_at`, `updated_at` UTC; el usuario edita solo `full_name`; el `ADMIN` edita `full_name`, `role`, `is_active`; inactivo ⇒ `401`; sin borrado.  | Modelo mínimo para el bonus de perfiles y R5.8.                                                 |
| 2026-10-31 | E. Roles que pueden inscribirse          | Solo `ATTENDEE`; `ORGANIZER` y `ADMIN` reciben `403` en `registrations`.                                                                                                                                                            | Coherente con la arquitectura (el Organizador no ve "Inscribirse") y cierra la frontera.        |
| 2026-10-31 | F. Persistencia de sesión                | `sessionStorage` con `mis_eventos.auth.token` y `mis_eventos.auth.user`; validación con `/api/auth/me` al arrancar; `clearSession` y `401` borran el almacenamiento.                                                               | Sobrevive a recargas sin la persistencia indefinida de `localStorage`; menor ventana ante XSS.   |
| 2026-10-31 | G. Contrato HTTP                         | JSON puro; registro `201` sin token; login `200` con `access_token`, `token_type`, `expires_in`, `user`; perfiles propios y administración según §7; sin logout, refresh, delete ni alta directa.                                | Contrato simple, alineado con OpenAPI y con el interceptor existente.                           |
| 2026-10-31 | Hashing                                  | argon2id con `argon2-cffi` (`PasswordHasher`), sal por defecto.                                                                                                                                                                      | R5.1; algoritmo adaptativo recomendado y sin límite de 72 bytes.                                |
| 2026-10-31 | Política de contraseña                   | 8–128 caracteres; sin reglas de composición; sin `trim`; rechazo si es solo espacios.                                                                                                                                               | Longitud como criterio principal; evita fricción innecesaria.                                    |
| 2026-10-31 | Email                                    | `trim` + minúsculas, máximo 254, validación con `EmailStr` (`email-validator`), unicidad por constraint.                                                                                                                            | Evita duplicados por mayúsculas/espacios y valida formato.                                      |
| 2026-10-31 | Registro                                 | No autentica automáticamente; `201` con `UserRead` y el frontend redirige al login con aviso de éxito.                                                                                                                              | Mantiene el login como única puerta de emisión del JWT.                                         |
| 2026-10-31 | Paginación del listado                   | Reutiliza `PLAT-BR-05`; orden por `id` ascendente; `page > pages` ⇒ `200` con `items: []`.                                                                                                                                           | Consistencia con `platform` y sin cálculo en el frontend.                                       |
| 2026-10-31 | Errores 401                              | `"No autenticado o sesión expirada"` + `WWW-Authenticate: Bearer`; en login `"Credenciales inválidas"`; hash ficticio si el email no existe.                                                                                        | R5.6 y R5.8; evita filtrar existencia de cuenta y tiempos.                                      |
| 2026-10-31 | Frontend 401 en vuelo                    | Un solo aviso/redirección (single-flight), conservando `query.redirect`; sin reintento automático.                                                                                                                                  | Evita duplicar avisos y navegaciones.                                                           |

## 13. Historial

| Versión | Fecha      | Cambio                                                                                                                                                                     |
| ------- | ---------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 0.1     | 2026-10-31 | Borrador inicial con las decisiones A–G, hashing, política de contraseña, email, registro, paginación y errores 401.                                                        |
| 0.1     | 2026-10-31 | Revisión de consistencia: `AUTH-AC-03` sin contradicción de creación, semántica única de `422` (`detail` genérico + `errors[].message`), `AUTH-AC-28` con `HTTPBearer` y nuevo `AUTH-AC-31` de paginación/filtros del listado. |
| 1.0     | 2026-10-31 | Aprobación explícita del usuario ("Apruebo la spec de auth") y paso a estado Aprobada; sin cambios de contenido respecto a 0.1. |
| 1.0     | 2026-10-31 | Paso a En implementación tras la aprobación y la verificación de que no quedan decisiones bloqueantes; inicio del TDD por B1. |
| 1.0     | 2026-10-31 | Validación del reviewer (¿pasa? sí, 31/31 criterios AUTH-AC-01..31 verificados en verde) y cierre en estado Implementada. |
