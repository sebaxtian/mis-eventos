<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import BaseAlert from '@/components/base/BaseAlert.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseSkeleton from '@/components/base/BaseSkeleton.vue'
import { useAuthStore } from '@/stores/auth'
import { useEventStore } from '@/stores/events'
import type { EventStatus } from '@/types/api'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const store = useEventStore()

const invalidId = ref(false)
const imageInputRef = ref<HTMLInputElement | null>(null)
const selectedImage = ref<File | null>(null)
const imageFeedback = ref('')
const imageFeedbackType = ref<'success' | 'error'>('success')

const event = computed(() => store.currentEvent)

const canManage = computed(() => {
  if (!event.value) return false
  if (authStore.role === 'ADMIN') return true
  return (
    authStore.role === 'ORGANIZER' &&
    authStore.user?.id === event.value.organizer_id
  )
})

const isCancelled = computed(() => event.value?.status === 'CANCELLED')

const isAttendeeOrAnonymous = computed(
  () => authStore.role === null || authStore.role === 'ATTENDEE',
)

const STATUS_LABELS: Record<EventStatus, string> = {
  DRAFT: 'Borrador',
  PUBLISHED: 'Publicado',
  CANCELLED: 'Cancelado',
}

const statusLabel = computed(() =>
  event.value ? STATUS_LABELS[event.value.status] : '',
)

const formattedDate = computed(() => {
  if (!event.value) return ''
  return new Intl.DateTimeFormat('es-CO', {
    dateStyle: 'long',
    timeStyle: 'short',
    timeZone: 'UTC',
  }).format(new Date(event.value.date))
})

const imageSrcSet = computed(() => {
  const urls = event.value?.image_urls
  if (!urls) return ''
  return `${urls.w400} 400w, ${urls.w800} 800w, ${urls.w1200} 1200w`
})

const notFoundMessage = computed(() =>
  invalidId.value ? 'Evento no encontrado' : store.errorMessage,
)

function onImageSelected(event: Event): void {
  const target = event.target as HTMLInputElement
  selectedImage.value = target.files?.[0] ?? null
  imageFeedback.value = ''
}

async function handleImageUpload(): Promise<void> {
  if (!event.value || !selectedImage.value) return
  imageFeedback.value = ''
  try {
    await store.uploadEventImage(event.value.id, selectedImage.value)
    imageFeedbackType.value = 'success'
    imageFeedback.value = 'Imagen actualizada correctamente.'
    selectedImage.value = null
    if (imageInputRef.value) {
      imageInputRef.value.value = ''
    }
  } catch {
    imageFeedbackType.value = 'error'
    imageFeedback.value =
      store.errorMessage || 'No se pudo subir la imagen del evento'
  }
}

async function handlePublish(): Promise<void> {
  if (!event.value) return
  try {
    await store.updateEvent(event.value.id, { status: 'PUBLISHED' })
  } catch {
    // The store exposes the Spanish error message through errorMessage.
  }
}

async function handleCancel(): Promise<void> {
  if (!event.value) return
  if (
    !window.confirm(
      '¿Seguro que deseas cancelar este evento? Esta acción no se puede revertir.',
    )
  ) {
    return
  }
  try {
    await store.updateEvent(event.value.id, { status: 'CANCELLED' })
  } catch {
    // The store exposes the Spanish error message through errorMessage.
  }
}

async function handleDelete(): Promise<void> {
  if (!event.value) return
  if (!window.confirm('¿Seguro que deseas eliminar este evento?')) {
    return
  }
  try {
    await store.deleteEvent(event.value.id)
    await router.push({ name: 'home' })
  } catch {
    // The store exposes the Spanish error message through errorMessage.
  }
}

onMounted(async () => {
  store.clearCurrentEvent()
  const parsedId = Number(route.params.id)
  if (!Number.isInteger(parsedId) || parsedId <= 0) {
    invalidId.value = true
    return
  }
  await store.fetchEventById(parsedId)
})
</script>

