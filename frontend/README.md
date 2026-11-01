# Mis Eventos — Frontend SPA

Aplicación cliente (SPA) de la plataforma **Mis Eventos**, desarrollada con **Vue 3** (Composition API y `<script setup lang="ts">`), **TypeScript ligero**, **Vite**, **Vue Router** (carga diferida de rutas y guards de UX), **Pinia**, **Axios** (`baseURL: '/api'`) y **Tailwind CSS**.

## Requisitos

- Node.js 22+
- npm 10+

## Estructura del proyecto

```text
frontend/
├── Dockerfile
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
├── tailwind.config.js
├── postcss.config.js
└── src/
    ├── main.ts
    ├── App.vue
    ├── env.d.ts
    ├── assets/
    │   └── main.css
    ├── types/
    │   └── api.ts
    ├── services/
    │   ├── api.ts
    │   ├── auth.ts
    │   ├── events.ts
    │   ├── registrations.ts
    │   ├── sessions.ts
    │   └── users.ts
    ├── stores/
    │   ├── auth.ts
    │   ├── events.ts
    │   ├── notification.ts
    │   ├── registrations.ts
    │   └── sessions.ts
    ├── router/
    │   └── index.ts
    ├── components/
    │   ├── base/
    │   │   ├── BaseAlert.vue
    │   │   ├── BaseButton.vue
    │   │   ├── BaseInput.vue
    │   │   ├── BaseSkeleton.vue
    │   │   └── BaseSpinner.vue
    │   ├── events/
    │   │   ├── EventCard.vue
    │   │   └── EventForm.vue
    │   ├── registrations/
    │   │   └── EventRegistrationsList.vue
    │   └── sessions/
    │       ├── SessionTimeline.vue
    │       └── SessionForm.vue
    ├── views/
    │   ├── AdminPlaceholderView.vue
    │   ├── AdminUsersView.vue
    │   ├── EventDetailView.vue
    │   ├── EventFormView.vue
    │   ├── EventsListView.vue
    │   ├── LoginPlaceholderView.vue
    │   ├── LoginView.vue
    │   ├── ProfileView.vue
    │   └── RegisterView.vue
    └── __tests__/
        ├── admin.users.spec.ts
        ├── api.interceptor.spec.ts
        ├── auth.store.spec.ts
        ├── auth.views.spec.ts
        ├── base.components.spec.ts
        ├── events.components.spec.ts
        ├── events.store.spec.ts
        ├── events.upload.spec.ts
        ├── events.views.spec.ts
        ├── registrations.components.spec.ts
        ├── registrations.store.spec.ts
        ├── registrations.views.spec.ts
        ├── router.guards.spec.ts
        ├── sessions.components.spec.ts
        ├── sessions.store.spec.ts
        └── sessions.views.spec.ts
```

## Rutas

Todas las vistas se cargan de forma diferida (`() => import(...)`); `EventForm.vue`, `SessionForm.vue` y `EventRegistrationsList.vue` se cargan además con `defineAsyncComponent`.

| Ruta              | Nombre        | Vista                 | Acceso                                     |
| ----------------- | ------------- | --------------------- | ------------------------------------------ |
| `/`               | `home`        | `EventsListView.vue`  | Público                                    |
| `/events/new`     | `event-create`| `EventFormView.vue`   | `ORGANIZER` y `ADMIN` (`requiresAuth`)     |
| `/events/:id`     | `event-detail`| `EventDetailView.vue` | Público                                    |
| `/events/:id/edit`| `event-edit`  | `EventFormView.vue`   | `ORGANIZER` y `ADMIN` (`requiresAuth`)     |
| `/login`          | `login`       | `LoginView.vue`       | Público                                    |
| `/register`       | `register`    | `RegisterView.vue`    | Público                                    |
| `/profile`        | `profile`     | `ProfileView.vue`     | Autenticado                                |
| `/admin`          | `admin`       | `AdminPlaceholderView.vue` | `ADMIN`                               |
| `/admin/users`    | `admin-users` | `AdminUsersView.vue`  | `ADMIN`                                    |

