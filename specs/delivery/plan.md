# Plan técnico: Entrega y Release v1.0.0 (`delivery`)

| Campo                  | Valor                         |
| ---------------------- | ----------------------------- |
| **ID del dominio**     | `DLV`                         |
| **Spec de referencia** | `specs/delivery/spec.md` v1.1 |
| **Fecha**              | 2026-11-01                    |

> Este plan describe **cómo** se implementa la spec. No añade comportamiento: si algo no está en `spec.md`, primero se agrega allí (R1.1, R1.5). Identificadores en inglés (R6).

## 1. Modelo de datos y migraciones

**No hay modelos, tablas, índices ni migraciones nuevas.** Este dominio no toca `backend/app/**/{models,schemas,service,router,dependencies}.py` ni `backend/migrations/versions/`.

| Tabla / modelo | Campos relevantes | Restricciones (PK, FK, UNIQUE, CHECK) |
| -------------- | ----------------- | ------------------------------------- |
| _(ninguno)_    | —                 | —                                     |

- Migración Alembic: **ninguna**. La cabeza vigente se mantiene en `0005_create_registrations` y se verifica, no se modifica.
- Índices (incluidos los de `pg_trgm` si aplica): **ninguno nuevo**; se comprueba que `ix_events_title_trgm` y los índices únicos parciales de `registrations` siguen presentes tras el arranque limpio.
- Único cambio admitido en backend de producto: el parámetro `version="1.0.0"` de `FastAPI(...)` en `backend/app/main.py` y la metainformación de versión en `backend/pyproject.toml` + `backend/uv.lock`.
- Cambio documental sin impacto en el modelo: la armonización de versiones de las seis specs a `1.0` (`DLV-BR-13`, `DLV-AC-32`) toca solo la cabecera, la fila de historial y la columna «Versión» de `specs/README.md` §5; no cambia contenido normativo, estados ni cifras.

## 2. Backend

El backend se trata como **checklist de verificación de contrato**, no como desarrollo.

- **Routers y endpoints:** ninguno nuevo ni modificado. Se verifica el conjunto ya existente (`health`, `auth`, `users`, `events`, `sessions`, `registrations`) contra el baseline de `registrations` v1.0.
- **Dependencias de FastAPI** (autenticación y autorización, R5.2): sin cambios; el E2E ejercita `401`/`403`/`404`/`409` con los tres roles sobre las dependencias ya existentes.
- **Schemas de entrada y salida** (R5.5): sin cambios; se comprueba que `password_hash`, `full_name` y `email` de terceros siguen ausentes en las respuestas de `registrations`.
- **Servicios / lógica de negocio:** sin cambios; cualquier corrección detectada se delega al dominio de origen (R1.3, `DLV-BR-01`).
- **Transacciones y bloqueos** (R5.4, si aplica): sin cambios en el código; el E2E confirma el comportamiento observable del último cupo (`409`) y de la cascada al cancelar.
- **Caché Redis** (R4.4, si aplica): sin cambios; se verifica la degradación con `docker compose stop redis` y la limpieza final de claves.

### 2.1 Archivos de backend que sí cambian (solo metainformación)

| Archivo                  | Cambio                                                                    | Verificación                              |
| ------------------------ | ------------------------------------------------------------------------- | ----------------------------------------- |
| `backend/pyproject.toml` | `version = "0.1.0"` → `"1.0.0"`.                                          | `grep '^version' backend/pyproject.toml`. |
| `backend/uv.lock`        | Regenerado con `uv lock`; `version = "1.0.0"` para `mis-eventos-backend`. | `uv lock --check` sin cambios pendientes. |
| `backend/app/main.py`    | `FastAPI(..., version="1.0.0")`.                                          | `info.version` en `/api/openapi.json`.    |

Prohibido en backend: dependencias nuevas en `pyproject.toml`, cambios en `app/core/**`, migraciones, routers, schemas o tests de producto.

### 2.2 Checklist de contrato (a través del gateway)

