# Spec: Plataforma Base (`platform`)

| Campo                      | Valor       |
| -------------------------- | ----------- |
| **ID del dominio**         | `PLAT`             |
| **Versión**                | 1.0                |
| **Estado**                 | Implementada       |
| **Fecha**                  | 2026-10-31         |
| **Dependencias**           | _(Ninguna)_        |
| **Decisiones bloqueantes** | Ninguna            |

> Esta spec describe **qué** hace el sistema en el dominio transversal `platform`, no cómo se implementa. Los detalles técnicos van en `plan.md`. Estado según R1.8 de `docs/constitution.md`: solo el usuario la marca como _Aprobada_.

## 1. Objetivo

Establecer los cimientos transversales de infraestructura, backend y frontend sobre los que se construirán todos los dominios funcionales de "Mis Eventos": orquestación de contenedores con Nginx como punto de entrada único (`/`, `/api`, `/api/media/`), esqueleto de la API en FastAPI con PostgreSQL (`pg_trgm`), Alembic, caché Redis prescindible, convención común de paginación, fechas en UTC y formato estandarizado de errores en español (incluido el código `422`), así como la SPA base en Vue 3 + TypeScript ligero con enrutamiento diferido (`lazy loading`), guards de UX, Pinia, cliente Axios con semántica estricta `401`/`403`, componentes reutilizables y suites de pruebas (`pytest` contra PostgreSQL y `Vitest`).

## 2. Roles involucrados

| Rol         | Qué puede hacer en este dominio                                                                                                                                                   |
| ----------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Anónimo     | Acceder a la aplicación web (`/`), consultar el estado de salud (`GET /api/health`), la especificación OpenAPI (`/api/docs`, `/api/openapi.json`) y los recursos en `/api/media/`. |
| `ATTENDEE`  | Igual que Anónimo, más navegación autenticada gestionada por el router y el interceptor de sesión en el cliente web.                                                              |
| `ORGANIZER` | Igual que `ATTENDEE`, con evaluación de acceso en rutas protegidas por rol (guards de UX en el frontend).                                                                         |
| `ADMIN`     | Igual que `ORGANIZER`, con acceso de UX a las rutas de administración en el frontend.                                                                                             |

## 3. Reglas de negocio

- **PLAT-BR-01 (Punto de entrada único y cero CORS):** Todo el tráfico HTTP de la plataforma ingresa por el gateway Nginx (`/` → contenedor `web`, `/api` → contenedor `api`, `/api/media/` → volumen `media` en solo lectura); el backend nunca habilita `CORSMiddleware` con orígenes cruzados y el frontend consume la API únicamente mediante la ruta relativa `/api` (R2.1, R2.2).
- **PLAT-BR-02 (Estado de salud y Redis prescindible):** El endpoint `GET /api/health` verifica la conectividad con PostgreSQL y Redis; si PostgreSQL responde, devuelve `200 OK` reportando `"redis": "ok"` o `"redis": "degraded"` sin fallar aunque Redis no esté disponible (R4.4), y si PostgreSQL no responde devuelve `503 Service Unavailable`.
- **PLAT-BR-03 (Contrato OpenAPI):** El backend expone su documentación interactiva y el esquema del contrato en `/api/docs` y `/api/openapi.json` sin servir archivos ni rutas del frontend (R2.3, R2.4).
- **PLAT-BR-04 (Formato único de error HTTP y normalización 422 en español):** Todo error HTTP devuelto por la API contiene el campo `detail` como cadena de texto (`string`) en español sin exponer trazas de pila, sentencias SQL ni nombres internos (R5.8, Principio 6); en los errores `422 Unprocessable Entity` de validación, `detail` es un resumen legible en español acompañado de la lista `errors: [{"field": "<campo>", "message": "<mensaje en español>"}]`.
- **PLAT-BR-05 (Convención común de paginación 1-indexed):** Todo listado paginado recibe los parámetros de consulta `page` (por defecto `1`, mínimo `1`) y `size` (por defecto `10`, mínimo `1`, máximo `50`), y devuelve el sobre `{ "items": [...], "total": <int>, "page": <int>, "size": <int>, "pages": <int> }`, donde `pages = ceil(total / size)` (`0` cuando `total = 0`).
- **PLAT-BR-06 (Almacenamiento y serialización de fechas en UTC):** Todas las fechas y marcas de tiempo gestionadas por la plataforma se normalizan, almacenan y serializan en UTC en formato ISO 8601 (`Z` o `+00:00`).
- **PLAT-BR-07 (Migraciones automáticas y extensión `pg_trgm`):** Al iniciar el contenedor de la API se aplican las migraciones de Alembic pendientes antes de levantar el servidor HTTP, garantizando que la extensión `pg_trgm` esté habilitada en PostgreSQL y que la suite `pytest` se ejecute exclusivamente contra PostgreSQL en contenedor con aislamiento determinista (R3.6, R3.7).
- **PLAT-BR-08 (Semántica del cliente HTTP en el frontend):** El interceptor global de Axios (`baseURL: "/api"`) limpia la sesión y redirige a `/login` conservando la ruta de origen ante un `401` (excepto cuando la petición proviene del propio endpoint de login), mantiene la sesión activa y muestra un aviso en español ante un `403` (R5.6), muestra el `detail` en español devuelto por la API ante `404`, `409` o `422`, y muestra un mensaje genérico en español ante errores `5xx` o fallos de red.
- **PLAT-BR-09 (Enrutamiento diferido, UX base, minificación y prevención de XSS):** El frontend carga todas las rutas de forma diferida (`lazy loading`), aplica guards de navegación como ayuda de UX según metadatos de autenticación/rol (R2.5), provee componentes base reutilizables (`BaseInput.vue`, `BaseButton.vue`, `BaseSpinner.vue`, `BaseSkeleton.vue`, `BaseAlert.vue`) con textos en español sin usar `v-html` con contenido de usuario (R5.9, R6.2), y genera un build de producción minificado sin source maps públicos.

