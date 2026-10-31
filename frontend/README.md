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
    ├── assets/
    │   └── main.css
    ├── types/
    │   └── api.ts
    ├── services/
    │   └── api.ts
    ├── stores/
    │   ├── auth.ts
    │   └── notification.ts
    ├── router/
    │   └── index.ts
    ├── components/
    │   └── base/
    │       ├── BaseInput.vue
    │       ├── BaseButton.vue
    │       ├── BaseSpinner.vue
    │       ├── BaseSkeleton.vue
    │       └── BaseAlert.vue
    ├── views/
    │   ├── HomePlaceholderView.vue
    │   ├── LoginPlaceholderView.vue
    │   └── AdminPlaceholderView.vue
    └── __tests__/
        ├── api.interceptor.spec.ts
        ├── router.guards.spec.ts
        └── base.components.spec.ts
```

## Comandos principales

### Pruebas unitarias y cobertura (Vitest)

```bash
npm run test -- --run
npx vitest run --coverage
```

### Verificación de tipos (TypeScript / Vue)

```bash
npx vue-tsc --noEmit
```

### Build de producción minificado

Genera artefactos optimizados y minificados en `dist/` con chunks separados por ruta diferida y sin archivos `.map` públicos:

```bash
npm run build
```
