<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import BaseAlert from '@/components/base/BaseAlert.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseSkeleton from '@/components/base/BaseSkeleton.vue'
import EventCard from '@/components/events/EventCard.vue'
import { useAuthStore } from '@/stores/auth'
import { useEventStore } from '@/stores/events'
import type { EventStatus } from '@/types/api'

const store = useEventStore()
const authStore = useAuthStore()

const canManage = computed(
  () => authStore.role === 'ORGANIZER' || authStore.role === 'ADMIN',
)

const STATUS_OPTIONS: Array<{ value: EventStatus; label: string }> = [
  { value: 'DRAFT', label: 'Borrador' },
  { value: 'PUBLISHED', label: 'Publicado' },
  { value: 'CANCELLED', label: 'Cancelado' },
]

async function onSearchSubmit(): Promise<void> {
  await store.fetchEvents({ page: 1, search: store.search })
}

async function onFiltersChanged(): Promise<void> {
  await store.fetchEvents({ page: 1 })
}

async function changePage(nextPage: number): Promise<void> {
  if (nextPage < 1 || (store.pages > 0 && nextPage > store.pages)) return
  await store.fetchEvents({ page: nextPage })
}

onMounted(() => {
  void store.fetchEvents()
})
</script>

<template>
  <main class="mx-auto max-w-5xl p-6">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="text-2xl font-bold text-slate-900">Eventos</h1>
        <p class="mt-1 text-sm text-slate-600">
          Explora el catálogo y encuentra tu próximo evento.
        </p>
      </div>
      <RouterLink
        v-if="canManage"
        :to="{ name: 'event-create' }"
        data-testid="event-create-link"
        class="inline-flex items-center rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
      >
        Crear evento
      </RouterLink>
    </div>

    <BaseAlert
      v-if="store.errorMessage"
      type="error"
      :message="store.errorMessage"
      class="mt-4"
    />

    <section class="mt-6 flex flex-wrap items-end gap-4 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <form
        data-testid="event-search-form"
        class="flex flex-1 flex-wrap items-end gap-2"
        @submit.prevent="onSearchSubmit"
      >
        <div class="flex min-w-[220px] flex-1 flex-col gap-1">
          <label
            for="event-search"
            class="text-xs font-semibold text-slate-600"
          >
            Buscar por nombre
          </label>
          <input
            id="event-search"
            v-model="store.search"
            type="search"
            placeholder="Ej. Python, Vue, conferencia..."
            maxlength="100"
            class="rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        <BaseButton type="submit">Buscar</BaseButton>
      </form>

      <template v-if="canManage">
        <div class="flex flex-col gap-1">
          <label
            for="event-status-filter"
            class="text-xs font-semibold text-slate-600"
          >
            Estado
          </label>
          <select
            id="event-status-filter"
            v-model="store.statusFilter"
            class="rounded-md border border-slate-300 px-3 py-2 text-sm"
            @change="onFiltersChanged"
          >
            <option value="">Todos los estados</option>
            <option
              v-for="option in STATUS_OPTIONS"
              :key="option.value"
              :value="option.value"
            >
              {{ option.label }}
            </option>
          </select>
        </div>

        <label
          class="flex items-center gap-2 pb-2 text-sm font-medium text-slate-700"
        >
          <input
            id="event-mine-filter"
            v-model="store.mineOnly"
            type="checkbox"
            class="h-4 w-4 rounded border-slate-300 text-indigo-600"
            @change="onFiltersChanged"
          />
          Mis eventos
        </label>
      </template>
    </section>

    <div v-if="store.isLoading" data-testid="events-loading" class="mt-6">
      <BaseSkeleton :lines="6" />
    </div>

    <div
      v-else-if="!store.hasEvents"
      data-testid="events-empty"
      class="mt-6 rounded-lg border border-slate-200 bg-white p-6 text-center text-sm text-slate-600"
    >
      No hay eventos disponibles con los criterios seleccionados.
    </div>

    <div
      v-else
      data-testid="events-grid"
      class="mt-6 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3"
    >
      <EventCard
        v-for="event in store.items"
        :key="event.id"
        :event="event"
      />
    </div>

    <div
      v-if="store.pages > 1"
      class="mt-6 flex flex-wrap items-center justify-between gap-3 text-sm text-slate-600"
    >
      <span>
        Página {{ store.page }} de {{ store.pages }} ({{ store.total }}
        eventos)
      </span>
      <div class="flex gap-2">
        <BaseButton
          type="button"
          variant="secondary"
          data-testid="previous-page"
          :disabled="store.page <= 1"
          @click="changePage(store.page - 1)"
        >
          Anterior
        </BaseButton>
        <BaseButton
          type="button"
          variant="secondary"
          data-testid="next-page"
          :disabled="store.page >= store.pages"
          @click="changePage(store.page + 1)"
        >
          Siguiente
        </BaseButton>
      </div>
    </div>
  </main>
</template>