| Comprobación                                                        | Criterio    |
| ------------------------------------------------------------------- | ----------- |
| `/api/health` → `200` con `database: ok` y `redis: ok`.             | `DLV-AC-15` |
| `/api/docs` → `200` con Swagger UI.                                 | `DLV-AC-17` |
| `/api/openapi.json` → `info.version = 1.0.0`.                       | `DLV-AC-03` |
| Mismos paths, operaciones, tags, schemas y códigos que el baseline. | `DLV-AC-18` |
| `503` con `detail` en español si cae PostgreSQL (smoke).            | `DLV-AC-17` |
| `409` de cupo agotado con `detail` en español.                      | `DLV-AC-22` |

## 3. Frontend

El frontend se trata como **checklist de build, tipos y cobertura**; no se crean ni modifican vistas, componentes, stores, servicios, rutas o guards.

- **Rutas (lazy loading) y guards:** sin cambios; se verifica en el build que cada vista sigue en su chunk diferido y que `EventForm.vue`, `SessionForm.vue` y `EventRegistrationsList.vue` se cargan con `defineAsyncComponent`.
- **Stores de Pinia:** sin cambios (`useAuthStore`, `useEventStore`, `useSessionStore`, `useRegistrationStore`); el E2E los ejercita desde la UI.
- **Componentes:** sin cambios. Se confirma por búsqueda de texto que no existe `v-html` con contenido de usuario (R5.9).
- **Manejo de errores y estados de carga:** sin cambios; el E2E observa los avisos en español de `409` y la consola sin errores.
- **Metainformación:** `frontend/package.json` y `frontend/package-lock.json` (raíz y `packages[""]`) pasan a `1.0.0` mediante `npm version 1.0.0 --no-git-tag-version`.
- **Build:** `vite.config.ts` ya define `minify: 'esbuild'` y `sourcemap: false`; se verifica el resultado, no se cambia la configuración.

Impacto esperado en componentes, rutas y stores de Vue: **ninguno** (cero archivos nuevos o modificados en `frontend/src/`).

## 4. Librerías de soporte (R4.2)

| Librería          | Componente del stack al que sirve | Motivo                                                                                                          |
| ----------------- | --------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| _(ninguna nueva)_ | —                                 | El dominio no introduce dependencias; regenerar `uv.lock` y `package-lock.json` no añade ni actualiza paquetes. |

Cualquier necesidad de una librería nueva (por ejemplo, un generador de secretos) se cubre con la biblioteca estándar (`secrets` de Python, `openssl rand`) sin modificar `pyproject.toml` ni `package.json`.

## 5. Estrategia de verificación

`delivery` no produce código de producto, por lo que la estrategia es **verificación con evidencia**, no TDD de comportamiento nuevo.

### 5.1 Correspondencia con R1.5 (decisión `DLV-D2`, opción A)

- Cada `DLV-AC-NN` tiene al menos una tarea `Vn` en `tasks.md` con un **comando reproducible** y una **evidencia esperada** verificable (salida, código HTTP, cifra de cobertura, línea de `git check-ignore`, documento OpenAPI).
- Cuando el comportamiento pertenece a otro dominio, se **reutiliza el test existente** en lugar de escribir uno nuevo: `test_plat_ac_02_health_and_cache_degrade_gracefully_when_redis_down` (`DLV-AC-19`), `test_plat_ac_12_docker_compose_and_nginx_gateway_routing` (`DLV-AC-15`, `DLV-AC-17`), `test_plat_ac_04_openapi_and_docs_exposed_without_open_cors` (`DLV-AC-17`, `DLV-AC-27`), `test_auth_ac_20_bootstrap_creates_single_admin_idempotently` (`DLV-AC-08`), `test_auth_ac_22_bootstrap_partial_env_fails_with_generic_spanish_error` (`DLV-AC-09`), `test_auth_ac_23_jwt_secret_validation_rejects_short_or_placeholder_in_production` (`DLV-AC-06`), `test_auth_ac_29_no_password_hash_or_secret_in_responses_or_logs` (`DLV-AC-25`), `test_reg_ac_25_event_registrations_list_exposes_no_personal_data` (`DLV-AC-25`) y `it('PLAT-AC-17 … without v-html')` (`DLV-AC-26`).
- Los criterios restantes se cubren con comandos de infraestructura y de auditoría (`docker compose`, `curl`, `git check-ignore`, `grep`, `uv lock --check`, `npm ci --dry-run`), cuya evidencia se transcribe fechada en `MEMORY.md` y en el cierre documental.
- Esta correspondencia es **la decisión adoptada** (`DLV-D2`, opción A, 2026-11-01): R1.5 se satisface con checklist, comando reproducible y evidencia registrada, más los tests reutilizados; no se escriben tests de aserción sobre documentación ni se tocan las suites de producto.

