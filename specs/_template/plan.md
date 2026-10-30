# Plan técnico: <Nombre del dominio>

| Campo                  | Valor                          |
| ---------------------- | ------------------------------ |
| **ID del dominio**     | `<DOM>`                        |
| **Spec de referencia** | `specs/<dominio>/spec.md` vX.Y |
| **Fecha**              | AAAA-MM-DD                     |

> Este plan describe **cómo** se implementa la spec. No añade comportamiento: si algo no está en `spec.md`, primero se agrega allí (R1.1, R1.5). Identificadores en inglés (R6).

## 1. Modelo de datos y migraciones

| Tabla / modelo | Campos relevantes | Restricciones (PK, FK, UNIQUE, CHECK) |
| -------------- | ----------------- | ------------------------------------- |
|                |                   |                                       |

- Migración Alembic: …
- Índices (incluidos los de `pg_trgm` si aplica): …

## 2. Backend

- **Routers y endpoints:** …
- **Dependencias de FastAPI** (autenticación y autorización, R5.2): …
- **Schemas de entrada y salida** (R5.5): …
- **Servicios / lógica de negocio:** …
- **Transacciones y bloqueos** (R5.4, si aplica): …
- **Caché Redis** (R4.4, si aplica): claves, TTL, invalidación y comportamiento si Redis no está disponible.

## 3. Frontend

- **Rutas** (lazy loading) y guards: …
- **Stores de Pinia:** estado, acciones, getters.
- **Componentes:** nuevos y reutilizados.
- **Manejo de errores y estados de carga:** …

## 4. Librerías de soporte (R4.2)

| Librería | Componente del stack al que sirve | Motivo |
| -------- | --------------------------------- | ------ |
|          |                                   |        |

Cada librería nueva se registra también en `MEMORY.md`.

## 5. Estrategia de pruebas

- **Backend (pytest):** unitarias e integración con `TestClient`; qué casos requieren PostgreSQL (R3.6).
- **Frontend (Vitest):** stores, componentes y guards.
- **Fixtures y datos de prueba:** …

## 6. Riesgos y mitigaciones

- …
