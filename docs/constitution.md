# Constitución del Proyecto — Mis Eventos

**Versión:** 1.1.1
**Fecha:** 30 de octubre de 2026
**Metodología:** Spec-Driven Development (SDD)
**Ámbito:** Todo el repositorio (`backend/`, `frontend/`, `infra/`, `specs/`, `docs/`)

Este documento fija los principios **innegociables** del proyecto. Ninguna spec, tarea ni línea de código puede contradecirlo. Si un principio impide avanzar, se enmienda la constitución (ver Gobernanza) antes de escribir código.

## Jerarquía normativa

1. **Requisitos de la prueba técnica** (`docs/prueba_tecnica_desarrollador_fullstack.md`): alcance mínimo externo. Incluye los bonus, que en este proyecto son obligatorios. No se recorta.
2. **Esta constitución**: cómo se construye. Innegociable.
3. **Arquitectura v1.1** (`docs/Analisis-Arquitectonico-Funcional-Plataforma-Mis-Eventos.md`): marco técnico global.
4. **Especificaciones** (`specs/`): comportamiento de cada funcionalidad. El índice, el orden de dominios y su estado están en `specs/README.md`.
5. **Código y tests**: implementación. Nunca son fuente de verdad.

Ante un conflicto prevalece el documento de mayor rango y se corrige el inferior. La corrección del manejo del código 403 que esta constitución hizo sobre la arquitectura v1.0 (R5.6) ya está incorporada en la arquitectura v1.1.

---

## Principio 1 — La Especificación Manda

Las specs guían el código, no al revés.

- **R1.1** No se escribe código de una funcionalidad sin una spec en `specs/` que la describa.
- **R1.2** Contenido mínimo de una spec: objetivo, roles involucrados, reglas de negocio, contrato de API (método, ruta, request, response y códigos de error), criterios de aceptación verificables, casos límite y fuera de alcance. Los criterios de aceptación se redactan en **notación EARS**, en español:
  - Ubicuo: "El sistema debe <respuesta>."
  - Por evento: "Cuando <disparador>, el sistema debe <respuesta>."
  - Por estado: "Mientras <estado>, el sistema debe <respuesta>."
  - No deseado: "Si <condición no deseada>, entonces el sistema debe <respuesta>."
  - Opcional: "Donde <característica incluida>, el sistema debe <respuesta>."
- **R1.3** Si el código contradice la spec, el defecto está en el código.
- **R1.4** Si la spec estaba equivocada, se corrige primero la spec (con fecha y motivo), después los tests y por último el código. El cambio se registra en `MEMORY.md`.
- **R1.5** Cada criterio de aceptación se cubre con al menos un test. No se implementa comportamiento que no esté en una spec.
- **R1.6** La ambigüedad no se resuelve en el código: se aclara y se documenta en la spec antes de implementar.
- **R1.7** Cada dominio tiene tres artefactos en `specs/<dominio>/`, creados a partir de `specs/_template/`:
  - `spec.md`: **qué** (comportamiento observable, contrato y criterios EARS). Sin detalles de implementación.
  - `plan.md`: **cómo** (modelos, migraciones, índices, transacciones, caché, librerías de soporte, impacto en el frontend).
  - `tasks.md`: tareas TDD ordenadas; cada una nombra el criterio que cubre y el test que se escribe en rojo.
- **R1.8** Ciclo de vida de una spec: `Borrador → Aprobada → En implementación → Implementada`.
  - Solo el responsable del proyecto (usuario) aprueba una spec; un agente nunca la marca como _Aprobada_ por su cuenta.
  - Una spec con decisiones bloqueantes abiertas no puede pasar a _Aprobada_.
  - No se implementa nada de una spec que no esté _Aprobada_.
  - Un cambio después de aprobada sube su versión, se justifica en la spec y se registra en `MEMORY.md` (R1.4).
- **R1.9** Trazabilidad con IDs independientes del idioma: reglas de negocio `<DOM>-BR-NN` y criterios de aceptación `<DOM>-AC-NN` (por ejemplo, `AUTH-AC-01`). Cada test incluye el ID del criterio en su nombre (`test_auth_ac_01_rejects_expired_token`, `it('EVT-AC-03 ...')`), de modo que R1.5 se verifica con una búsqueda de texto.

**Anti-patrón:** implementar primero y ajustar la spec después para que coincida con el código.

---

## Principio 2 — Aislamiento de Dominio Puro

Vue.js y FastAPI son dominios independientes que solo se comunican por HTTP a través del gateway Nginx.

- **R2.1** Nginx es el único punto de entrada: `/` → contenedor web, `/api` → contenedor API. El frontend llama al backend con la ruta relativa `/api`, nunca con un host o puerto absoluto.
- **R2.2** Prohibido abrir CORS (`allow_origins=["*"]` u otros orígenes cruzados). En desarrollo local, el proxy del servidor de desarrollo puede replicar la regla `/api` del gateway; nunca se habilita CORS.
- **R2.3** El backend no sirve archivos del frontend ni conoce sus rutas. El frontend no conoce tablas, modelos ni consultas.
- **R2.4** El contrato entre ambos es el OpenAPI que genera FastAPI. Un cambio de contrato se escribe primero en la spec y después se refleja en los dos lados.
- **R2.5** Las reglas de negocio viven solo en el backend. Las validaciones del formulario y los guards del router son ayudas de UX, no controles.
- **R2.6** `backend/` y `frontend/` no comparten código ni dependencias. Cada uno tiene su propio manifiesto, Dockerfile y README.