### 5.2 Comandos por bloque (evidencia esperada)

| Bloque                | Comando                                                                                                                                                               | Evidencia esperada                                                                                                                                                                                                                             |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Versiones             | `uv lock --check` (en `backend/`); `npm ci --dry-run` (en `frontend/`)                                                                                                | Sin cambios pendientes; lockfile consistente con el manifiesto.                                                                                                                                                                                |
| Contrato              | `curl -s http://localhost:8080/api/openapi.json`                                                                                                                      | `info.version == "1.0.0"` y diff vacío frente al baseline salvo esa clave.                                                                                                                                                                     |
| Tipo/tests backend    | `uv run pytest --cov=app --cov-report=xml --cov-report=term-missing`                                                                                                  | Suite en verde, `backend/coverage.xml` regenerado, cifra y fecha publicadas.                                                                                                                                                                   |
| Tests frontend        | `npm run test -- --run`; `npx vitest run --coverage`                                                                                                                  | Suite en verde y reporte de cobertura con cifras.                                                                                                                                                                                              |
| Tipos frontend        | `npx vue-tsc --noEmit`                                                                                                                                                | Sin salida de errores.                                                                                                                                                                                                                         |
| Build frontend        | `npm run build`                                                                                                                                                       | `dist/` minificado, chunks diferidos y cero archivos `.map`.                                                                                                                                                                                   |
| Stack desde cero      | `docker compose down -v && docker compose up -d --build`                                                                                                              | Cinco servicios operativos; `api` healthy; `db`/`redis` healthy.                                                                                                                                                                               |
| Migraciones           | `docker compose exec api uv run alembic current`                                                                                                                      | `0005_create_registrations (head)`.                                                                                                                                                                                                            |
| Gateway               | `curl -i http://localhost:8080/`, `/api/health`, `/api/docs`, `/api/openapi.json`, `/api/media/events/<archivo>`                                                      | `200`, `Content-Type` correcto y sin `Access-Control-Allow-Origin`.                                                                                                                                                                            |
| Redis prescindible    | `docker compose stop redis` + `curl -s http://localhost:8080/api/health`                                                                                              | `200` con `"redis": "degraded"`; lecturas siguen funcionando.                                                                                                                                                                                  |
| E2E transversal       | Navegador real sobre `http://localhost:8080` (o `curl` equivalente) con `ADMIN`, `ORGANIZER` y `ATTENDEE`                                                             | Secuencia completa de `DLV-AC-20`–`DLV-AC-23` con limpieza final en cero.                                                                                                                                                                      |
| Entorno (`.env`)      | Leer `.env` y `.env.example`, respaldar `.env` fuera del repositorio, calcular las claves ausentes y **añadirlas al final** sin reescribir líneas previas (§5.5)      | `CONTEXT7_API_KEY`, `GITHUB_PERSONAL_ACCESS_TOKEN`, `DEV_DATABASE_URI` y `BROWSER_PATH` presentes con su valor original; claves de aplicación añadidas una sola vez; sin duplicados.                                                           |
| Secretos              | `git check-ignore -v .env`; `git status --short`; `git ls-files`; comparación de nombres y huellas de las claves de OpenCode/MCP antes/después (sin publicar valores) | `.env` ignorado y ausente del índice; `.env.example` con placeholders; variables de OpenCode/MCP con nombre y huella intactos.                                                                                                                 |
| Privacidad            | `curl` autenticado sobre `registrations`; `docker compose logs api`                                                                                                   | Sin `password_hash`, trazas, SQL ni datos personales en respuestas o logs.                                                                                                                                                                     |
| Alcance               | `git diff --stat v0.5.0-registrations..HEAD`                                                                                                                          | Solo manifiestos, `backend/app/main.py`, documentación y `specs/`; sin endpoints, modelos ni migraciones.                                                                                                                                      |
| Armonización de specs | `grep -n "\\*\\*Versión\\*\\*" specs/*/spec.md` y lectura de la columna «Versión» de `specs/README.md` §5                                                             | Versiones exactas: `platform` `1.0`, `auth` `1.0`, `events` `1.0`, `sessions` `1.0`, `registrations` `1.0`, `delivery` `1.1`; §5 coincide fila a fila; una fila de historial fechada por spec; contenido normativo, estados y cifras intactos. |