<template>
  <main class="mx-auto max-w-4xl p-6">
    <RouterLink
      to="/"
      class="text-sm font-medium text-indigo-600 hover:underline"
    >
      ← Volver al catálogo
    </RouterLink>

    <div v-if="store.isLoading" data-testid="detail-loading" class="mt-6">
      <BaseSkeleton :lines="6" />
    </div>

    <div
      v-else-if="!event && notFoundMessage"
      data-testid="event-detail-error"
      class="mt-6 flex flex-col gap-4"
    >
      <BaseAlert type="error" :message="notFoundMessage" />
    </div>

    <article v-else-if="event" class="mt-6 flex flex-col gap-6">
      <BaseAlert
        v-if="store.errorMessage && !imageFeedback"
        type="error"
        :message="store.errorMessage"
      />

      <header class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 class="text-2xl font-bold text-slate-900">
            {{ event.title }}
          </h1>
          <p class="mt-1 text-sm text-slate-600">{{ formattedDate }}</p>
        </div>
        <span
          class="rounded-full px-3 py-1 text-xs font-medium"
          :class="{
            'bg-amber-100 text-amber-800': event.status === 'DRAFT',
            'bg-emerald-100 text-emerald-800':
              event.status === 'PUBLISHED',
            'bg-red-100 text-red-800': event.status === 'CANCELLED',
          }"
        >
          {{ statusLabel }}
        </span>
      </header>

      <img
        v-if="event.image_urls"
        :src="event.image_urls.w800"
        :srcset="imageSrcSet"
        sizes="(max-width: 640px) 400px, (max-width: 1024px) 800px, 1200px"
        :alt="event.title"
        width="800"
        height="450"
        loading="lazy"
        decoding="async"
        class="w-full rounded-lg object-cover"
      />
      <div
        v-else
        data-testid="detail-image-placeholder"
        class="flex h-48 w-full items-center justify-center rounded-lg bg-slate-100 text-sm text-slate-500"
      >
        Sin imagen disponible
      </div>

      <section class="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
        <h2 class="text-lg font-semibold text-slate-900">Descripción</h2>
        <p class="mt-2 whitespace-pre-line text-sm text-slate-700">
          {{ event.description }}
        </p>
      </section>

      <section class="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div class="rounded-lg border border-slate-200 bg-white p-4">
          <p class="text-xs font-semibold uppercase text-slate-500">
            Cupos disponibles
          </p>
          <p class="mt-1 text-lg font-semibold text-slate-900">
            {{ event.available_capacity }} de {{ event.total_capacity }}
          </p>
        </div>
        <div class="rounded-lg border border-slate-200 bg-white p-4">
          <p class="text-xs font-semibold uppercase text-slate-500">
            Inscritos
          </p>
          <p class="mt-1 text-lg font-semibold text-slate-900">
            {{ event.registered_count }}
          </p>
        </div>
        <div class="rounded-lg border border-slate-200 bg-white p-4">
          <p class="text-xs font-semibold uppercase text-slate-500">
            Organizador
          </p>
          <p class="mt-1 text-lg font-semibold text-slate-900">
            Organizador #{{ event.organizer_id }}
          </p>
        </div>
      </section>

      <section
        v-if="canManage"
        class="flex flex-wrap gap-3 rounded-lg border border-slate-200 bg-white p-4"
      >
        <RouterLink
          v-if="!isCancelled"
          :to="{ name: 'event-edit', params: { id: event.id } }"
          data-testid="event-edit-link"
          class="inline-flex items-center rounded-md bg-slate-200 px-4 py-2 text-sm font-medium text-slate-800 hover:bg-slate-300"
        >
          Editar
        </RouterLink>
        <BaseButton
          v-if="event.status === 'DRAFT'"
          type="button"
          data-testid="event-publish-button"
          @click="handlePublish"
        >
          Publicar
        </BaseButton>
        <BaseButton
          v-if="!isCancelled"
          type="button"
          variant="secondary"
          data-testid="event-cancel-button"
          @click="handleCancel"
        >
          Cancelar evento
        </BaseButton>
        <BaseButton
          v-if="event.registered_count === 0"
          type="button"
          variant="danger"
          data-testid="event-delete-button"
          @click="handleDelete"
        >
          Eliminar
        </BaseButton>

        <div
          v-if="!isCancelled"
          data-testid="event-image-upload-block"
          class="flex w-full flex-col gap-2 border-t border-slate-200 pt-3"
        >
          <label
            for="event-image-upload"
            class="text-xs font-semibold text-slate-600"
          >
            Actualizar imagen
          </label>
          <div class="flex flex-wrap items-center gap-3">
            <input
              id="event-image-upload"
              ref="imageInputRef"
              type="file"
              accept="image/jpeg,image/png,image/webp"
              class="text-sm text-slate-700 file:mr-3 file:rounded-md file:border-0 file:bg-slate-200 file:px-3 file:py-2 file:text-sm file:font-medium"
              @change="onImageSelected"
            />
            <BaseButton
              type="button"
              data-testid="event-image-submit"
              :is-loading="store.isSubmitting"
              @click="handleImageUpload"
            >
              Actualizar imagen
            </BaseButton>
          </div>
        </div>

        <BaseAlert
          v-if="imageFeedback"
          :type="imageFeedbackType"
          :message="imageFeedback"
          class="w-full"
        />
      </section>

      <section
        v-if="isAttendeeOrAnonymous"
        data-testid="registration-placeholder"
        class="rounded-lg border border-dashed border-slate-300 bg-white p-4 text-sm text-slate-600"
      >
        Las inscripciones estarán disponibles próximamente.
      </section>
    </article>
  </main>
</template>
