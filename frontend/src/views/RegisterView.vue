<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import type { AxiosError } from 'axios'
import BaseAlert from '@/components/base/BaseAlert.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseInput from '@/components/base/BaseInput.vue'
import type { ApiError } from '@/types/api'
import { useAuthStore } from '@/stores/auth'
import { useNotificationStore } from '@/stores/notification'

const router = useRouter()
const authStore = useAuthStore()
const notificationStore = useNotificationStore()

const fullName = ref('')
const email = ref('')
const password = ref('')
const errorMessage = ref('')
const isLoading = ref(false)

async function onSubmit(): Promise<void> {
  errorMessage.value = ''
  const trimmedName = fullName.value.trim()
  if (trimmedName.length < 2 || trimmedName.length > 120) {
    errorMessage.value = 'El nombre debe tener entre 2 y 120 caracteres'
    return
  }
  if (password.value.length < 8 || password.value.length > 128 || !password.value.trim()) {
    errorMessage.value = 'La contraseña debe tener entre 8 y 128 caracteres'
    return
  }

  isLoading.value = true
  try {
    await authStore.register({
      full_name: trimmedName,
      email: email.value.trim().toLowerCase(),
      password: password.value,
    })
    notificationStore.notify(
      'Cuenta creada exitosamente. Inicia sesión para continuar.',
      'success',
    )
    await router.push({ name: 'login' })
  } catch (err: unknown) {
    const axiosErr = err as AxiosError<ApiError>
    const fieldMsg = axiosErr.response?.data?.errors?.[0]?.message
    const detail = axiosErr.response?.data?.detail
    errorMessage.value =
      fieldMsg || detail || 'No se pudo completar el registro'
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <main class="mx-auto max-w-md p-6">
    <h1 class="text-2xl font-bold text-slate-900">Crear cuenta</h1>
    <p class="mt-1 text-sm text-slate-600">
      Regístrate para inscribirte en los próximos eventos.
    </p>

    <BaseAlert
      v-if="errorMessage"
      type="error"
      :message="errorMessage"
      class="mt-4"
    />

    <form class="mt-6 flex flex-col gap-4" @submit.prevent="onSubmit">
      <BaseInput
        id="register-full-name"
        v-model="fullName"
        label="Nombre completo"
        placeholder="Ana Pérez"
        required
      />
      <BaseInput
        id="register-email"
        v-model="email"
        type="email"
        label="Correo electrónico"
        placeholder="ana@ejemplo.com"
        required
      />
      <BaseInput
        id="register-password"
        v-model="password"
        type="password"
        label="Contraseña"
        placeholder="Mínimo 8 caracteres"
        required
      />
      <BaseButton type="submit" :is-loading="isLoading">
        Registrarse
      </BaseButton>
    </form>

    <p class="mt-4 text-center text-sm text-slate-600">
      ¿Ya tienes cuenta?
      <RouterLink to="/login" class="font-medium text-indigo-600 hover:underline">
        Inicia sesión
      </RouterLink>
    </p>
  </main>
</template>
