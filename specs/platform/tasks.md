# Tareas TDD: Plataforma Base (`platform`)

| Campo                  | Valor                        |
| ---------------------- | ---------------------------- |
| **ID del dominio**     | `PLAT`                       |
| **Spec de referencia** | `specs/platform/spec.md` v1.0 |
| **Plan de referencia** | `specs/platform/plan.md`     |

> Ninguna tarea empieza hasta que la spec esté _Aprobada_ (R1.8). Cada tarea sigue el ciclo test → rojo → implementación mínima → verde → refactor (R3.1). El rojo debe fallar por la aserción esperada (R3.2).

**Estados:** `[ ]` pendiente · `[R]` test en rojo · `[V]` verde · `[x]` refactorizada y cerrada

## Backend e Infraestructura

| #   | Estado | Criterio   | Test (en rojo primero)                                                         | Implementación                                                                                                                                                                                                                 |
| --- | ------ | ---------- | ------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| B1  | [x]    | PLAT-AC-11 | `test_plat_ac_11_postgres_test_db_and_pg_trgm_enabled`                         | Inicializar `backend/pyproject.toml` + `uv.lock`, `app/core/config.py`, `app/core/database.py`, `alembic.ini`, migración `0001_enable_pg_trgm.py` y `tests/conftest.py` contra `mis_eventos_test` en PostgreSQL (SAVEPOINT + TRUNCATE). |
| B2  | [x]    | PLAT-AC-01 | `test_plat_ac_01_health_returns_ok_when_db_and_redis_up`                       | Implementar `CacheClient` en `app/core/cache.py` y el endpoint `GET /api/health` en `app/core/health.py` devolviendo `200` con `{"status": "ok", "database": "ok", "redis": "ok"}`.                                            |
| B3  | [x]    | PLAT-AC-02 | `test_plat_ac_02_health_and_cache_degrade_gracefully_when_redis_down`          | Hacer que `CacheClient` capture `RedisError` retornando `None`/`False` sin propagar error y que `GET /api/health` devuelva `200` con `"redis": "degraded"` cuando Redis no responde (R4.4).                                    |
| B4  | [x]    | PLAT-AC-03 | `test_plat_ac_03_health_returns_503_in_spanish_when_db_down`                   | Manejar el fallo de conexión a PostgreSQL en `GET /api/health` devolviendo `503` con `{"detail": "Servicio de base de datos no disponible"}`.                                                                                  |
| B5  | [x]    | PLAT-AC-04 | `test_plat_ac_04_openapi_and_docs_exposed_without_open_cors`                   | Configurar `app/main.py` con `/api/openapi.json` y `/api/docs`, paquetes esqueleto por dominio (`auth`, `users`, `events`, `sessions`, `registrations`) y verificar ausencia de `CORSMiddleware` abierto (R2.2, R2.4).         |
| B6  | [x]    | PLAT-AC-05 | `test_plat_ac_05_http_errors_return_spanish_detail_string`                     | Implementar manejador de `StarletteHTTPException` en `app/core/exceptions.py` garantizando que `detail` sea siempre un `string` en español (ej. `404` → `"Recurso no encontrado"`).                                            |
| B7  | [x]    | PLAT-AC-06 | `test_plat_ac_06_validation_error_422_normalized_to_spanish`                   | Implementar manejador de `RequestValidationError` (`422`) en `app/core/exceptions.py` devolviendo `detail` string en español y lista `errors: [{"field", "message"}]` traducida al español (Principio 6).                      |
| B8  | [x]    | PLAT-AC-07 | `test_plat_ac_07_unhandled_exception_returns_generic_500_in_spanish`           | Implementar manejador global de `Exception` (`500`) en `app/core/exceptions.py` devolviendo `{"detail": "Error interno del servidor"}` sin exponer trazas ni consultas SQL (R5.8).                                             |
| B9  | [x]    | PLAT-AC-08 | `test_plat_ac_08_pagination_envelope_and_defaults`                             | Implementar `PaginationParams`, `PaginatedResponse[T]` y `build_paginated_response` en `app/core/pagination.py` (`page=1`, `size=10`, cálculo de `pages` y `pages=0` cuando `total=0`).                                        |
| B10 | [x]    | PLAT-AC-09 | `test_plat_ac_09_pagination_rejects_out_of_range_params_with_spanish_422`      | Validar restricciones `page >= 1` y `1 <= size <= 50` en `PaginationParams` devolviendo `422` en español cuando están fuera de rango.                                                                                          |
| B11 | [x]    | PLAT-AC-10 | `test_plat_ac_10_datetime_normalized_and_serialized_in_utc`                    | Implementar `utc_now`, `ensure_utc` y `UTCDateTime` en `app/core/datetime_utils.py` asegurando normalización a UTC y serialización ISO 8601 (`Z`).                                                                             |
| B12 | [x]    | PLAT-AC-12 | `test_plat_ac_12_docker_compose_and_nginx_gateway_routing`                     | Crear `backend/Dockerfile`, `frontend/Dockerfile`, `infra/nginx/default.conf`, `infra/postgres/init-test-db.sql`, `docker-compose.yml`, ampliar `.env.example` (conservando las 4 variables MCP) y redactar `backend/README.md`. |