## 4. Contrato de API

Todas las rutas cuelgan de `/api`. Los errores siguen el formato definido en la sección 4.2 con `detail` en español.

### 4.1 `GET /api/health`

- **Descripción:** Verifica la disponibilidad del servicio de API, la conexión obligatoria a PostgreSQL y el estado de la caché prescindible Redis.
- **Autenticación / rol requerido:** Público (Anónimo).
- **Request:** Sin cuerpo ni parámetros.
- **Response `200 OK` (PostgreSQL operativo, Redis operativo o degradado):**

  ```json
  {
    "status": "ok",
    "database": "ok",
    "redis": "ok"
  }
  ```

  *(Si Redis no responde o no está disponible, el código HTTP sigue siendo `200 OK` y el campo `"redis"` toma el valor `"degraded"` en cumplimiento de R4.4).*

- **Errores:**

  | Código | Cuándo                                    | `detail` (español)                        |
  | ------ | ----------------------------------------- | ----------------------------------------- |
  | 503    | PostgreSQL no responde o rechaza conexión | `"Servicio de base de datos no disponible"` |

### 4.2 Contrato transversal de errores HTTP y validación `422`

- **Errores HTTP estándar (`400`, `401`, `403`, `404`, `409`, `500`, `503`):**

  ```json
  {
    "detail": "Descripción clara del problema en español"
  }
  ```

  | Código | Caso transversal en `platform`            | `detail` por defecto (español)                     |
  | ------ | ----------------------------------------- | -------------------------------------------------- |
  | 401    | Token ausente, inválido o expirado        | `"No autenticado o sesión expirada"`               |
  | 403    | Usuario autenticado sin permisos          | `"No tienes permisos para realizar esta acción"`   |
  | 404    | Ruta o recurso inexistente                | `"Recurso no encontrado"`                          |
  | 405    | Método HTTP no permitido en la ruta       | `"Método no permitido"`                            |
  | 500    | Excepción interna no controlada           | `"Error interno del servidor"`                     |
  | 503    | Base de datos no disponible en health     | `"Servicio de base de datos no disponible"`        |

