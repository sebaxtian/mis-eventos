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
    │   └── users.ts
    ├── stores/
    │   ├── auth.ts
    │   ├── events.ts
    │   └── notification.ts
    ├── router/
    │   └── index.ts
    ├── components/
    │   ├── base/
    │   │   ├── BaseAlert.vue
    │   │   ├── BaseButton.vue
    │   │   ├── BaseInput.vue
    │   │   ├── BaseSkeleton.vue
    │   │   └── BaseSpinner.vue
    │   └── events/
    │       ├── EventCard.vue
    │       └── EventForm.vue
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
        └── router.guards.spec.ts
```

## Rutas

Todas las vistas se cargan de forma diferida (`() => import(...)`); `EventForm.vue` se carga además con `defineAsyncComponent`.

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

Última validación registrada del Dominio 2 (`events`, 2026-10-31):

| Control               | Resultado                                                        |
| --------------------- | ---------------------------------------------------------------- |
| Tests                 | **45 passed** en 10 archivos (19 de `platform`/`auth` + 26 de `events`) |
| Cobertura             | 92.65 % statements/lines, 83.78 % branches, 90.17 % functions    |
| Tipos                 | `vue-tsc --noEmit` sin errores                                   |
| Build                 | 126 módulos; chunks diferidos minificados y sin `.map` públicos   |

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
