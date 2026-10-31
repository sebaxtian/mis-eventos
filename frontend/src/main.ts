import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { configureApiNavigation } from './services/api'
import './assets/main.css'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)

configureApiNavigation(
  (location) => {
    void router.push(location)
  },
  () => router.currentRoute.value.fullPath,
)

app.mount('#app')
