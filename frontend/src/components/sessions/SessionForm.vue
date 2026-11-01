<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import BaseAlert from '@/components/base/BaseAlert.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseInput from '@/components/base/BaseInput.vue'
import type {
  SessionCreatePayload,
  SessionRead,
  SessionUpdatePayload,
  ValidationFieldError,
} from '@/types/api'

const props = withDefaults(
  defineProps<{
    eventId: number
    session?: SessionRead | null
    disabled?: boolean
    isSubmitting?: boolean
    fieldErrors?: ValidationFieldError[]
    errorMessage?: string
  }>(),
  {
    session: null,
    disabled: false,
    isSubmitting: false,
    fieldErrors: () => [],
    errorMessage: '',
  },
)

const emit = defineEmits<{
  submit: [payload: SessionCreatePayload | SessionUpdatePayload]
  cancel: []
}>()

const title = ref('')
const speaker = ref('')
const description = ref('')
const startTime = ref('')
const endTime = ref('')
const capacity = ref('')
const clientErrors = reactive<Record<string, string>>({})

function toDateTimeLocal(isoDate: string): string {
  const parsed = new Date(isoDate)
  if (Number.isNaN(parsed.getTime())) return ''
  const pad = (value: number): string => String(value).padStart(2, '0')
  return `${parsed.getFullYear()}-${pad(parsed.getMonth() + 1)}-${pad(
    parsed.getDate(),
  )}T${pad(parsed.getHours())}:${pad(parsed.getMinutes())}`
}

function toIsoUtc(value: string): string {
  return new Date(value).toISOString()
}

function applySession(session: SessionRead | null): void {
  title.value = session?.title ?? ''
  speaker.value = session?.speaker ?? ''
  description.value = session?.description ?? ''
  startTime.value = session ? toDateTimeLocal(session.start_time) : ''
  endTime.value = session ? toDateTimeLocal(session.end_time) : ''
  capacity.value = session ? String(session.capacity) : ''
}

watch(
  () => props.session,
  (session) => applySession(session ?? null),
  { immediate: true },
)

const apiFieldErrors = computed<Record<string, string>>(() => {
  const mapped: Record<string, string> = {}
  for (const error of props.fieldErrors) {
    if (!(error.field in mapped)) {
      mapped[error.field] = error.message
    }
  }
  return mapped
})

function fieldError(name: string): string {
  return clientErrors[name] ?? apiFieldErrors.value[name] ?? ''
}

function clearClientError(name: string): void {
  delete clientErrors[name]
}

function onTitleInput(value: string): void {
  title.value = value
  clearClientError('title')
}

function onSpeakerInput(value: string): void {
  speaker.value = value
  clearClientError('speaker')
}

function onDescriptionInput(event: Event): void {
  description.value = (event.target as HTMLTextAreaElement).value
  clearClientError('description')
}

function onStartTimeInput(value: string): void {
  startTime.value = value
  clearClientError('start_time')
}

function onEndTimeInput(value: string): void {
  endTime.value = value
  clearClientError('end_time')
}

function onCapacityInput(value: string): void {
  capacity.value = value
  clearClientError('capacity')
}

function validate(): boolean {
  for (const key of Object.keys(clientErrors)) {
    delete clientErrors[key]
  }

  const trimmedTitle = title.value.trim()
  if (trimmedTitle.length < 3 || trimmedTitle.length > 160) {
    clientErrors.title = 'El título debe tener entre 3 y 160 caracteres'
  }

  const trimmedSpeaker = speaker.value.trim()
  if (trimmedSpeaker.length < 2 || trimmedSpeaker.length > 120) {
    clientErrors.speaker = 'El ponente debe tener entre 2 y 120 caracteres'
  }

  if (description.value.trim().length > 2000) {
    clientErrors.description =
      'La descripción no debe superar los 2000 caracteres'
  }

  const parsedStart = startTime.value
    ? new Date(startTime.value).getTime()
    : Number.NaN
  if (Number.isNaN(parsedStart)) {
    clientErrors.start_time = 'Debes indicar una fecha y hora válida'
  }

  const parsedEnd = endTime.value
    ? new Date(endTime.value).getTime()
    : Number.NaN
  if (Number.isNaN(parsedEnd)) {
    clientErrors.end_time = 'Debes indicar una fecha y hora válida'
  }

  if (
    !Number.isNaN(parsedStart) &&
    !Number.isNaN(parsedEnd) &&
    parsedStart >= parsedEnd
  ) {
    clientErrors.start_time =
      'La hora de inicio debe ser anterior a la hora de fin'
  }

  const numericCapacity = Number(capacity.value)
  if (
    !Number.isInteger(numericCapacity) ||
    numericCapacity < 1 ||
    numericCapacity > 100000
  ) {
    clientErrors.capacity =
      'La capacidad de la sesión debe estar entre 1 y 100000'
  }

  return Object.keys(clientErrors).length === 0
}