- **Errores de validación `422 Unprocessable Entity` (`RequestValidationError`):**

  ```json
  {
    "detail": "Error de validación en los datos enviados",
    "errors": [
      {
        "field": "size",
        "message": "El valor debe ser menor o igual a 50"
      }
    ]
  }
  ```

  - `detail` es **siempre** un `string` en español apto para mostrarse directamente en alertas o notificaciones globales.
  - `errors` contiene la lista detallada por campo (`field` con la ruta del campo en notación punto o nombre de parámetro, y `message` traducido al español).

### 4.3 Convención transversal de paginación

- **Parámetros Query de entrada:**
  - `page`: entero opcional, por defecto `1`, restricción `>= 1`.
  - `size`: entero opcional, por defecto `10`, restricción `>= 1` y `<= 50`.
- **Sobre (envelope) de respuesta `200 OK`:**

  ```json
  {
    "items": [],
    "total": 0,
    "page": 1,
    "size": 10,
    "pages": 0
  }
  ```

### 4.4 Documentación del contrato OpenAPI

- `GET /api/openapi.json` → devuelve `200 OK` con el documento JSON OpenAPI 3.x generado por FastAPI.
- `GET /api/docs` → devuelve `200 OK` con la interfaz Swagger UI apuntando a `/api/openapi.json`.

## 5. Criterios de aceptación (EARS)

Cada criterio tiene al menos un test cuyo nombre incluye su ID (R1.5, R1.9).

