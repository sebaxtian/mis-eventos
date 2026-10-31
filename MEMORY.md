# MEMORY.md

Registro vivo del proyecto: decisiones, estado y tropiezos. Las reglas estables del stack viven en `AGENTS.md`; aquí solo va lo que cambia con el tiempo.

**Regla de uso:** una entrada por sesión de trabajo. No duplicar lo que ya está en `AGENTS.md`. Podar lo obsoleto en lugar de acumular.

**Última actualización:** 2026-10-31

## 1. Estado del proyecto

- `backend/`, `frontend/` e `infra/` solo contienen `.gitkeep`. `specs/` contiene el índice `specs/README.md` (v1.2) y las plantillas `specs/_template/`; ninguna spec de dominio redactada.
- Sin código, manifests (`pyproject.toml`, `package.json`), `docker-compose.yml` ni CI.
- Documentación existente: `docs/prueba_tecnica_desarrollador_fullstack.md` (requisitos), `docs/Analisis-Arquitectonico-Funcional-Plataforma-Mis-Eventos.md` (arquitectura v1.1) y `docs/constitution.md` (principios innegociables, v1.1.1).
- Plazo de la prueba: 5 días desde la recepción.

## 2. Decisiones tomadas

| Fecha      | Decisión                                                                                                   | Motivo                                                                           |
| ---------- | ---------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| 2026-10-28 | Frontend Vue 3 + Pinia + Tailwind (no React)                                                               | Composition API y velocidad de desarrollo en un plazo de 5 días                  |
| 2026-10-28 | Backend FastAPI + SQLModel/SQLAlchemy + PostgreSQL + Alembic sobre Python 3.14                             | Cumple el requerimiento técnico al milímetro                                     |
| 2026-10-28 | Nginx como punto de entrada único (`/` → web, `/api` → backend)                                            | Elimina CORS de raíz y permite balancear réplicas                                |
| 2026-10-28 | Redis solo para cachear listados paginados y consultas de solo lectura                                     | Bonus con bajo riesgo de consistencia                                            |
| 2026-10-28 | JWT + RBAC con roles Admin / Organizador / Asistente                                                       | Cubre el bonus de roles y permisos                                               |
| 2026-10-28 | Migraciones Alembic al inicializar el contenedor de la API                                                 | Evita pasos manuales de despliegue                                               |
| 2026-10-29 | Metodología SDD: las specs en `specs/` preceden a la implementación                                        | Enfoque acordado para el proyecto                                                |
| 2026-10-29 | Constitución v1.0 ratificada en `docs/constitution.md`                                                     | Fija los 6 principios innegociables y la jerarquía normativa                     |
| 2026-10-29 | Los bonus de la prueba se tratan como requisitos obligatorios                                              | Decisión del usuario: todo el alcance se entrega junto                           |
| 2026-10-29 | 401 ≠ 403: solo el 401 limpia la sesión                                                                    | La arquitectura v1.0 §3 era incorrecta; la constitución la corrige (R5.6)        |
| 2026-10-29 | Librerías de soporte permitidas si implementan un componente ya decidido                                   | Vite, driver Postgres, cliente Redis, JWT/hashing y utilidades de test (R4.2)    |
| 2026-10-29 | Constitución v1.1: criterios de aceptación en notación EARS                                                | Criterios verificables y mapeables 1:1 a tests (R1.2)                            |
| 2026-10-29 | Tres artefactos por dominio: `spec.md`, `plan.md`, `tasks.md` + plantillas                                 | Separar qué / cómo / tareas TDD (R1.7)                                           |
| 2026-10-29 | Ciclo de vida de specs; solo el usuario aprueba                                                            | "Spec aprobada" verificable antes de implementar (R1.8)                          |
| 2026-10-29 | Trazabilidad por IDs `<DOM>-BR-NN` / `<DOM>-AC-NN` en specs y nombres de test                              | R1.5 comprobable con búsqueda de texto (R1.9)                                    |
| 2026-10-29 | Dominio `platform` como orden 0 y `delivery` como cierre                                                   | Base transversal previa a auth; entregables sin dueño (minificación, READMEs)    |
| 2026-10-29 | Plan de specs renombrado a `specs/README.md` (v1.1)                                                        | Índice natural de la carpeta para personas y agentes                             |
| 2026-10-30 | Gestor de dependencias del backend: UV (`pyproject.toml` + `uv.lock`)                                      | Velocidad de resolución e instalación en local y en Docker                       |
| 2026-10-30 | pytest siempre contra PostgreSQL en contenedor (nunca SQLite)                                              | R3.6: `pg_trgm`, `FOR UPDATE` y unicidad solo son fieles en PostgreSQL           |
| 2026-10-30 | Frontend con TypeScript ligero (`lang="ts"`, stores/servicios/props tipados)                               | Aprovechar Pinia y Composition API con seguridad de tipos sin sobrecoste         |
| 2026-10-30 | Imágenes: Pillow → 3 variantes WebP en backend, volumen `media`, Nginx sirve `/api/media/` en solo lectura | Bonus obligatorio; sin workers (R4.3) y respetando el prefijo `/api` (R2.1)      |
| 2026-10-30 | Librerías de soporte: Pillow y `python-multipart`                                                          | R4.2: implementan la subida y conversión de imágenes ya decidida                 |
| 2026-10-30 | Arquitectura v1.1 alineada con la constitución                                                             | Elimina ambigüedades de la v1.0 (UV, BD de tests, TS, 401/403, WebP, dominios)   |
| 2026-10-30 | Constitución v1.1.1 (PATCH), enmienda puntual autorizada por el usuario                                    | Referencias a la arquitectura v1.1 y R4.1 concreta UV y TypeScript ligero        |
| 2026-10-30 | `opencode.json` versionado (no ignorado) y secretos solo vía `{env:...}`                                   | No contiene secretos, reproduce el entorno y es revisable; `.env` sigue ignorado |
| 2026-10-30 | Versiones fijadas de los MCP `npx` (`chrome-devtools-mcp@1.12.0`, `@yawlabs/postgres-mcp@0.13.9`)          | Evita deriva de versiones y hace el entorno reproducible                         |
| 2026-10-30 | Agentes SDD de `.opencode/agents/` versionados; resto de `.opencode/` ignorado                             | Reproducir el flujo multiagente sin compartir configuración local                |
| 2026-10-30 | Permisos de agente en orden v2; implementer limita shell y rutas editables; reviewer shell con allowlist    | Reducir escalada de permisos y proteger specs, normas y configuración            |