**Anti-patrón:** calcular la capacidad disponible en Vue y confiar en ese valor.

---

## Principio 3 — TDD Obligatorio

Primero la prueba en rojo; después el código que la pone en verde.

- **R3.1** Ciclo obligatorio: test → rojo → implementación mínima → verde → refactor.
- **R3.2** El rojo debe fallar por la aserción esperada, no por un error de import, de sintaxis o de configuración.
- **R3.3** Backend con `pytest`; frontend con `vitest`.
- **R3.4** Pruebas obligatorias del dominio: capacidad (límite exacto, límite +1 e inscripciones concurrentes), solapamiento de sesiones (incluido el borde que defina la spec), transiciones de estado del evento, permisos por rol, propiedad del recurso y JWT ausente, inválido o expirado.
- **R3.5** Todo cambio de comportamiento llega con un test nuevo o modificado. Un refactor sin test nuevo solo es válido si los tests existentes ya lo cubren.
- **R3.6** Las reglas que dependen de PostgreSQL (bloqueo de filas, `pg_trgm`) se prueban contra PostgreSQL, no contra SQLite.
- **R3.7** Los tests son deterministas y aislados: sin depender del orden de ejecución ni dejar datos residuales.
- **R3.8** Prohibido `skip`/`xfail` sin justificación escrita, y prohibido borrar un test que falla para obtener verde.
- **R3.9** Se genera el reporte de cobertura de ambos lados. No se escriben tests triviales para inflarla.

**Anti-patrón:** un test escrito después del código que pasa a la primera.

---

## Principio 4 — Simplicidad del Stack

Solo se usa lo definido en la arquitectura v1.1.

- **R4.1** Componentes cerrados:
  - Backend: Python 3.14 (`python:3.14-slim`), FastAPI + Uvicorn, SQLModel/SQLAlchemy, PostgreSQL, Alembic, JWT, UV, pytest.
  - Frontend: Vue 3 (Composition API, `<script setup>`) con TypeScript ligero, Vue Router, Pinia, Axios, Tailwind CSS, Vitest.
  - Infra: Docker, Docker Compose, Nginx, PostgreSQL, Redis.
- **R4.2** Se permiten librerías de soporte que implementen un componente ya decidido (herramienta de build, driver de base de datos, cliente Redis, librería de JWT o de hashing, utilidades de test y cobertura), siempre que sean de uso extendido y se registren en `MEMORY.md` con su motivo.
- **R4.3** Prohibido sin enmienda previa: componentes nuevos de arquitectura (otra base de datos, colas o workers, WebSockets, GraphQL, otro gestor de estado, librerías de componentes UI, ORMs alternativos).
- **R4.4** Redis es solo una caché de lectura y es prescindible: si no está disponible, la API responde desde PostgreSQL. Las escrituras invalidan la caché afectada.
- **R4.5** Sin abstracciones especulativas. Ante dos soluciones igual de legibles, gana la más simple.

**Anti-patrón:** añadir Celery o una librería de componentes UI "porque será útil después".

---

## Principio 5 — Seguridad y Privacidad

La seguridad se implementa en el backend y se demuestra con tests.

- **R5.1** Contraseñas con un algoritmo adaptativo con sal (bcrypt o argon2, fijado en la spec de autenticación). Nunca en texto plano ni con hashes rápidos (MD5, SHA-\*). El hash nunca se devuelve ni se registra en logs.
- **R5.2** Validación atómica de JWT y RBAC: una sola cadena de dependencias, todo o nada, que se ejecuta antes de cualquier lógica de negocio. Comprueba en orden: token presente → firma → expiración → usuario existente → rol → propiedad del recurso. El primer fallo corta la petición.
- **R5.3** Matriz de roles verificada en el servidor en cada endpoint protegido:
  - Admin: gestión de perfiles y visibilidad total.
  - Organizador: CRUD solo de sus propios eventos y sesiones.
  - Asistente: lectura de eventos e inscripción.
