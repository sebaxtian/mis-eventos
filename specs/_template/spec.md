# Spec: <Nombre del dominio>

| Campo                      | Valor                                                                  |
| -------------------------- | ---------------------------------------------------------------------- |
| **ID del dominio**         | `<DOM>`                                                                |
| **Versión**                | 0.1                                                                    |
| **Estado**                 | Borrador                                                               |
| **Fecha**                  | AAAA-MM-DD                                                             |
| **Dependencias**           | `<dominio>`, …                                                         |
| **Decisiones bloqueantes** | Ninguna / lista de decisiones abiertas (bloquean el paso a _Aprobada_) |

> Esta spec describe **qué** hace el sistema, no cómo se implementa. Los detalles técnicos van en `plan.md`. Estado según R1.8 de `docs/constitution.md`: solo el usuario la marca como _Aprobada_.

## 1. Objetivo

Qué problema resuelve este dominio y para quién, en dos o tres frases.

## 2. Roles involucrados

| Rol         | Qué puede hacer en este dominio |
| ----------- | ------------------------------- |
| Anónimo     |                                 |
| `ATTENDEE`  |                                 |
| `ORGANIZER` |                                 |
| `ADMIN`     |                                 |

## 3. Reglas de negocio

- **<DOM>-BR-01** <Regla verificable, en una sola frase.>
- **<DOM>-BR-02** …

## 4. Contrato de API

Todas las rutas cuelgan de `/api`. Los errores siguen el formato definido en `specs/platform/spec.md` con `detail` en español.

### 4.1 `<MÉTODO> /api/<ruta>`

- **Descripción:** …
- **Autenticación / rol requerido:** …
- **Request:**

  ```json
  {}
  ```

- **Response `2xx`:**

  ```json
  {}
  ```

- **Errores:**

  | Código | Cuándo                             | `detail` (español) |
  | ------ | ---------------------------------- | ------------------ |
  | 401    | Token ausente, inválido o expirado |                    |
  | 403    | Rol o propiedad insuficiente       |                    |
  | 404    |                                    |                    |
  | 409    |                                    |                    |
  | 422    |                                    |                    |

## 5. Criterios de aceptación (EARS)

Cada criterio tiene al menos un test cuyo nombre incluye su ID (R1.5, R1.9).

| ID              | Criterio                                                         | Reglas      |
| --------------- | ---------------------------------------------------------------- | ----------- |
| **<DOM>-AC-01** | Cuando <disparador>, el sistema debe <respuesta>.                | <DOM>-BR-01 |
| **<DOM>-AC-02** | Si <condición no deseada>, entonces el sistema debe <respuesta>. |             |
| **<DOM>-AC-03** | Mientras <estado>, el sistema debe <respuesta>.                  |             |

## 6. Casos límite

- …

## 7. Fuera de alcance

- …

## 8. Decisiones resueltas

| Fecha | Pregunta | Decisión | Motivo |
| ----- | -------- | -------- | ------ |
|       |          |          |        |

## 9. Historial

| Versión | Fecha      | Cambio            |
| ------- | ---------- | ----------------- |
| 0.1     | AAAA-MM-DD | Borrador inicial. |