## 3. Decisiones pendientes

| Tema                        | Opciones                              | Impacto                               | Bloquea a |
| --------------------------- | ------------------------------------- | ------------------------------------- | --------- |
| Expiración / refresh de JWT | Token único largo vs access + refresh | `useAuthStore` e interceptor de Axios | `auth`    |

Las preguntas abiertas no bloqueantes de cada dominio están en `specs/README.md` y se resuelven al redactar su `spec.md`.

## 4. Progreso por entregable

Estado de las specs (fuente de verdad: tabla de estado en `specs/README.md`):

| Orden | Dominio         | Estado                 |
| :---: | --------------- | ---------------------- |
|   0   | `platform`      | Pendiente de redacción |
|   1   | `auth`          | Pendiente de redacción |
|   2   | `events`        | Pendiente de redacción |
|   3   | `sessions`      | Pendiente de redacción |
|   4   | `registrations` | Pendiente de redacción |
|   5   | `delivery`      | Pendiente de redacción |

Entregables:

- [ ] Backend: modelo de datos (`User`, `Event`, `Session`, `Registration`) + migraciones
- [ ] Backend: autenticación y RBAC
- [ ] Backend: CRUD de eventos con búsqueda por nombre y estados
- [ ] Backend: sesiones con validación de solapamiento
- [ ] Backend: inscripciones con control atómico de capacidad
- [ ] Backend (bonus obligatorio): gestión de perfiles por el Admin
- [ ] Backend (bonus obligatorio): caché Redis de listados paginados con invalidación en escrituras
- [ ] Frontend: vistas (lista, detalle, crear/editar, login, registro, perfil)
- [ ] Frontend: stores Pinia + guards de router + interceptor Axios
- [ ] Frontend (bonus obligatorio): imágenes WebP con tamaños por dispositivo
- [ ] Frontend (bonus obligatorio): lazy loading de rutas y componentes + build minificado
- [ ] Infra: Dockerfile backend, Dockerfile frontend, `docker-compose.yml`, Nginx
- [ ] Tests backend (pytest + cobertura XML) y frontend (Vitest)
- [ ] README de `backend/` y de `frontend/` + documentación de estructura del frontend
- [ ] Swagger/OpenAPI verificado

