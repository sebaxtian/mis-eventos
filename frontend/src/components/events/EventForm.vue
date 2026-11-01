<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import BaseAlert from '@/components/base/BaseAlert.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseInput from '@/components/base/BaseInput.vue'
import type {
  EventCreatePayload,
  EventRead,
  EventStatus,
  EventUpdatePayload,
} from '@/types/api'

const props = withDefaults(
  defineProps<{
    initialEvent?: EventRead | null
    isSubmitting?: boolean
    fieldErrors?: Record<string, string>
    errorMessage?: string
  }>(),
  {
    initialEvent: null,
    isSubmitting: false,
    fieldErrors: () => ({}),
    errorMessage: '',
  },
)

const emit = defineEmits<{
  submit: [payload: EventCreatePayload | EventUpdatePayload, file: File | null]
  cancel: []
}>()

const title = ref('')
const description = ref('')
const date = ref('')
const capacity = ref('')
const status = ref<EventStatus>('DRAFT')
const selectedFile = ref<File | null>(null)
const clientErrors = reactive<Record<string, string>>({})

const isCancelled = computed(
  () => props.initialEvent?.status === 'CANCELLED',
)

const availableStatuses = computed<EventStatus[]>(() => {
  const currentStatus = props.initialEvent?.status
  if (currentStatus === 'CANCELLED') return ['CANCELLED']
  if (currentStatus === 'PUBLISHED') return ['PUBLISHED']
  return ['DRAFT', 'PUBLISHED']
})

const fieldErrors = computed<Record<string, string>>(() => ({
  ...props.fieldErrors,
  ...clientErrors,
}))

function toDateTimeLocal(isoDate: string): string {
  const parsed = new Date(isoDate)
  if (Number.isNaN(parsed.getTime())) return ''
  const pad = (value: number): string => String(value).padStart(2, '0')
  return `${parsed.getFullYear()}-${pad(parsed.getMonth() + 1)}-${pad(
    parsed.getDate(),
  )}T${pad(parsed.getHours())}:${pad(parsed.getMinutes())}`
}

function applyInitialEvent(event: EventRead | null): void {
  title.value = event?.title ?? ''
  description.value = event?.description ?? ''
  date.value = event ? toDateTimeLocal(event.date) : ''
  capacity.value = event ? String(event.total_capacity) : ''
  status.value = event?.status ?? 'DRAFT'
}

watch(
  () => props.initialEvent,
  (event) => applyInitialEvent(event ?? null),
  { immediate: true },
)

function clearClientError(field: string): void {
  delete clientErrors[field]
}

function onTitleInput(value: string): void {
  title.value = value
  clearClientError('title')
}

function onDescriptionInput(event: Event): void {
  description.value = (event.target as HTMLTextAreaElement).value
  clearClientError('description')
}

function onDateInput(value: string): void {
  date.value = value
  clearClientError('date')
}

function onCapacityInput(value: string): void {
  capacity.value = value
  clearClientError('total_capacity')
}

function onFileChange(event: Event): void {
  const target = event.target as HTMLInputElement
  selectedFile.value = target.files?.[0] ?? null
}

function validate(): boolean {
  for (const key of Object.keys(clientErrors)) {
    delete clientErrors[key]
  }

  const trimmedTitle = title.value.trim()
  if (trimmedTitle.length < 3 || trimmedTitle.length > 160) {
    clientErrors.title = 'El título debe tener entre 3 y 160 caracteres'
  }

  const trimmedDescription = description.value.trim()
  if (
    trimmedDescription.length < 10 ||
    trimmedDescription.length > 5000
  ) {
    clientErrors.description =
      'La descripción debe tener entre 10 y 5000 caracteres'
  }

  if (!date.value || Number.isNaN(new Date(date.value).getTime())) {
    clientErrors.date = 'Debes indicar una fecha válida'
  }

  const numericCapacity = Number(capacity.value)
  if (
    !Number.isInteger(numericCapacity) ||
    numericCapacity < 1 ||
    numericCapacity > 100000
  ) {
    clientErrors.total_capacity =
      'La capacidad total debe estar entre 1 y 100000'
  }

  return Object.keys(clientErrors).length === 0
}