### 5.3 Guion del E2E transversal

1. `ADMIN` sembrado desde `BOOTSTRAP_ADMIN_*`; login correcto y acceso a `/admin/users`.
2. `ORGANIZER` crea evento en `DRAFT` (`201`), sube imagen (`200`, tres variantes WebP con `image/webp` y `Cache-Control` inmutable) y publica (`PATCH 200`).
3. `ORGANIZER` añade una sesión (`201`) dentro de la ventana UTC del evento.
4. `ATTENDEE` se inscribe al evento (`201`) y a la sesión (`201`); los cupos se leen de la API.
5. Segundo `ATTENDEE` ocupa el último cupo; el tercero recibe `409` con `detail` en español y no se crea fila.
6. El `ATTENDEE` cancela su inscripción al evento (`204`); la inscripción a la sesión queda `CANCELLED` y los cupos se liberan.
7. Limpieza: usuarios, eventos, sesiones, inscripciones, variantes WebP del volumen `media` y claves Redis; verificar contadores en cero y `redis-cli DBSIZE` = 0.
8. Evidencia sin credenciales ni datos personales: IDs, códigos HTTP, mensajes en español y cifras.

### 5.4 Fixtures y datos de prueba

- Se usan datos efímeros del E2E con email sintético (`admin.e2e@example.test`, `org.e2e@example.test`, `att.e2e@example.test`); las credenciales reales de bootstrap y la clave JWT se **añaden al `.env` existente** sin tocar ninguna variable previa (§5.5), con respaldo fuera del repositorio.
- La base de pruebas `mis_eventos_test` sigue siendo la única usada por `pytest` (R3.6); el E2E usa `mis_eventos` y se limpia al final.
- No se versiona ninguna evidencia con tokens, contraseñas ni datos personales; las comparaciones de variables usan nombres y huellas, nunca valores.

### 5.5 Procedimiento seguro de `.env` (append idempotente)

Prohibido `cp .env.example .env` sobre un `.env` existente y prohibido cualquier comando que reescriba el archivo completo. Secuencia obligatoria:

1. **Leer** el `.env` actual y `.env.example` (sin imprimir valores en la evidencia).
2. **Inventariar** los nombres de clave presentes en `.env` y **respaldar** el archivo fuera del repositorio (copia en el directorio temporal aprobado), con permiso restringido.
3. **Calcular** el conjunto de claves de aplicación de `.env.example` que faltan en `.env` (`GATEWAY_PORT`, `POSTGRES_*`, `DATABASE_URL`, `TEST_DATABASE_URL`, `REDIS_URL`, `MEDIA_ROOT`, `APP_ENV`, `JWT_SECRET_KEY`, `JWT_EXPIRE_MINUTES`, `BOOTSTRAP_ADMIN_*`).
4. **Añadir solo esas claves al final** del archivo, en modo append, sin reescribir ni reordenar las líneas previas; generar `JWT_SECRET_KEY` con CSPRNG (≥32 caracteres), `POSTGRES_PASSWORD` distinto de `postgres` y `DATABASE_URL`/`TEST_DATABASE_URL` coherentes con esa contraseña.
5. **Verificar** que las claves de OpenCode/MCP (`CONTEXT7_API_KEY`, `GITHUB_PERSONAL_ACCESS_TOKEN`, `DEV_DATABASE_URI`, `BROWSER_PATH`) conservan nombre y huella, que no hay claves duplicadas y que una segunda ejecución no cambia nada (idempotencia).
6. **Comprobar** `git check-ignore -v .env` y `git status --short`: `.env` sigue ignorado y fuera del índice.