function onSubmit(): void {
  if (props.disabled || props.isSubmitting) return
  if (!validate()) return

  const trimmedDescription = description.value.trim()
  const payload: SessionCreatePayload = {
    title: title.value.trim(),
    speaker: speaker.value.trim(),
    description: trimmedDescription ? trimmedDescription : null,
    start_time: toIsoUtc(startTime.value),
    end_time: toIsoUtc(endTime.value),
    capacity: Number(capacity.value),
  }
  emit('submit', payload)
}
</script>

<template>
  <form
    data-testid="session-form"
    class="flex flex-col gap-4 rounded-lg border border-slate-200 bg-slate-50 p-4"
    novalidate
    @submit.prevent="onSubmit"
  >
    <BaseAlert v-if="errorMessage" type="error" :message="errorMessage" />

    <BaseInput
      id="session-title"
      :model-value="title"
      label="Título de la sesión"
      placeholder="Apertura y bienvenida"
      :error="fieldError('title')"
      :disabled="disabled"
      required
      @update:model-value="onTitleInput"
    />

    <BaseInput
      id="session-speaker"
      :model-value="speaker"
      label="Ponente"
      placeholder="Ana Torres"
      :error="fieldError('speaker')"
      :disabled="disabled"
      required
      @update:model-value="onSpeakerInput"
    />

    <div class="flex flex-col gap-1">
      <label
        for="session-description"
        class="text-sm font-medium text-slate-700"
      >
        Descripción (opcional)
      </label>
      <textarea
        id="session-description"
        :value="description"
        :disabled="disabled"
        rows="3"
        placeholder="Describe el contenido de la sesión"
        class="rounded-md border px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2"
        :class="
          fieldError('description')
            ? 'border-red-500 focus:ring-red-500'
            : 'border-slate-300 focus:ring-indigo-500'
        "
        :aria-invalid="fieldError('description') ? 'true' : 'false'"
        :aria-describedby="
          fieldError('description') ? 'session-description-error' : undefined
        "
        @input="onDescriptionInput"
      />
      <p
        v-if="fieldError('description')"
        id="session-description-error"
        role="alert"
        class="text-xs text-red-600"
      >
        {{ fieldError('description') }}
      </p>
    </div>

    <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
      <BaseInput
        id="session-start-time"
        :model-value="startTime"
        type="datetime-local"
        label="Inicio (hora local)"
        :error="fieldError('start_time')"
        :disabled="disabled"
        required
        @update:model-value="onStartTimeInput"
      />

      <BaseInput
        id="session-end-time"
        :model-value="endTime"
        type="datetime-local"
        label="Fin (hora local)"
        :error="fieldError('end_time')"
        :disabled="disabled"
        required
        @update:model-value="onEndTimeInput"
      />
    </div>

    <BaseInput
      id="session-capacity"
      :model-value="capacity"
      type="number"
      label="Capacidad de la sesión"
      placeholder="40"
      :error="fieldError('capacity')"
      :disabled="disabled"
      required
      @update:model-value="onCapacityInput"
    />

    <div class="flex justify-end gap-3">
      <BaseButton
        type="button"
        variant="secondary"
        :disabled="disabled"
        @click="emit('cancel')"
      >
        Cancelar
      </BaseButton>
      <BaseButton
        type="submit"
        data-testid="session-submit"
        :is-loading="isSubmitting"
        :disabled="disabled"
      >
        Guardar sesión
      </BaseButton>
    </div>
  </form>
</template>