| ID             | Criterio                                                                                                                                                                                                                                                      | Reglas                   |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------ |
| **PLAT-AC-01** | Cuando un cliente envía `GET /api/health` y tanto PostgreSQL como Redis están operativos, el sistema debe responder con código `200` y el cuerpo `{"status": "ok", "database": "ok", "redis": "ok"}`.                                                          | PLAT-BR-02               |
| **PLAT-AC-02** | Si Redis no está disponible o falla al responder cuando un cliente solicita `GET /api/health` o invoca las operaciones del helper de caché, entonces el sistema debe degradar de forma transparente sin propagar error y responder en `GET /api/health` con código `200` y `{"status": "ok", "database": "ok", "redis": "degraded"}`. | PLAT-BR-02               |
| **PLAT-AC-03** | Si PostgreSQL no está disponible cuando un cliente envía `GET /api/health`, entonces el sistema debe responder con código `503` y el cuerpo `{"detail": "Servicio de base de datos no disponible"}`.                                                          | PLAT-BR-02, PLAT-BR-04   |
| **PLAT-AC-04** | Cuando un cliente solicita `GET /api/openapi.json` o `GET /api/docs`, el sistema debe responder con código `200` exponiendo el contrato OpenAPI válido sin incluir cabeceras `Access-Control-Allow-Origin` abiertas ante orígenes cruzados.                    | PLAT-BR-01, PLAT-BR-03   |
| **PLAT-AC-05** | Si un cliente solicita una ruta inexistente bajo `/api` o se lanza una `HTTPException`, entonces el sistema debe responder con el código HTTP correspondiente y un objeto JSON cuyo campo `detail` sea un `string` en español.                                 | PLAT-BR-04               |
| **PLAT-AC-06** | Si un cliente envía parámetros o un cuerpo que incumplen la validación de esquemas Pydantic (`RequestValidationError`), entonces el sistema debe responder con código `422`, un campo `detail` de tipo `string` en español y una lista `errors` con objetos `{"field": "<campo>", "message": "<mensaje en español>"}` sin textos en inglés de Pydantic. | PLAT-BR-04               |
| **PLAT-AC-07** | Si ocurre una excepción interna no controlada durante el procesamiento de una petición en la API, entonces el sistema debe responder con código `500` y el cuerpo `{"detail": "Error interno del servidor"}` sin exponer trazas, sentencias SQL ni rutas internas. | PLAT-BR-04               |
| **PLAT-AC-08** | Cuando un endpoint paginado es invocado con parámetros `page` y `size` válidos (o sin ellos, aplicando por defecto `page=1` y `size=10`), el sistema debe devolver el sobre `{ "items": [...], "total": <int>, "page": <int>, "size": <int>, "pages": <int> }` con `pages = ceil(total / size)` y `pages = 0` cuando `total = 0`. | PLAT-BR-05               |
| **PLAT-AC-09** | Si un cliente solicita un listado paginado con `page < 1`, `size < 1` o `size > 50`, entonces el sistema debe rechazar la petición con código `422` y el formato de error de validación en español.                                                           | PLAT-BR-04, PLAT-BR-05   |
| **PLAT-AC-10** | El sistema debe normalizar toda fecha u hora a UTC y serializarla en las respuestas JSON en formato ISO 8601 UTC (`Z` o `+00:00`).                                                                                                                            | PLAT-BR-06               |
| **PLAT-AC-11** | El sistema debe aplicar las migraciones de Alembic sobre PostgreSQL habilitando la extensión `pg_trgm` y ejecutar toda la suite `pytest` exclusivamente contra PostgreSQL en contenedor con aislamiento determinista entre pruebas.                           | PLAT-BR-07               |
| **PLAT-AC-12** | Cuando el sistema se despliega con Docker Compose, el gateway Nginx debe servir la aplicación web en `/`, enrutar `/api/` hacia el contenedor de la API y servir archivos desde `/api/media/` en modo solo lectura.                                           | PLAT-BR-01               |
| **PLAT-AC-13** | Si el cliente Axios del frontend recibe una respuesta `401` desde cualquier endpoint distinto de `/api/auth/login`, entonces el sistema debe limpiar la sesión en `useAuthStore`, emitir un aviso en español y redirigir a `/login` conservando la ruta de origen en `query.redirect`; si el `401` proviene de `/api/auth/login`, no debe redirigir. | PLAT-BR-08               |
| **PLAT-AC-14** | Si el cliente Axios del frontend recibe una respuesta `403`, entonces el sistema debe mantener intacta la sesión activa en `useAuthStore`, no redirigir al login y mostrar un aviso en español (`"No tienes permisos para realizar esta acción"` o el `detail` recibido). | PLAT-BR-08               |
| **PLAT-AC-15** | Si el cliente Axios del frontend recibe una respuesta `404`, `409` o `422`, entonces el sistema debe extraer y mostrar el campo `detail` en español devuelto por la API; y si recibe un error `5xx` o un fallo de red sin respuesta, entonces el sistema debe mostrar un mensaje genérico en español sin información técnica. | PLAT-BR-08               |
| **PLAT-AC-16** | Cuando un usuario navega en el frontend hacia una ruta con `meta.requiresAuth` sin estar autenticado, el guard del router debe redirigirlo a `/login` con `query.redirect`; y cuando un usuario autenticado intenta acceder a una ruta con `meta.roles` sin poseer un rol permitido, el guard debe redirigirlo a `/`. | PLAT-BR-09               |
| **PLAT-AC-17** | El sistema debe proporcionar en el frontend los componentes reutilizables `BaseInput.vue`, `BaseButton.vue`, `BaseSpinner.vue`, `BaseSkeleton.vue` y `BaseAlert.vue` que muestren etiquetas, estados de carga (`isLoading`), errores de campo y alertas en español sin utilizar `v-html` con contenido de usuario. | PLAT-BR-09               |
| **PLAT-AC-18** | Cuando se ejecuta el build de producción del frontend, el sistema debe validar los tipos con `vue-tsc`, empaquetar las rutas mediante carga diferida (`lazy loading`) y producir artefactos minificados sin archivos source map (`.map`) públicos.             | PLAT-BR-09               |

## 6. Casos límite

- **Página solicitada mayor al total de páginas (`page > pages` con `total > 0` o `total = 0`):** La utilidad de paginación no devuelve `404`, sino `200 OK` con `items: []`, `total` real, `page` solicitada, `size` solicitado y `pages` calculado (`0` cuando `total = 0`).
- **Caída repentina de Redis a mitad de una operación de lectura o invalidación:** El cliente de caché captura cualquier `RedisError`/`ConnectionError`, registra un warning en logs en inglés (Principio 6) y devuelve `None` (en lectura) o `False` (en escritura/invalidación) para que el servicio continúe contra PostgreSQL sin afectar al usuario (R4.4).
- **Error `401` en el propio formulario de inicio de sesión (`POST /api/auth/login`):** El interceptor de Axios detecta que la petición original iba dirigida al endpoint de login y no limpia ni redirige de nuevo a `/login`, permitiendo que la vista muestre el mensaje de credenciales inválidas.
- ** Cuerpo JSON malformado en una petición a la API:** FastAPI genera un `RequestValidationError` (`json_invalid`); el manejador global de `422` lo intercepta y devuelve `{"detail": "El cuerpo de la petición no es un JSON válido", "errors": [...]}` en español, sin filtrar nombres internos del parser.
- **Fechas entrantes sin zona horaria (naive) o con otra zona horaria (ej. `-05:00`):** La utilidad de fechas convierte valores con offset a su equivalente en UTC y asume UTC para valores naive antes de persistir o serializar.

