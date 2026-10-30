# MEMORY.md

Registro vivo del proyecto: decisiones, estado y tropiezos. Las reglas estables del stack viven en `AGENTS.md`; aquí solo va lo que cambia con el tiempo.

**Regla de uso:** una entrada por sesión de trabajo. No duplicar lo que ya está en `AGENTS.md`. Podar lo obsoleto en lugar de acumular.

**Última actualización:** 2026-10-29

## 1. Estado del proyecto

- `backend/`, `frontend/` e `infra/` solo contienen `.gitkeep`. `specs/` contiene el índice `specs/README.md` (v1.1) y las plantillas `specs/_template/`; ninguna spec de dominio redactada.
- Sin código, manifests (`pyproject.toml`, `package.json`), `docker-compose.yml` ni CI.
- Documentación existente: `docs/prueba_tecnica_desarrollador_fullstack.md` (requisitos), `docs/Analisis-Arquitectonico-Funcional-Plataforma-Mis-Eventos.md` (arquitectura v1.0) y `docs/constitution.md` (principios innegociables, v1.1).
- Plazo de la prueba: 5 días desde la recepción.

## 2. Decisiones tomadas

| Fecha      | Decisión                                                                       | Motivo                                                                        |
| ---------- | ------------------------------------------------------------------------------ | ----------------------------------------------------------------------------- |
| 2026-10-28 | Frontend Vue 3 + Pinia + Tailwind (no React)                                   | Composition API y velocidad de desarrollo en un plazo de 5 días               |
| 2026-10-28 | Backend FastAPI + SQLModel/SQLAlchemy + PostgreSQL + Alembic sobre Python 3.14 | Cumple el requerimiento técnico al milímetro                                  |
| 2026-10-28 | Nginx como punto de entrada único (`/` → web, `/api` → backend)                | Elimina CORS de raíz y permite balancear réplicas                             |
| 2026-10-28 | Redis solo para cachear listados paginados y consultas de solo lectura         | Bonus con bajo riesgo de consistencia                                         |
| 2026-10-28 | JWT + RBAC con roles Admin / Organizador / Asistente                           | Cubre el bonus de roles y permisos                                            |
| 2026-10-28 | Migraciones Alembic al inicializar el contenedor de la API                     | Evita pasos manuales de despliegue                                            |
| 2026-10-29 | Metodología SDD: las specs en `specs/` preceden a la implementación            | Enfoque acordado para el proyecto                                             |
| 2026-10-29 | Constitución v1.0 ratificada en `docs/constitution.md`                         | Fija los 6 principios innegociables y la jerarquía normativa                  |
| 2026-10-29 | Los bonus de la prueba se tratan como requisitos obligatorios                  | Decisión del usuario: todo el alcance se entrega junto                        |
| 2026-10-29 | 401 ≠ 403: solo el 401 limpia la sesión                                        | La arquitectura v1.0 §3 era incorrecta; la constitución la corrige (R5.6)     |
| 2026-10-29 | Librerías de soporte permitidas si implementan un componente ya decidido       | Vite, driver Postgres, cliente Redis, JWT/hashing y utilidades de test (R4.2) |
| 2026-10-29 | Constitución v1.1: criterios de aceptación en notación EARS                    | Criterios verificables y mapeables 1:1 a tests (R1.2)                         |
| 2026-10-29 | Tres artefactos por dominio: `spec.md`, `plan.md`, `tasks.md` + plantillas     | Separar qué / cómo / tareas TDD (R1.7)                                        |
| 2026-10-29 | Ciclo de vida de specs; solo el usuario aprueba                                | "Spec aprobada" verificable antes de implementar (R1.8)                       |
| 2026-10-29 | Trazabilidad por IDs `<DOM>-BR-NN` / `<DOM>-AC-NN` en specs y nombres de test  | R1.5 comprobable con búsqueda de texto (R1.9)                                 |
| 2026-10-29 | Dominio `platform` como orden 0 y `delivery` como cierre                       | Base transversal previa a auth; entregables sin dueño (minificación, READMEs) |
| 2026-10-29 | Plan de specs renombrado a `specs/README.md` (v1.1)                            | Índice natural de la carpeta para personas y agentes                          |

## 3. Decisiones pendientes

| Tema                                    | Opciones                                                              | Impacto                                                                                                             | Bloquea a  |
| --------------------------------------- | --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- | ---------- |
| Gestor de dependencias                  | UV vs Poetry                                                          | Scripts de instalación, Dockerfile del backend                                                                      | `platform` |
| Base de datos en tests                  | SQLite en memoria vs Postgres en contenedor                           | La búsqueda trigrama (`pg_trgm`) solo funciona en Postgres; R3.6 obliga a probar bloqueo y búsqueda contra Postgres | `platform` |
| Tipado del frontend                     | TypeScript ligero vs JavaScript puro                                  | Configuración de Vite/Vitest y tipos de stores                                                                      | `platform` |
| Expiración / refresh de JWT             | Token único largo vs access + refresh                                 | `useAuthStore` e interceptor de Axios                                                                               | `auth`     |
| Imágenes de eventos (bonus obligatorio) | Campo en `Event` + almacenamiento (volumen/disco) y tamaños a generar | La arquitectura no define dónde viven los archivos ni cómo se sirven en WebP                                        | `events`   |

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