## 5. Tropiezos y correcciones

Formato: `síntoma → causa → solución`. Vacío hasta que aparezca el primer problema real.

## 6. Bitácora de sesiones

- **2026-10-29** — Se crearon `AGENTS.md` y `MEMORY.md` a partir de los docs de requisitos y arquitectura. Siguiente: definir las specs iniciales en `specs/` y elegir gestor de dependencias.
- **2026-10-29** — Ratificada `docs/constitution.md` v1.0 con los 6 principios, la jerarquía normativa y los bonus como alcance obligatorio. Siguiente: escribir la primera spec en `specs/` (autenticación y modelo de datos) y resolver el gestor de dependencias.
- **2026-10-29** — Análisis del plan de specs: enmienda de la constitución a v1.1 (EARS, R1.7–R1.9), plan renombrado a `specs/README.md` v1.1 con dominios `platform` (0) y `delivery` (5), preguntas abiertas por dominio, decisiones bloqueantes y matriz de trazabilidad; plantillas en `specs/_template/`. Siguiente: resolver las tres decisiones que bloquean `platform` y redactar `specs/platform/spec.md`, `plan.md` y `tasks.md`.
- **2026-10-29** — Creado `README.md` raíz (alcance, stack, arquitectura, SDD, estado y enlaces internos). La sección "Puesta en marcha" queda pendiente hasta que exista `docker-compose.yml`. Sin commit todavía. Siguiente: redactar `specs/platform/`.
- **2026-10-30** — Arquitectura reescrita a v1.1: UV, pytest contra PostgreSQL, TypeScript ligero, 401 ≠ 403 en el interceptor, diseño de imágenes WebP (§3.8) y desarrollo por dominios. Enmienda PATCH de la constitución a v1.1.1 (referencias y R4.1), `specs/README.md` v1.2 sin bloqueantes en `platform` ni `events`, `AGENTS.md` y `README.md` alineados. Siguiente: redactar `specs/platform/spec.md`, `plan.md` y `tasks.md`.
- **2026-10-30** — Entorno OpenCode: `opencode.json` con 4 servidores MCP versionado (sin secretos, todo por `{env:...}`), versiones de los MCP `npx` fijadas (`chrome-devtools-mcp@1.12.0`, `@yawlabs/postgres-mcp@0.13.9`), `.env.example` con las 4 variables y sección "Entorno de desarrollo (OpenCode)" en `README.md` documentando `BROWSER_PATH`. Siguiente: redactar `specs/platform/`.
- **2026-10-31** — Auditoría multiagente y pruebas de humo: `opencode debug agents` carga coordinator (primary) y planner/implementer/reviewer (subagent); los cuatro MCP figuran conectados. Planner pudo escribir en `specs/` y se le denegó `backend/`. Implementer pudo escribir en `backend/`; se le denegaron sondas en `specs/` y `.opencode/agents/`, además de `git push --dry-run` y `Set-Content`; `git status` fue permitido. Reviewer tuvo denegada la escritura de sonda y pudo ejecutar `git status`; no se confirmó dinámicamente su denegación de `git push` ni la disponibilidad de MCP por agente. Las llamadas de edición con texto inexistente no se consideran prueba de denegación. Todas las sondas creadas se verificaron y eliminaron. `.opencode/agents/` y la documentación de la arquitectura multiagente quedan listas para el hito base; siguiente: iniciar `specs/platform/` tras la revisión/aprobación del usuario.
