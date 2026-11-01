<script setup lang="ts">
import { computed } from 'vue'
import type { SessionRead } from '@/types/api'

const props = defineProps<{
  sessions: SessionRead[]
}>()

defineSlots<{
  actions?: (props: { session: SessionRead }) => any
}>()

const timeFormatter = new Intl.DateTimeFormat('es-CO', {
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
  timeZone: 'UTC',
})

function formatTime(isoDate: string): string {
  const parsed = new Date(isoDate)
  if (Number.isNaN(parsed.getTime())) return ''
  return timeFormatter.format(parsed)
}

const orderedSessions = computed(() =>
  [...props.sessions].sort(
    (first, second) =>
      first.start_time.localeCompare(second.start_time) ||
      first.id - second.id,
  ),
)
</script>

<template>
  <div>
    <p
      v-if="orderedSessions.length === 0"
      data-testid="sessions-empty"
      class="rounded-lg border border-dashed border-slate-300 bg-white p-4 text-sm text-slate-600"
    >
      Este evento todavía no tiene sesiones programadas.
    </p>

    <ol v-else class="flex flex-col gap-4">
      <li
        v-for="session in orderedSessions"
        :key="session.id"
        data-testid="session-item"
        class="rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
      >
        <div class="flex flex-wrap items-start justify-between gap-2">
          <div>
            <p class="text-sm font-semibold text-slate-900">
              {{ session.title }}
            </p>
            <p class="text-xs text-slate-600">
              {{ formatTime(session.start_time) }} –
              {{ formatTime(session.end_time) }} UTC
            </p>
          </div>
          <span
            class="rounded-full bg-indigo-50 px-3 py-1 text-xs font-medium text-indigo-700"
          >
            {{ session.available_capacity }} de {{ session.capacity }} cupos
            disponibles
          </span>
        </div>

        <p class="mt-2 text-sm text-slate-700">
          <span class="font-medium">Ponente:</span> {{ session.speaker }}
        </p>
        <p
          v-if="session.description"
          class="mt-1 whitespace-pre-line text-sm text-slate-600"
        >
          {{ session.description }}
        </p>

        <div v-if="$slots.actions" class="mt-3 flex flex-wrap gap-2">
          <slot name="actions" :session="session" />
        </div>
      </li>
    </ol>
  </div>
</template>