## Frontend

| #   | Estado | Criterio   | Test (en rojo primero)                                                                                       | Implementación                                                                                                                                                                             |
| --- | ------ | ---------- | ------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| F1  | [x]    | PLAT-AC-13 | `it('PLAT-AC-13 clears auth session and redirects to login on 401 except on login endpoint')`                | Inicializar proyecto Vue 3 + Vite + TS + Pinia + Axios (`src/services/api.ts`, `src/stores/auth.ts`, `src/stores/notification.ts`) e implementar manejo de `401` en el interceptor global. |
| F2  | [x]    | PLAT-AC-14 | `it('PLAT-AC-14 preserves active session and shows Spanish warning on 403')`                                 | Implementar manejo de `403` en el interceptor de Axios conservando `useAuthStore` intacto y publicando aviso en español (R5.6).                                                            |
| F3  | [x]    | PLAT-AC-15 | `it('PLAT-AC-15 notifies API Spanish detail on 404/409/422 and generic Spanish message on 5xx or network error')` | Implementar en el interceptor de Axios la extracción de `detail` en español para `404`/`409`/`422` y el mensaje genérico en español para `5xx` o errores de red.                      |
| F4  | [x]    | PLAT-AC-16 | `it('PLAT-AC-16 enforces UX navigation guards for requiresAuth and role restrictions with lazy-loaded routes')` | Configurar `src/router/index.ts` con rutas diferidas (`() => import(...)`) y guard `beforeEach` para `meta.requiresAuth` y `meta.roles`.                                               |
| F5  | [x]    | PLAT-AC-17 | `it('PLAT-AC-17 renders BaseInput, BaseButton, BaseSpinner, BaseSkeleton and BaseAlert in Spanish without v-html')` | Crear `BaseInput.vue`, `BaseButton.vue`, `BaseSpinner.vue`, `BaseSkeleton.vue` y `BaseAlert.vue` con Tailwind CSS, estados de carga y textos en español sin usar `v-html` (R5.9, R6.2). |
| F6  | [x]    | PLAT-AC-18 | `it('PLAT-AC-18 configures lazy route chunks and builds minified bundle without public sourcemaps')`         | Configurar `vite.config.ts` (`minify: 'esbuild'`, `sourcemap: false`, proxy `/api`), `tsconfig.json` (`vue-tsc`) y redactar `frontend/README.md`.                                          |

## Definition of Done del dominio

- [x] Todos los criterios `PLAT-AC-01` a `PLAT-AC-18` tienen al menos un test con su ID en el nombre (R1.5, R1.9).
- [x] Suite de backend (`pytest`) y frontend (`Vitest`) en verde con reportes de cobertura generados; sin `skip`/`xfail` sin justificar (R3.8, R3.9).
- [x] Suite `pytest` ejecutándose exclusivamente contra PostgreSQL en contenedor (`mis_eventos_test`) con `pg_trgm` habilitada (R3.6, R3.7).
- [x] Contrato OpenAPI (`/api/openapi.json` y `/api/docs`) verificado y cliente Axios del frontend alineado (R2.4).
- [x] Mensajes de UI y `detail` de errores (incluidos `422` y `500`) en español; identificadores y nombres de tests en inglés (Principio 6).
- [x] Sin secretos en el repositorio y `.env.example` conservando intactas las 4 variables MCP (R5.7).
- [x] Estado actualizado en `specs/README.md` y entrada registrada en `MEMORY.md`.
