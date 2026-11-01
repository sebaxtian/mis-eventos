<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import type { EventRead, EventStatus } from '@/types/api'

const props = defineProps<{ event: EventRead }>()

const STATUS_LABELS: Record<EventStatus, string> = {
  DRAFT: 'Borrador',
  PUBLISHED: 'Publicado',
  CANCELLED: 'Cancelado',
}

const statusLabel = computed(() => STATUS_LABELS[props.event.status])

const formattedDate = computed(() =>
  new Intl.DateTimeFormat('es-CO', {
    dateStyle: 'long',
    timeStyle: 'short',
    timeZone: 'UTC',
  }).format(new Date(props.event.date)),
)

const imageSrcSet = computed(() => {
  const urls = props.event.image_urls
  if (!urls) return ''
  return `${urls.w400} 400w, ${urls.w800} 800w, ${urls.w1200} 1200w`
})
</script>

<template>
  <article
    data-testid="event-card"
    class="flex h-full flex-col overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm transition hover:shadow-md"
  >
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
      class="h-44 w-full object-cover"
    />
    <div
      v-else
      data-testid="event-image-placeholder"
      class="flex h-44 w-full items-center justify-center bg-slate-100 text-sm text-slate-500"
    >
      Sin imagen disponible
    </div>

    <div class="flex flex-1 flex-col gap-3 p-4">
      <div class="flex items-start justify-between gap-2">
        <h2 class="text-base font-semibold text-slate-900">
          {{ event.title }}
        </h2>
        <span
          class="shrink-0 rounded-full px-2 py-1 text-xs font-medium"
          :class="{
            'bg-amber-100 text-amber-800': event.status === 'DRAFT',
            'bg-emerald-100 text-emerald-800': event.status === 'PUBLISHED',
            'bg-red-100 text-red-800': event.status === 'CANCELLED',
          }"
        >
          {{ statusLabel }}
        </span>
      </div>

      <p class="text-sm text-slate-600">{{ formattedDate }}</p>

      <p class="text-sm text-slate-700">
        Cupos disponibles:
        <span class="font-semibold text-slate-900">
          {{ event.available_capacity }}
        </span>
        de {{ event.total_capacity }}
      </p>

      <RouterLink
        :to="{ name: 'event-detail', params: { id: event.id } }"
        class="mt-auto inline-flex items-center text-sm font-medium text-indigo-600 hover:underline"
      >
        Ver detalle
      </RouterLink>
    </div>
  </article>
</template>
