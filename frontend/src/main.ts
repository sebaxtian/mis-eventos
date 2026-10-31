import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { configureApiNavigation } from './services/api'
import { useAuthStore } from './stores/auth'
import './assets/main.css'

async function bootstrap(): Promise<void> {
  const app = createApp(App)
  const pinia = createPinia()

  app.use(pinia)

  configureApiNavigation(
    (location) => {
      void router.push(location)
    },
    () => router.currentRoute.value.fullPath,
  )

  const authStore = useAuthStore(pinia)
  await authStore.initialize()

  app.use(router)
  app.mount('#app')
}

void bootstrap()