Los guards de `router/index.ts` son **solo UX**: redirigen a `/login?redirect=...` cuando falta sesión y a `/` con aviso cuando el rol no autoriza. La autorización real la impone el backend.

## Dominio `events`

- **Tipos** (`src/types/api.ts`): `EventStatus`, `EventImageUrls`, `EventRead`, `EventCreatePayload`, `EventUpdatePayload`, `EventListQuery` y `EventListResponse`.
- **Servicio** (`src/services/events.ts`): listado con filtros, detalle, creación, actualización parcial, eliminación y subida de imagen (`multipart/form-data` real; esa petición no fuerza `Content-Type: application/json`).
- **Store** (`src/stores/events.ts`, `useEventStore`): `items`, `total`, `page`, `size`, `pages`, `search`, `statusFilter`, `mineOnly`, `currentEvent`, `isLoading`, `isSubmitting`, `errorMessage`; acciones `fetchEvents`, `fetchEventById`, `createEvent`, `updateEvent`, `deleteEvent`, `uploadEventImage`, `resetFilters` y `clearCurrentEvent`.
- **Componentes** (`src/components/events/`): `EventCard.vue` (imagen WebP responsiva con `srcset`, estado traducido y cupos) y `EventForm.vue` (formulario reutilizable de creación/edición).
- **Vistas** (`src/views/`): `EventsListView.vue` (búsqueda, filtros, paginación y alta), `EventDetailView.vue` (detalle, acciones de gestión y actualización de imagen) y `EventFormView.vue` (orquesta creación/edición y subida de imagen).

Regla de presentación: la UI muestra `total_capacity`, `registered_count` y `available_capacity` **tal como llegan de la API**; el cliente no calcula cupos (R2.5). La UI nunca usa `v-html` (R5.9).

## Dominio `sessions`

- **Tipos** (`src/types/api.ts`): `SessionRead`, `SessionListResponse`, `SessionCreatePayload` y `SessionUpdatePayload`.
- **Servicio** (`src/services/sessions.ts`): listado, detalle, creación, edición parcial y borrado sobre `/api/events/{event_id}/sessions`.
- **Store** (`src/stores/sessions.ts`, `useSessionStore`): `items`, `total`, `currentSession`, `isLoading`, `isSubmitting`, `errorMessage` y `fieldErrors`; acciones `fetchSessions`, `fetchSessionById`, `createSession`, `updateSession`, `deleteSession`, `clearErrors` y `reset`. Conserva `available_capacity` tal como llega de la API y nunca envía `event_id` en el cuerpo.
- **Componentes** (`src/components/sessions/`): `SessionTimeline.vue` (orden cronológico, hora UTC formateada en español, ponente, descripción opcional y cupos de la API; estado vacío en español) y `SessionForm.vue` (creación/edición, `datetime-local` convertido a UTC con `toISOString()`, errores `422` por campo y `409` en español).
- **Detalle** (`EventDetailView.vue`): compone el evento y su agenda con dos llamadas en paralelo (`GET /api/events/{id}` y `GET /api/events/{id}/sessions`), muestra `SessionTimeline`, estados de carga/error con reintento y carga `SessionForm.vue` con `defineAsyncComponent` en un chunk separado.
- **Permisos de UI:** solo el `ORGANIZER` dueño o un `ADMIN` ven «Añadir sesión», editar y eliminar; en eventos `CANCELLED` se ocultan los controles de escritura y se muestra el aviso en español. La autorización real sigue impuesta por el backend.

## Dominio `registrations`

