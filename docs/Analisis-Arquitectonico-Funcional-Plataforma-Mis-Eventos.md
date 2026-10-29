# Análisis Arquitectónico y Funcional: Plataforma "Mis Eventos"

**Versión:** 1.0
**Fecha:** Miércoles, 28 de Octubre de 2026
**Metodología:** Spec-Driven Development (SDD) con OpenCode

> **Nota de Evolución:** Dado que trabajaremos bajo la metodología estricta de Spec-Driven Development (SDD) orquestada con el agente OpenCode, este documento representa la especificación inicial (v1.0). Esta arquitectura evolucionará iterativamente a medida que se inicie el desarrollo formal del proyecto desde Visual Studio Code y se refinen los contratos técnicos.

Con las decisiones estratégicas consolidadas, el diseño del sistema ha evolucionado de un simple requerimiento a una arquitectura robusta, escalable y, sobre todo, viable para ser implementada, probada y documentada en un marco estricto de 5 días.

A continuación, presento el diseño arquitectónico final que gobernará nuestra especificación (SDD) y el desarrollo de la prueba para Tusdatos.co.

## 1. Topología de Infraestructura (Capa de Contenedores)

El sistema será orquestado íntegramente a través de `docker-compose.yml` e incluirá una capa de red enrutada para simular un entorno de producción real, destacando tu perfil de ingeniería:

- **Proxy Inverso y Balanceador (Nginx):** Actuará como el punto de entrada único (API Gateway). Redirigirá el tráfico del frontend al contenedor web y las peticiones `/api` al backend, solucionando de raíz los problemas de CORS. Está preparado para balancear carga entre múltiples réplicas de la API si se escala en el futuro.
- **Contenedor Web (Frontend):** Servidor estático (Nginx ligero o Node) sirviendo los artefactos compilados de Vue.js.
- **Contenedores API (Backend):** Instancia de FastAPI corriendo bajo Uvicorn. Construido estrictamente sobre la imagen base `python:3.14-slim` para cumplir el requerimiento técnico al milímetro.
- **Base de Datos (PostgreSQL):** Motor relacional persistido mediante volúmenes de Docker, gestionando la integridad referencial.
- **Capa de Caché (Redis):** Motor en memoria (Bonus). Reducirá la carga en PostgreSQL al cachear las respuestas de los listados de eventos paginados y consultas de solo lectura.

### Diagrama de Arquitectura de Infraestructura

```mermaid
---
title: Topología de Infraestructura - v1.0 (28 de Octubre de 2026)
---
graph TD
    Client((Cliente Web)) -->|HTTP/HTTPS| Nginx[Nginx API Gateway / Load Balancer]

    subgraph Docker Compose Network
        Nginx -->|Rutas /| WebContainer[Contenedor Web Vue.js]
        Nginx -->|Rutas /api| ApiContainer[Contenedor API FastAPI]

        ApiContainer -->|Consultas SQL| DB[(PostgreSQL)]
        ApiContainer -->|Lectura/Escritura Caché| Redis[(Redis Cache)]
    end
```

## 2. Diseño del Backend (FastAPI + SQLModel)

La API será el núcleo de las reglas de negocio, diseñada bajo principios RESTful y documentada automáticamente (OpenAPI):

- **Autenticación y Seguridad (RBAC):** Implementación de JWT (JSON Web Tokens). Se integrará el Bono de Roles (Admin, Organizador, Asistente).
  - _Admin:_ Gestión de perfiles y visibilidad total.
  - _Organizador:_ CRUD de sus propios eventos y sesiones.
  - _Asistente:_ Lectura de eventos e inscripción.
- **Modelado de Datos (SQLAlchemy/SQLModel):**
  - `User`: Credenciales, datos básicos y un enum de `Role`.
  - `Event`: Entidad principal. Contiene `title`, `description`, `date`, `total_capacity`, `status` (Borrador, Publicado, Cancelado), e índices trigrama para la búsqueda por nombre.
  - `Session`: Vinculada a un evento (One-to-Many). Contiene `title`, `speaker`, `start_time`, `end_time` y `capacity`. Requerirá lógica de negocio para evitar solapamiento de horarios.
  - `Registration`: Tabla transaccional (Many-to-Many entre User y Event/Session) que validará atómicamente si `current_registrations < capacity` antes de insertar.
- **Migraciones:** `Alembic` controlará el esquema de la base de datos, garantizando que el contenedor de la API pueda ejecutar migraciones al inicializarse.

### Diagrama de Arquitectura Backend (FastAPI)

