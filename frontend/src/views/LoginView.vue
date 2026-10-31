<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import type { AxiosError } from 'axios'
import BaseAlert from '@/components/base/BaseAlert.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseInput from '@/components/base/BaseInput.vue'
import type { ApiError } from '@/types/api'
import { resolveSafeRedirect } from '@/router'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const email = ref('')
const password = ref('')
const errorMessage = ref('')
const isLoading = ref(false)

async function onSubmit(): Promise<void> {
  errorMessage.value = ''
  isLoading.value = true
  try {
    await authStore.login({
      email: email.value.trim().toLowerCase(),
      password: password.value,
    })
    const target = resolveSafeRedirect(route.query.redirect)
    await router.push(target)
  } catch (err: unknown) {
    const axiosErr = err as AxiosError<ApiError>
    const status = axiosErr.response?.status
    const fieldMsg = axiosErr.response?.data?.errors?.[0]?.message
    const detail = axiosErr.response?.data?.detail
    if (status === 401) {
      errorMessage.value = detail || 'Credenciales inválidas'
    } else {
      errorMessage.value =
        fieldMsg || detail || 'Credenciales inválidas'
    }
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <main class="mx-auto max-w-md p-6">
    <h1 class="text-2xl font-bold text-slate-900">Iniciar sesión</h1>
    <p class="mt-1 text-sm text-slate-600">
      Ingresa tus credenciales para acceder a tu cuenta.
    </p>

    <BaseAlert
      v-if="errorMessage"
      type="error"
      :message="errorMessage"
      class="mt-4"
    />

    <form class="mt-6 flex flex-col gap-4" @submit.prevent="onSubmit">
      <BaseInput
        id="login-email"
        v-model="email"
        type="email"
        label="Correo electrónico"
        placeholder="ana@ejemplo.com"
        required
      />
      <BaseInput
        id="login-password"
        v-model="password"
        type="password"
        label="Contraseña"
        placeholder="Tu contraseña"
        required
      />
      <BaseButton type="submit" :is-loading="isLoading">
        Iniciar sesión
      </BaseButton>
    </form>

    <p class="mt-4 text-center text-sm text-slate-600">
      ¿No tienes cuenta?
      <RouterLink
        to="/register"
        class="font-medium text-indigo-600 hover:underline"
      >
        Regístrate aquí
      </RouterLink>
    </p>
  </main>
</template>
