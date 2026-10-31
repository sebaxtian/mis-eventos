<script setup lang="ts">
import { RouterLink, RouterView, useRouter } from 'vue-router'
import BaseAlert from '@/components/base/BaseAlert.vue'
import { useAuthStore } from '@/stores/auth'
import { useNotificationStore } from '@/stores/notification'

const router = useRouter()
const authStore = useAuthStore()
const notificationStore = useNotificationStore()

async function handleLogout(): Promise<void> {
  authStore.logout()
  await router.push({ name: 'login' })
}
</script>

<template>
  <div class="min-h-screen bg-slate-50 text-slate-900">
    <header class="border-b border-slate-200 bg-white">
      <nav class="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
        <RouterLink to="/" class="text-lg font-bold text-indigo-600">
          Mis Eventos
        </RouterLink>
        <div class="flex items-center gap-4 text-sm font-medium">
          <RouterLink to="/" class="hover:text-indigo-600">
            Eventos
          </RouterLink>
          <template v-if="authStore.isAuthenticated">
            <RouterLink
              v-if="authStore.isAdmin"
              to="/admin/users"
              class="hover:text-indigo-600"
            >
              Administración
            </RouterLink>
            <RouterLink to="/profile" class="hover:text-indigo-600">
              Mi perfil
            </RouterLink>
            <button
              type="button"
              class="text-slate-700 hover:text-indigo-600"
              @click="handleLogout"
            >
              Cerrar sesión
            </button>
          </template>
          <template v-else>
            <RouterLink to="/login" class="hover:text-indigo-600">
              Iniciar sesión
            </RouterLink>
            <RouterLink to="/register" class="hover:text-indigo-600">
              Registrarse
            </RouterLink>
          </template>
        </div>
      </nav>
    </header>

    <div
      v-if="notificationStore.lastMessage"
      class="mx-auto max-w-5xl px-6 pt-4"
    >
      <BaseAlert
        :type="notificationStore.lastType || 'info'"
        :message="notificationStore.lastMessage"
        dismissible
        @dismiss="notificationStore.clear()"
      />
    </div>

    <RouterView />
  </div>
</template>