```mermaid
---
title: Arquitectura Backend FastAPI - v1.0 (28 de Octubre de 2026)
---
graph TD
    subgraph Backend Application
        direction TB
        API_Router[Routers: /auth, /events, /sessions]
        Dependency[Dependencies: get_current_user, DB Session]
        Pydantic[Validación Schemas Pydantic]
        Services[Lógica de Negocio / Controllers]
        ORM[SQLModel / SQLAlchemy ORM]
    end

    ClientRequest((Petición Nginx)) -->|HTTP REST| API_Router
    API_Router --> Dependency
    API_Router --> Pydantic
    Pydantic --> Services
    Services --> ORM

    ORM -->|Consultas SQL| Postgres[(PostgreSQL)]
    Services -->|Set/Get| Redis[(Redis Cache)]
```

### Diagrama Entidad-Relación (Básico)

```mermaid
---
title: Diagrama Entidad-Relación - v1.0 (28 de Octubre de 2026)
---
erDiagram
    USER ||--o{ REGISTRATION : registers
    USER ||--o{ EVENT : organizes
    EVENT ||--o{ SESSION : contains
    EVENT ||--o{ REGISTRATION : has
    SESSION ||--o{ REGISTRATION : has

    USER {
        int id PK
        string email
        string password_hash
        enum role
    }
    EVENT {
        int id PK
        int organizer_id FK
        string title
        datetime date
        int total_capacity
        enum status
    }
    SESSION {
        int id PK
        int event_id FK
        datetime start_time
        datetime end_time
        int capacity
    }
    REGISTRATION {
        int id PK
        int user_id FK
        int event_id FK
        int session_id FK
    }
```

## 3. Diseño del Frontend (Vue.js 3 + Pinia)

La arquitectura del cliente prioriza la velocidad de desarrollo y la estabilidad, utilizando la _Composition API_ y `<script setup>` con JavaScript moderno/TypeScript ligero.

- **Enrutamiento (Vue Router):** Implementaremos Navigation Guards (`router.beforeEach`). Si un Asistente intenta entrar a `/admin/events`, el router interceptará la petición y lo enviará al listado general.
- **Gestión de Estado (Pinia):**
  - `useAuthStore`: Manejará el token JWT persistido (en `localStorage` o `sessionStorage`) y los datos del usuario logueado.
  - `useEventStore`: Consumirá la API, cacheará localmente la lista de eventos activa, y gestionará la paginación.
- **Lógica de Consumo (Axios/Fetch):** Crearemos un interceptor global. Si el token expira (401) o el usuario no tiene permisos (403), el interceptor limpiará el store y redirigirá al login mostrando un mensaje claro.
- **UI/UX (Tailwind CSS):**
  - Se construirán componentes atómicos: `EventCard.vue`, `BaseInput.vue`, `BaseButton.vue`.
  - Se implementarán Skeleton Loaders y/o Spinners vinculados a variables reactivas (ej. `const isLoading = ref(false)`) para otorgar feedback visual estricto en cada petición HTTP, cumpliendo el requerimiento de UI/UX.

### Diagrama de Arquitectura Frontend (Vue.js)

```mermaid
---
title: Arquitectura Frontend Vue.js - v1.0 (28 de Octubre de 2026)
---
graph TD
    subgraph Frontend Application Vue.js
        direction TB
        Router[Vue Router + Navigation Guards]
        Views[Vistas: EventList, Admin, Login]
        Components[Componentes UI: Tailwind CSS]
        Pinia[Pinia Stores: AuthStore, EventStore]
        Axios[Axios HTTP Client + Interceptors]
    end

    User((Usuario)) -->|Navega / Interactúa| Views
    Views --> Router
    Router --> Views
    Views --> Components
    Components -->|Dispara Actions| Pinia
    Pinia -->|Peticiones| Axios
    Axios -->|Respuestas / Intercepta 401| Pinia
    Pinia -->|Actualiza Estado Reactivo| Views

    Axios -->|Llamadas API| API((Backend FastAPI))
```

## 4. Estrategia de Testing (Aseguramiento de Calidad)

- **Backend (`pytest`):** Usaremos `TestClient` de FastAPI combinado con una base de datos SQLite en memoria (o PostgreSQL en un contenedor de test) para probar la validación de capacidad (ej. intentar registrar a 101 personas en un evento de 100). Se generará el reporte XML de cobertura.
- **Frontend (`Vitest`):** Pruebas unitarias sobre las funciones de los stores de Pinia y el renderizado básico de los componentes (ej. validar que el botón de "Inscribirse" no aparezca si el rol es "Organizador").

---

**Estado del Sistema:** Entendimiento total del proyecto alcanzado. La arquitectura está definida para equilibrar el despliegue avanzado (Balanceador, Redis, RBAC) con un desarrollo seguro y ágil en Vue.js.
