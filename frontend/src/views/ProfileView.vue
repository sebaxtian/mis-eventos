<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import type { AxiosError } from 'axios'
import BaseAlert from '@/components/base/BaseAlert.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseInput from '@/components/base/BaseInput.vue'
import BaseSkeleton from '@/components/base/BaseSkeleton.vue'
import type { ApiError, RegistrationStatus, UserRole } from '@/types/api'
import { useAuthStore } from '@/stores/auth'
import { useRegistrationStore } from '@/stores/registrations'

const router = useRouter()
const authStore = useAuthStore()
const registrationStore = useRegistrationStore()

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

const REGISTRATION_STATUS_LABELS: Record<RegistrationStatus, string> = {
  ACTIVE: 'Activa',
  CANCELLED: 'Cancelada',
}

const registrationStatusFilter = ref<RegistrationStatus | ''>('')
const registrationFeedback = ref('')
const registrationFeedbackType = ref<'success' | 'error'>('success')

const registrationDateFormatter = new Intl.DateTimeFormat('es-CO', {
  dateStyle: 'long',
  timeZone: 'UTC',
})

function formatRegistrationDate(isoDate: string): string {
  const parsed = new Date(isoDate)
  if (Number.isNaN(parsed.getTime())) return ''
  return registrationDateFormatter.format(parsed)
}

async function loadRegistrations(page = 1): Promise<void> {
  await registrationStore.fetchMyRegistrations({
    page,
    size: 10,
    status: registrationStatusFilter.value,
  })
}

function onRegistrationFilterChange(): void {
  registrationFeedback.value = ''
  void loadRegistrations(1)
}

function goToPreviousRegistrationPage(): void {
  if (registrationStore.page <= 1) return
  void loadRegistrations(registrationStore.page - 1)
}

function goToNextRegistrationPage(): void {
  if (registrationStore.page >= registrationStore.pages) return
  void loadRegistrations(registrationStore.page + 1)
}

async function onCancelRegistration(id: number): Promise<void> {
  if (
    !window.confirm(
      '¿Seguro que deseas cancelar esta inscripción?',
    )
  ) {
    return
  }
  registrationFeedback.value = ''
  try {
    await registrationStore.cancelRegistration(id)
    registrationFeedbackType.value = 'success'
    registrationFeedback.value = 'Inscripción cancelada correctamente.'
    await loadRegistrations(registrationStore.page)
  } catch {
    registrationFeedbackType.value = 'error'
    registrationFeedback.value =
      registrationStore.errorMessage ||
      'No se pudo cancelar la inscripción'
  }
}

onMounted(() => {
  registrationStore.reset()
  void loadRegistrations(1)
})
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

    <section
      data-testid="registrations-section"
      class="mt-6 rounded-lg border border-slate-200 bg-white p-6 shadow-sm"
    >
      <div class="flex flex-wrap items-center justify-between gap-3">
        <h2 class="text-lg font-semibold text-slate-900">
          Mis inscripciones
        </h2>
        <div class="flex items-center gap-2">
          <label
            for="registrations-status-filter"
            class="text-xs font-semibold uppercase tracking-wide text-slate-500"
          >
            Estado
          </label>
          <select
            id="registrations-status-filter"
            v-model="registrationStatusFilter"
            data-testid="registrations-status-filter"
            class="rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-800"
            @change="onRegistrationFilterChange"
          >
            <option value="">Todas</option>
            <option value="ACTIVE">Activas</option>
            <option value="CANCELLED">Canceladas</option>
          </select>
        </div>
      </div>

      <BaseAlert
        v-if="registrationFeedback"
        :type="registrationFeedbackType"
        :message="registrationFeedback"
        class="mt-3"
      />

      <div
        v-if="registrationStore.isLoading"
        data-testid="registrations-loading"
        class="mt-3"
      >
        <BaseSkeleton :lines="3" />
      </div>

      <div
        v-else-if="registrationStore.errorMessage"
        data-testid="registrations-error"
        class="mt-3 flex flex-col gap-2"
      >
        <BaseAlert type="error" :message="registrationStore.errorMessage" />
        <div>
          <BaseButton
            type="button"
            variant="secondary"
            data-testid="registrations-retry"
            @click="loadRegistrations(1)"
          >
            Reintentar
          </BaseButton>
        </div>
      </div>

      <p
        v-else-if="registrationStore.items.length === 0"
        data-testid="registrations-empty"
        class="mt-3 rounded-lg border border-dashed border-slate-300 bg-white p-4 text-sm text-slate-600"
      >
        Todavía no tienes inscripciones.
      </p>

      <ul v-else class="mt-3 flex flex-col gap-3">
        <li
          v-for="registration in registrationStore.items"
          :key="registration.id"
          data-testid="registration-item"
          class="rounded-lg border border-slate-200 bg-white p-4"
        >
          <div class="flex flex-wrap items-start justify-between gap-2">
            <div>
              <p class="text-sm font-semibold text-slate-900">
                {{ registration.event.title }}
              </p>
              <p class="text-xs text-slate-600">
                {{ formatRegistrationDate(registration.event.date) }}
              </p>
              <p
                v-if="registration.session"
                class="mt-1 text-xs text-slate-600"
              >
                Sesión: {{ registration.session.title }} —
                {{ registration.session.speaker }}
              </p>
            </div>
            <span
              class="rounded-full px-3 py-1 text-xs font-medium"
              :class="{
                'bg-emerald-100 text-emerald-800':
                  registration.status === 'ACTIVE',
                'bg-slate-200 text-slate-700':
                  registration.status === 'CANCELLED',
              }"
            >
              {{ REGISTRATION_STATUS_LABELS[registration.status] }}
            </span>
          </div>
          <div class="mt-3 flex justify-end">
            <BaseButton
              type="button"
              variant="danger"
              data-testid="registration-cancel-button"
              @click="onCancelRegistration(registration.id)"
            >
              Cancelar inscripción
            </BaseButton>
          </div>
        </li>
      </ul>

      <div
        v-if="registrationStore.pages > 0"
        class="mt-3 flex items-center justify-between gap-2"
      >
        <BaseButton
          type="button"
          variant="secondary"
          data-testid="registrations-prev"
          :disabled="registrationStore.page <= 1"
          @click="goToPreviousRegistrationPage"
        >
          Anterior
        </BaseButton>
        <p data-testid="registrations-page" class="text-xs text-slate-600">
          Página {{ registrationStore.page }} de
          {{ registrationStore.pages }}
        </p>
        <BaseButton
          type="button"
          variant="secondary"
          data-testid="registrations-next"
          :disabled="registrationStore.page >= registrationStore.pages"
          @click="goToNextRegistrationPage"
        >
          Siguiente
        </BaseButton>
      </div>
    </section>
  </main>
</template>