## 7. Fuera de alcance

- Modelos de negocio (`User`, `Event`, `Session`, `Registration`) y sus migraciones específicas (pertenecen a `auth`, `events`, `sessions` y `registrations`).
- Emisión/verificación criptográfica de JWT y hashing de contraseñas (pertenecen a `specs/auth/`).
- Procesamiento de imágenes con Pillow a variantes WebP (pertenece a `specs/events/`, aunque `platform` deja configurados el volumen `media` y la ubicación `/api/media/` en Nginx).
- Vistas definitivas de negocio (catálogo completo, detalle de evento con sesiones, formularios de login/registro/evento y perfil), que se implementan en sus respectivos dominios sobre el router y componentes base creados aquí.

## 8. Decisiones resueltas

| Fecha      | Pregunta                                                           | Decisión                                                                                                                                                                                                                      | Motivo                                                                                                                                             |
| ---------- | ------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026-10-31 | #1 Convención de paginación y sobre de respuesta                   | Opción A: `page` (defecto `1`, mín. `1`) y `size` (defecto `10`, mín. `1`, máx. `50`), sobre `{ "items": [], "total": 0, "page": 1, "size": 10, "pages": 0 }`.                                                                | Evita cálculos en el frontend (R2.5, R4.5) y estandariza las claves de caché en Redis.                                                             |
| 2026-10-31 | #2 Formato del cuerpo de error HTTP y normalización 422            | Opción A: `{"detail": "Mensaje en español"}` en todos los errores HTTP, y en `422` `detail` tipo `string` en español más `errors: [{"field": "...", "message": "..."}]` en español.                                          | Garantiza que `detail` sea siempre un `string` en español para notificaciones globales y aporta detalle por campo para formularios (Principio 6).  |
| 2026-10-31 | #3 Estrategia de BD PostgreSQL en contenedor para `pytest`         | Opción A: Base de datos `mis_eventos_test` en el mismo contenedor `db` de Docker Compose; aislamiento por transacción con `SAVEPOINT` y rollback en tests ordinarios, más fixture `TRUNCATE ... RESTART IDENTITY CASCADE` para concurrencia. | Cumple R3.6 y R3.7 sin duplicar contenedores PostgreSQL y soporta tanto tests rápidos como pruebas multi-conexión `FOR UPDATE`.                    |
| 2026-10-31 | #4 Contrato exacto de `GET /api/health`                            | Opción A: `200 OK` con `{"status": "ok", "database": "ok", "redis": "ok" \| "degraded"}` si PostgreSQL responde, y `503` con `{"detail": "Servicio de base de datos no disponible"}` si PostgreSQL falla.                     | Demuestra R4.4 (Redis prescindible) desde el Dominio 0 sin reiniciar el contenedor de la API si Redis cae.                                         |

## 9. Historial

| Versión | Fecha      | Cambio                                                                                                                          |
| ------- | ---------- | ------------------------------------------------------------------------------------------------------------------------------- |
| 0.1     | 2026-10-31 | Especificación completa del dominio `platform` en estado `Borrador` con las 4 decisiones resueltas por el usuario.              |
| 1.0     | 2026-10-31 | Aprobación explícita del usuario (`Borrador → Aprobada`) y paso inmediato a `En implementación` para iniciar el Paso 6 (TDD). |
| 1.0     | 2026-10-31 | Validación del `reviewer` (`¿pasa? sí`, 18/18 criterios `PLAT-AC-01..18` verificados en verde) y cierre en estado `Implementada`. |
