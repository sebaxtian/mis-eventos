<script setup lang="ts">
import {
  computed,
  defineAsyncComponent,
  onMounted,
  ref,
} from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { AxiosError } from 'axios'
import BaseAlert from '@/components/base/BaseAlert.vue'
import BaseSkeleton from '@/components/base/BaseSkeleton.vue'
import { useEventStore } from '@/stores/events'
import { useNotificationStore } from '@/stores/notification'
import type {
  ApiError,
  EventCreatePayload,
  EventRead,
  EventUpdatePayload,
} from '@/types/api'

const EventForm = defineAsyncComponent(
  () => import('@/components/events/EventForm.vue'),
)

const route = useRoute()
const router = useRouter()
const store = useEventStore()
const notificationStore = useNotificationStore()

const isEditMode = computed(() => route.name === 'event-edit')
const eventId = computed(() => Number(route.params.id))

const isLoadingEvent = ref(route.name === 'event-edit')
const fieldErrors = ref<Record<string, string>>({})
const errorMessage = ref('')

onMounted(async () => {
  store.clearCurrentEvent()

  if (!isEditMode.value) {
    isLoadingEvent.value = false
    return
  }

  if (!Number.isInteger(eventId.value) || eventId.value <= 0) {
    errorMessage.value = 'Evento no encontrado'
    isLoadingEvent.value = false
    return
  }

  await store.fetchEventById(eventId.value)
  isLoadingEvent.value = false
  if (!store.currentEvent) {
    errorMessage.value = store.errorMessage || 'Evento no encontrado'
  }
})

async function handleSubmit(
  payload: EventCreatePayload | EventUpdatePayload,
  file: File | null,
): Promise<void> {
  fieldErrors.value = {}
  errorMessage.value = ''

  let saved: EventRead
  try {
    saved = isEditMode.value
      ? await store.updateEvent(eventId.value, payload)
      : await store.createEvent(payload as EventCreatePayload)
  } catch (error: unknown) {
    applySubmitError(error)
    return
  }

  if (file) {
    try {
      await store.uploadEventImage(saved.id, file)
    } catch {
      const message = isEditMode.value
        ? 'Los datos del evento se guardaron, pero la imagen no se pudo subir. Puedes intentarlo de nuevo desde el detalle.'
        : 'El evento se creó, pero la imagen no se pudo subir. Puedes intentarlo de nuevo desde el detalle.'

      notificationStore.notify(message, 'warning')
      await router.push({
        name: 'event-detail',
        params: { id: saved.id },
      })
      return
    }
  }

  await router.push({
    name: 'event-detail',
    params: { id: saved.id },
  })
}

function applySubmitError(error: unknown): void {
  const axiosError = error as AxiosError<ApiError>
  const status = axiosError.response?.status
  const detail = axiosError.response?.data?.detail
  const errors = axiosError.response?.data?.errors

  if (status === 422 && errors && errors.length > 0) {
    fieldErrors.value = Object.fromEntries(
      errors.map((item) => [item.field, item.message]),
    )
    errorMessage.value =
      detail || 'Error de validación en los datos enviados'
    return
  }

  errorMessage.value = detail || 'No se pudo guardar el evento'
}

async function handleCancel(): Promise<void> {
  if (isEditMode.value && Number.isInteger(eventId.value)) {
    await router.push({
      name: 'event-detail',
      params: { id: eventId.value },
    })
    return
  }
  await router.push({ name: 'home' })
}
</script>

<template>
  <main class="mx-auto max-w-2xl p-6">
    <h1 class="text-2xl font-bold text-slate-900">
      {{ isEditMode ? 'Editar evento' : 'Crear evento' }}
    </h1>
    <p class="mt-1 text-sm text-slate-600">
      {{
        isEditMode
          ? 'Actualiza la información del evento y su imagen principal.'
          : 'Completa los datos para publicar un nuevo evento.'
      }}
    </p>

    <div
      v-if="isLoadingEvent"
      data-testid="event-form-loading"
      class="mt-6"
    >
      <BaseSkeleton :lines="6" />
    </div>

    <EventForm
      v-else-if="!isEditMode || store.currentEvent"
      class="mt-6"
      :initial-event="store.currentEvent"
      :is-submitting="store.isSubmitting"
      :field-errors="fieldErrors"
      :error-message="errorMessage"
      @submit="handleSubmit"
      @cancel="handleCancel"
    />

    <div v-else data-testid="event-form-error" class="mt-6">
      <BaseAlert
        type="error"
        :message="errorMessage || 'Evento no encontrado'"
      />
    </div>
  </main>
</template>
