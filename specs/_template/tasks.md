# Tareas TDD: <Nombre del dominio>

| Campo                  | Valor                          |
| ---------------------- | ------------------------------ |
| **ID del dominio**     | `<DOM>`                        |
| **Spec de referencia** | `specs/<dominio>/spec.md` vX.Y |
| **Plan de referencia** | `specs/<dominio>/plan.md`      |

> Ninguna tarea empieza hasta que la spec esté _Aprobada_ (R1.8). Cada tarea sigue el ciclo test → rojo → implementación mínima → verde → refactor (R3.1). El rojo debe fallar por la aserción esperada (R3.2).

**Estados:** `[ ]` pendiente · `[R]` test en rojo · `[V]` verde · `[x]` refactorizada y cerrada

## Backend

| #   | Estado | Criterio    | Test (en rojo primero)        | Implementación |
| --- | ------ | ----------- | ----------------------------- | -------------- |
| B1  | [ ]    | <DOM>-AC-01 | `test_<dom>_ac_01_<behavior>` | …              |
| B2  | [ ]    | <DOM>-AC-02 | `test_<dom>_ac_02_<behavior>` | …              |

## Frontend

| #   | Estado | Criterio    | Test (en rojo primero)         | Implementación |
| --- | ------ | ----------- | ------------------------------ | -------------- |
| F1  | [ ]    | <DOM>-AC-0N | `it('<DOM>-AC-0N <behavior>')` | …              |

## Definition of Done del dominio

- [ ] Todos los criterios `<DOM>-AC-NN` tienen al menos un test con su ID en el nombre.
- [ ] Suite de backend y frontend en verde; sin `skip`/`xfail` sin justificar (R3.8).
- [ ] Reglas dependientes de PostgreSQL probadas contra PostgreSQL (R3.6).
- [ ] Contrato OpenAPI verificado y frontend alineado (R2.4).
- [ ] Mensajes de UI y `detail` de errores en español; código en inglés (R6).
- [ ] Sin secretos en el repositorio (R5.7).
- [ ] Estado actualizado en `specs/README.md` y entrada en `MEMORY.md`.
