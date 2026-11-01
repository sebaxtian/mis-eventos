<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import BaseAlert from '@/components/base/BaseAlert.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseSkeleton from '@/components/base/BaseSkeleton.vue'
import { useRegistrationStore } from '@/stores/registrations'
import type { RegistrationStatus } from '@/types/api'

const props = defineProps<{
  eventId: number
  canManage: boolean
}>()

const store = useRegistrationStore()
const statusFilter = ref<RegistrationStatus | ''>('')

const STATUS_LABELS: Record<RegistrationStatus, string> = {
  ACTIVE: 'Activa',
  CANCELLED: 'Cancelada',
}

const dateFormatter = new Intl.DateTimeFormat('es-CO', {
  dateStyle: 'medium',
  timeStyle: 'short',
  timeZone: 'UTC',
})

function formatDate(isoDate: string): string {
  const parsed = new Date(isoDate)
  if (Number.isNaN(parsed.getTime())) return ''
  return dateFormatter.format(parsed)
}

async function load(page = 1): Promise<void> {
  if (!props.canManage) return
  await store.fetchEventRegistrations(props.eventId, {
    page,
    size: 10,
    status: statusFilter.value,
  })
}

function onFilterChange(): void {
  void load(1)
}

function goToPreviousPage(): void {
  if (store.page <= 1) return
  void load(store.page - 1)
}

function goToNextPage(): void {
  if (store.page >= store.pages) return
  void load(store.page + 1)
}

onMounted(() => {
  void load(1)
})

watch(
  () => props.eventId,
  () => {
    statusFilter.value = ''
    void load(1)
  },
)
</script>

<template>
  <section
    v-if="canManage"
    data-testid="event-registrations"
    class="rounded-lg border border-slate-200 bg-white p-5 shadow-sm"
  >
    <div class="flex flex-wrap items-center justify-between gap-3">
      <h2 class="text-lg font-semibold text-slate-900">
        Inscripciones al evento
      </h2>
      <div class="flex items-center gap-2">
        <label
          for="event-registrations-status-filter"
          class="text-xs font-semibold uppercase tracking-wide text-slate-500"
        >
          Estado
        </label>
        <select
          id="event-registrations-status-filter"
          v-model="statusFilter"
          data-testid="event-registrations-status-filter"
          class="rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-800"
          @change="onFilterChange"
        >
          <option value="">Todas</option>
          <option value="ACTIVE">Activas</option>
          <option value="CANCELLED">Canceladas</option>
        </select>
      </div>
    </div>

    <div
      v-if="store.isLoading"
      data-testid="event-registrations-loading"
      class="mt-3"
    >
      <BaseSkeleton :lines="3" />
    </div>

    <div
      v-else-if="store.errorMessage"
      data-testid="event-registrations-error"
      class="mt-3 flex flex-col gap-2"
    >
      <BaseAlert type="error" :message="store.errorMessage" />
      <div>
        <BaseButton
          type="button"
          variant="secondary"
          data-testid="event-registrations-retry"
          @click="load(1)"
        >
          Reintentar
        </BaseButton>
      </div>
    </div>

    <p
      v-else-if="store.items.length === 0"
      data-testid="event-registrations-empty"
      class="mt-3 rounded-lg border border-dashed border-slate-300 bg-white p-4 text-sm text-slate-600"
    >
      Todavía no hay inscripciones a este evento.
    </p>

    <div v-else class="mt-3 overflow-x-auto">
      <table class="min-w-full text-left text-sm text-slate-700">
        <thead>
          <tr class="border-b border-slate-200 text-xs uppercase text-slate-500">
            <th class="py-2 pr-4 font-semibold">Usuario</th>
            <th class="py-2 pr-4 font-semibold">Estado</th>
            <th class="py-2 font-semibold">Fecha de inscripción</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="registration in store.items"
            :key="registration.id"
            data-testid="event-registration-row"
            class="border-b border-slate-100"
          >
            <td class="py-2 pr-4">Usuario #{{ registration.user_id }}</td>
            <td class="py-2 pr-4">
              {{ STATUS_LABELS[registration.status] }}
            </td>
            <td class="py-2">
              {{ formatDate(registration.created_at) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div
      v-if="store.pages > 0"
      class="mt-3 flex items-center justify-between gap-2"
    >
      <BaseButton
        type="button"
        variant="secondary"
        data-testid="event-registrations-prev"
        :disabled="store.page <= 1"
        @click="goToPreviousPage"
      >
        Anterior
      </BaseButton>
      <p
        data-testid="event-registrations-page"
        class="text-xs text-slate-600"
      >
        Página {{ store.page }} de {{ store.pages }}
      </p>
      <BaseButton
        type="button"
        variant="secondary"
        data-testid="event-registrations-next"
        :disabled="store.page >= store.pages"
        @click="goToNextPage"
      >
        Siguiente
      </BaseButton>
    </div>
  </section>
</template>
