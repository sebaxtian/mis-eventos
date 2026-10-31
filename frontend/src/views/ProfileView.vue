<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import type { AxiosError } from 'axios'
import BaseAlert from '@/components/base/BaseAlert.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseInput from '@/components/base/BaseInput.vue'
import type { ApiError, UserRole } from '@/types/api'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const fullName = ref(authStore.user?.full_name ?? '')
const feedbackMessage = ref('')
const feedbackType = ref<'success' | 'error'>('success')
const isSaving = ref(false)

watch(
  () => authStore.user?.full_name,
  (newName) => {
    if (typeof newName === 'string') {
      fullName.value = newName
    }
  },
)

const ROLE_LABELS_ES: Record<UserRole, string> = {
  ADMIN: 'Administrador',
  ORGANIZER: 'Organizador',
  ATTENDEE: 'Asistente',
}

const roleLabel = computed(() => {
  const role = authStore.user?.role
  return role ? ROLE_LABELS_ES[role] : '—'
})

const statusLabel = computed(() =>
  authStore.user?.is_active ? 'Activa' : 'Inactiva',
)

async function onSave(): Promise<void> {
  feedbackMessage.value = ''
  const trimmed = fullName.value.trim()
  if (trimmed.length < 2 || trimmed.length > 120) {
    feedbackType.value = 'error'
    feedbackMessage.value = 'El nombre debe tener entre 2 y 120 caracteres'
    return
  }

  isSaving.value = true
  try {
    await authStore.updateProfile({ full_name: trimmed })
    feedbackType.value = 'success'
    feedbackMessage.value = 'Perfil actualizado correctamente.'
  } catch (err: unknown) {
    const axiosErr = err as AxiosError<ApiError>
    const fieldMsg = axiosErr.response?.data?.errors?.[0]?.message
    const detail = axiosErr.response?.data?.detail
    feedbackType.value = 'error'
    feedbackMessage.value =
      fieldMsg || detail || 'No se pudo actualizar el perfil'
  } finally {
    isSaving.value = false
  }
}

async function onLogout(): Promise<void> {
  authStore.logout()
  await router.push({ name: 'login' })
}
</script>

<template>
  <main class="mx-auto max-w-2xl p-6">
    <div class="flex items-center justify-between">
      <h1 class="text-2xl font-bold text-slate-900">Mi perfil</h1>
      <BaseButton
        type="button"
        variant="secondary"
        data-testid="logout-button"
        @click="onLogout"
      >
        Cerrar sesión
      </BaseButton>
    </div>

    <BaseAlert
      v-if="feedbackMessage"
      :type="feedbackType"
      :message="feedbackMessage"
      class="mt-4"
    />

    <section class="mt-6 rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
      <dl class="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <dt class="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Correo electrónico
          </dt>
          <dd class="mt-1 text-sm font-medium text-slate-900">
            {{ authStore.user?.email }}
          </dd>
        </div>
        <div>
          <dt class="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Rol
          </dt>
          <dd class="mt-1 text-sm font-medium text-slate-900">
            {{ roleLabel }}
          </dd>
        </div>
        <div>
          <dt class="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Estado de la cuenta
          </dt>
          <dd class="mt-1 text-sm font-medium text-slate-900">
            {{ statusLabel }}
          </dd>
        </div>
      </dl>

      <form class="mt-6 flex flex-col gap-4 border-t border-slate-200 pt-6" @submit.prevent="onSave">
        <BaseInput
          id="profile-full-name"
          v-model="fullName"
          label="Nombre completo"
          required
        />
        <div class="flex justify-end">
          <BaseButton type="submit" :is-loading="isSaving">
            Guardar cambios
          </BaseButton>
        </div>
      </form>
    </section>
  </main>
</template>