Si cualquier verificación del paso 5 falla, se restaura el respaldo y se detiene la entrega: la pérdida de credenciales de OpenCode/MCP es un fallo bloqueante, no una incidencia menor.

## 6. Riesgos y mitigaciones

- **Pérdida de las credenciales de OpenCode/MCP por sobrescribir `.env`:** copiar `.env.example` sobre `.env` o reescribir el archivo completo elimina `CONTEXT7_API_KEY`, `GITHUB_PERSONAL_ACCESS_TOKEN`, `DEV_DATABASE_URI` y `BROWSER_PATH`, y rompe la configuración local de agentes. Mitigación: append idempotente con inventario previo, respaldo fuera del repositorio, verificación de nombres y huellas y prohibición expresa de `cp .env.example .env` sobre un `.env` existente (`DLV-BR-03`, §5.5).
- **`.env` olvidado con el placeholder de JWT en `production`:** la API no arranca (o arranca con una clave insegura en `development`). Mitigación: completar el `.env` con CSPRNG sin tocar las claves previas, comprobar `APP_ENV=production` + placeholder (debe fallar) y `grep -c "change-me" .env` = 0 antes de cualquier validación.
- **`docker compose down -v` destruye datos locales:** el volumen `pg_data` se borra. Mitigación: ejecutarlo solo en el entorno de verificación, avisarlo en la tarea `V19` y no reutilizar datos que se quieran conservar; la limpieza del E2E se hace por API y con `redis-cli FLUSHDB`, no con `down -v` a mitad del recorrido.
- **Deriva entre `uv.lock`/`package-lock.json` y los manifiestos:** bump manual del manifiesto sin regenerar el lockfile. Mitigación: `uv lock` + `uv lock --check` y `npm version --no-git-tag-version` + `npm ci --dry-run`; el lockfile nunca se edita a mano.
- **Cifras históricas no reejecutadas:** publicar coberturas de `sessions`/`registrations` sin correr la suite en esta entrega. Mitigación: `DLV-AC-11`/`DLV-AC-12` exigen corrida real y fecha; si no se puede ejecutar, la cifra se etiqueta como "última validación registrada" y no como medición del release.
- **Etiqueta `v1.0.0` prematura o mal apuntada:** crear la etiqueta antes del commit de cierre. Mitigación: `V7` depende de contrato, documentación y seguridad cerrados; si hay cambios posteriores, se borra y se recrea (`git tag -d v1.0.0`).
- **Contrato tocado "de paso" al añadir `version` a `FastAPI`:** el parámetro solo cambia `info.info.version`; cualquier otro diff es un fallo. Mitigación: baseline capturado en `V1` y comparado en `V6`/`V18`.
- **CORS abierto para "facilitar" la demo:** viola R2.2 y el diseño del gateway. Mitigación: `DLV-AC-27` con `curl -H "Origin: http://evil.test"` y revisión de `app/main.py`; nunca se añade `CORSMiddleware`.
- **Source maps o dependencias de desarrollo en el build de producción:** exposición de código y peso innecesario. Mitigación: `vite.config.ts` ya fija `sourcemap: false`; verificar `find frontend/dist -name "*.map"` = 0.
- **Limpieza incompleta del E2E:** filas o archivos huérfanos que ensucian el entorno y la evidencia. Mitigación: orden base de datos → media → claves Redis y verificación de contadores en cero (`DLV-AC-23`).
- **Hallazgo funcional durante la verificación:** tentación de parchearlo en `delivery`. Mitigación: se registra como defecto, se corrige en su dominio de origen con test y entrada en `MEMORY.md` (R1.3, `DLV-BR-01`).
- **Puertos `5432`/`6379` publicados y falta de `restart:`:** quedan expuestos y sin política de reinicio en el entorno de desarrollo. Mitigación: es una **limitación declarada** en la sección `[1.0.0]` de `CHANGELOG.md` (`DLV-D4`: fuera de alcance); no se modifica `docker-compose.yml` ni se reabre `platform`.