function onSubmit(): void {
  if (isCancelled.value || props.isSubmitting) return
  if (!validate()) return

  const payload: EventCreatePayload | EventUpdatePayload = {
    title: title.value.trim(),
    description: description.value.trim(),
    date: new Date(date.value).toISOString(),
    total_capacity: Number(capacity.value),
    status: status.value,
  }

  emit('submit', payload, selectedFile.value)
}
</script>

<template>
  <form
    data-testid="event-form"
    class="flex flex-col gap-4"
    novalidate
    @submit.prevent="onSubmit"
  >
    <BaseAlert
      v-if="isCancelled"
      type="warning"
      message="Un evento cancelado no puede cambiar de estado ni editarse"
    />
    <BaseAlert v-if="errorMessage" type="error" :message="errorMessage" />

    <BaseInput
      id="event-title"
      :model-value="title"
      label="Título"
      placeholder="Nombre del evento"
      :error="fieldErrors.title"
      :disabled="isCancelled"
      required
      @update:model-value="onTitleInput"
    />

    <div class="flex flex-col gap-1">
      <label
        for="event-description"
        class="text-sm font-medium text-slate-700"
      >
        Descripción
        <span class="text-red-600">*</span>
      </label>
      <textarea
        id="event-description"
        :value="description"
        :disabled="isCancelled"
        rows="4"
        placeholder="Describe el evento, su temática y a quién está dirigido"
        class="rounded-md border px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2"
        :class="
          fieldErrors.description
            ? 'border-red-500 focus:ring-red-500'
            : 'border-slate-300 focus:ring-indigo-500'
        "
        :aria-invalid="fieldErrors.description ? 'true' : 'false'"
        :aria-describedby="
          fieldErrors.description ? 'event-description-error' : undefined
        "
        @input="onDescriptionInput"
      />
      <p
        v-if="fieldErrors.description"
        id="event-description-error"
        role="alert"
        class="text-xs text-red-600"
      >
        {{ fieldErrors.description }}
      </p>
    </div>

    <BaseInput
      id="event-date"
      :model-value="date"
      type="datetime-local"
      label="Fecha y hora (UTC)"
      :error="fieldErrors.date"
      :disabled="isCancelled"
      required
      @update:model-value="onDateInput"
    />

    <BaseInput
      id="event-capacity"
      :model-value="capacity"
      type="number"
      label="Capacidad total"
      placeholder="100"
      :error="fieldErrors.total_capacity"
      :disabled="isCancelled"
      required
      @update:model-value="onCapacityInput"
    />

    <div class="flex flex-col gap-1">
      <label for="event-status" class="text-sm font-medium text-slate-700">
        Estado
      </label>
      <select
        id="event-status"
        v-model="status"
        :disabled="isCancelled"
        class="rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-60"
      >
        <option
          v-for="option in availableStatuses"
          :key="option"
          :value="option"
        >
          {{
            option === 'DRAFT'
              ? 'Borrador'
              : option === 'PUBLISHED'
                ? 'Publicado'
                : 'Cancelado'
          }}
        </option>
      </select>
    </div>

    <div class="flex flex-col gap-1">
      <label for="event-image" class="text-sm font-medium text-slate-700">
        Imagen del evento (opcional)
      </label>
      <input
        id="event-image"
        type="file"
        accept="image/jpeg,image/png,image/webp"
        :disabled="isCancelled"
        class="text-sm text-slate-700 file:mr-3 file:rounded-md file:border-0 file:bg-slate-200 file:px-3 file:py-2 file:text-sm file:font-medium"
        @change="onFileChange"
      />
      <p class="text-xs text-slate-500">
        JPEG, PNG o WebP de hasta 5 MB. Se generarán variantes WebP
        responsivas.
      </p>
      <p v-if="selectedFile" class="text-xs text-slate-600">
        Archivo seleccionado: {{ selectedFile.name }}
      </p>
    </div>

    <div class="flex justify-end gap-3">
      <BaseButton type="button" variant="secondary" @click="emit('cancel')">
        Cancelar
      </BaseButton>
      <BaseButton
        type="submit"
        data-testid="event-submit"
        :is-loading="isSubmitting"
        :disabled="isCancelled"
      >
        Guardar evento
      </BaseButton>
    </div>
  </form>
</template>