- **Tipos** (`src/types/api.ts`): `RegistrationStatus`, `RegistrationEventSummary`, `RegistrationSessionSummary`, `RegistrationRead`, `RegistrationListRead`/`RegistrationListResponse`, `RegistrationListQuery` y `EventRegistrationListQuery`.
- **Servicio** (`src/services/registrations.ts`): alta al evento, alta a sesión, cancelación, «mis inscripciones», listado por evento y detalle; las altas devuelven `{ registration, created }` para distinguir un alta nueva (`201`) de una reactivación (`200`).
- **Store** (`src/stores/registrations.ts`, `useRegistrationStore`): `items`, `total`, `page`, `size`, `pages`, `currentRegistration`, `isLoading`, `isSubmitting`, `errorMessage`, `fieldErrors` y `lastCreatedStatus`; acciones `fetchMyRegistrations`, `fetchEventRegistrations`, `fetchRegistrationById`, `registerForEvent`, `registerForSession`, `cancelRegistration`, `clearErrors` y `reset`. Consume los DTOs tal como llegan y no calcula cupos.
- **Perfil** (`ProfileView.vue`): sección «Mis inscripciones» paginada y filtrable por estado (`Activa`/`Cancelada`), fecha UTC en español, resumen de sesión, cancelación con confirmación y feedback, estados de carga/vacío/error.
- **Detalle** (`EventDetailView.vue`): botón «Inscribirme» visible solo para `ATTENDEE` y eventos `PUBLISHED`; se deshabilita con aviso si `available_capacity === 0` y muestra «Ya estás inscrito en este evento» cuando existe una inscripción activa. Las sesiones se inscriben desde el slot `#actions` de `SessionTimeline`, con el aviso «Debes inscribirte primero al evento» cuando falta la inscripción al evento y «No hay cupos disponibles para esta sesión» cuando la sesión está llena. Tras cada alta o cancelación se refrescan el evento y la agenda desde la API.
- **Gestión** (`EventRegistrationsList.vue`): listado paginado y filtrable por estado para el `ORGANIZER` dueño o un `ADMIN`, con `Usuario #<user_id>`, estado y fecha; nunca `full_name` ni `email`. Se carga con `defineAsyncComponent` y `BaseSpinner` como `loadingComponent`.
- **Privacidad y cupos:** la UI usa `available_capacity` de la API y nunca lo recalcula (R2.5); no usa `v-html` (R5.9).

## Comandos principales

### Desarrollo local

```bash
npm install
npm run dev
```

Vite sirve la SPA en `http://localhost:5173` y proxya `/api` a `http://localhost:8000` (ver `vite.config.ts`). Para usar el gateway completo, levanta el stack con `docker compose up -d --build` desde la raíz y abre `http://localhost:8080`.

### Pruebas unitarias y cobertura (Vitest)

```bash
npm run test -- --run
npx vitest run --coverage
```

El script `pretest` instala las dependencias si falta `node_modules`. La suite usa `jsdom` y `@vue/test-utils`, con `createMemoryHistory` para las pruebas de router.

Validación de release v1.0.0 (2026-11-01):

| Control               | Resultado                                                        |
| --------------------- | ---------------------------------------------------------------- |
| Tests                 | **62 passed** en 16 archivos                                      |
| Cobertura             | **95,19 %** sentencias/líneas, 86,39 % ramas, 94,35 % funciones   |
| Tipos                 | `vue-tsc --noEmit` sin errores                                   |
| Build                 | **136 módulos**, 19 chunks JS con `EventForm`, `SessionForm` y `EventRegistrationsList` en chunks diferidos, artefactos minificados y **0 archivos `.map`** |

Detalle del alcance y de la validación completa en [CHANGELOG.md](../CHANGELOG.md).

### Verificación de tipos (TypeScript / Vue)

```bash
npx vue-tsc --noEmit
```

### Build de producción minificado

Genera artefactos optimizados y minificados en `dist/` con chunks separados por ruta diferida y sin archivos `.map` públicos:

```bash
npm run build
```

## Cliente HTTP

`src/services/api.ts` crea una instancia de Axios con `baseURL: '/api'` y un interceptor de respuestas:

- **401** → limpia la sesión y redirige a `/login`.
- **403** → conserva la sesión y muestra un aviso (R5.6).

No se realizan llamadas absolutas a `http://` desde la SPA: todas pasan por `/api`, servido por Nginx en el gateway.

## Docker

El `Dockerfile` construye la SPA y la sirve con Nginx dentro del contenedor `web`. En el stack completo, el gateway (`infra/nginx/default.conf`) sirve `/` desde `web` y enruta `/api` al backend, además de servir `/api/media/` desde el volumen `media`.