- **R5.4** Inscripción atómica: la comprobación de capacidad (del evento y, si aplica, de la sesión) y la inserción ocurren en la misma transacción con bloqueo. Una restricción de unicidad impide inscripciones duplicadas. Prohibido comprobar y después insertar sin protección.
- **R5.5** Toda entrada se valida en el backend con schemas Pydantic. Las respuestas usan schemas de salida explícitos que nunca incluyen `password_hash`.
- **R5.6** Semántica estricta: 401 (token ausente, inválido o expirado) → el frontend limpia la sesión y redirige al login. 403 (sin permiso) → el frontend mantiene la sesión y muestra un aviso. _Corrigió la arquitectura v1.0 §3; incorporado en la arquitectura v1.1 §4.4._
- **R5.7** Secretos solo en variables de entorno. `.env` no se versiona; se versiona `.env.example` sin valores reales. Ningún secreto ni dato personal en el código, las specs, `AGENTS.md`, `MEMORY.md` o este archivo.
- **R5.8** Privacidad: se recogen solo los datos necesarios. Un usuario solo ve sus propias inscripciones; solo el Admin ve perfiles ajenos. El login responde con un mensaje genérico que no revela si el email existe. Los errores no exponen trazas, SQL ni nombres internos.
- **R5.9** Como el token es accesible desde JavaScript, está prohibido `v-html` con contenido proveniente de usuarios.

---

## Principio 6 — Idioma

Un idioma por tipo de artefacto, sin mezclas.

| Artefacto                                                                                                         | Idioma                                                                                    |
| ----------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| Identificadores, archivos, componentes, rutas de API, tablas, columnas, valores de enums, claves de configuración | Inglés                                                                                    |
| Comentarios, docstrings, nombres y descripciones de tests, logs                                                   | Inglés                                                                                    |
| Textos de la UI, mensajes de validación y error mostrados al usuario                                              | Español                                                                                   |
| Campo `detail` de los errores de API, incluidos los 422 de validación de FastAPI                                  | Español                                                                                   |
| Specs, constitución, arquitectura, README, `AGENTS.md`, `MEMORY.md`                                               | Español                                                                                   |
| Commits                                                                                                           | Prefijo de Conventional Commits (`feat:`, `fix:`, `docs:`…) con la descripción en español |

- **R6.1** Los valores de dominio se guardan en inglés (`DRAFT`, `PUBLISHED`, `CANCELLED`; `ADMIN`, `ORGANIZER`, `ATTENDEE`) y se traducen solo en la presentación.
- **R6.2** Componentes con nombre en inglés: `EventCard.vue`, `BaseInput.vue`, `BaseButton.vue`, `EventForm.vue`.

**Anti-patrón:** `EventoCard.vue` con una prop `titulo`, o un 422 que muestra `field required` al usuario.

---

## Alcance obligatorio

Todos los requisitos de la prueba técnica, **incluidos los bonus**, son obligatorios y se desarrollan junto con el resto:

- Backend: roles (Admin, Organizador, Asistente), permisos por rol y gestión de perfiles por el Admin.
- Frontend: imágenes optimizadas (WebP, compresión y tamaños según el dispositivo), lazy loading de rutas y componentes, código de producción minificado, caché de datos con Redis en el backend.
- La entrega no está completa mientras falte cualquiera de ellos.

## Flujo de trabajo y Definition of Done

Cada incremento recorre estas etapas en orden:

1. **Spec aprobada**: `spec.md` + `plan.md` + `tasks.md` del dominio, con la spec en estado _Aprobada_ (R1.7, R1.8).
2. **Rojo**: tests que fallan por la razón correcta.
3. **Verde**: implementación mínima que respeta los seis principios.
4. **Refactor**: la suite sigue en verde.
5. **Contrato**: OpenAPI y frontend alineados.
6. **Registro**: entrada en `MEMORY.md`.

**Definition of Done:** todos los criterios de aceptación tienen test · la suite está en verde · el contrato está verificado · no hay secretos · cada artefacto está en el idioma correcto · `MEMORY.md` está actualizado.

## Gobernanza

- **Enmiendas:** requieren justificación escrita, cambio de versión (MAJOR si se elimina o cambia un principio, MINOR si se añade una regla, PATCH si es solo redacción), entrada en `MEMORY.md` y un commit `docs:` separado del código.
- **Excepciones:** se documentan en la spec afectada con su motivo y alcance. Nunca se aplican por costumbre.
- **Cumplimiento:** al cerrar cada funcionalidad se revisan los seis principios. Una violación bloquea la entrega hasta corregirla.

### Historial de versiones

| Versión | Fecha      | Tipo  | Cambio                                                                                                                                                                                                                                                              |
| ------- | ---------- | ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1.0     | 2026-10-29 | —     | Ratificación inicial: jerarquía normativa, 6 principios, alcance obligatorio con bonus, flujo y gobernanza.                                                                                                                                                         |
| 1.1     | 2026-10-29 | MINOR | R1.2 adopta notación EARS para los criterios de aceptación; nuevas R1.7 (tres artefactos por dominio), R1.8 (ciclo de vida y aprobación de specs) y R1.9 (trazabilidad por IDs). La jerarquía apunta a `specs/README.md` y el paso 1 del flujo exige spec aprobada. |
| 1.1.1   | 2026-10-30 | PATCH | Alineación con la arquitectura v1.1: las referencias pasan de v1.0 a v1.1 (jerarquía, Principio 4, R5.6) y R4.1 concreta opciones ya previstas (UV en lugar de "UV o Poetry"; TypeScript ligero en el frontend). Enmienda puntual autorizada por el responsable del proyecto; no añade ni elimina principios ni reglas. |
