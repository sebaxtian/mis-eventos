import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import type { AxiosError } from 'axios'
import type {
  ApiError,
  EventCreatePayload,
  EventListQuery,
  EventRead,
  EventStatus,
  EventUpdatePayload,
} from '@/types/api'
import {
  createEventApi,
  deleteEventApi,
  fetchEventByIdApi,
  fetchEventsApi,
  updateEventApi,
  uploadEventImageApi,
} from '@/services/events'
import { useAuthStore } from '@/stores/auth'

function resolveErrorMessage(error: unknown, fallback: string): string {
  const axiosError = error as AxiosError<ApiError>
  return (
    axiosError.response?.data?.detail ||
    axiosError.response?.data?.errors?.[0]?.message ||
    fallback
  )
}

export const useEventStore = defineStore('events', () => {
  const items = ref<EventRead[]>([])
  const total = ref(0)
  const page = ref(1)
  const size = ref(10)
  const pages = ref(0)
  const search = ref('')
  const statusFilter = ref<EventStatus | ''>('')
  const mineOnly = ref(false)
  const currentEvent = ref<EventRead | null>(null)
  const isLoading = ref(false)
  const isSubmitting = ref(false)
  const errorMessage = ref('')

  const authStore = useAuthStore()

  const hasEvents = computed(() => items.value.length > 0)
  const canCreate = computed(
    () => authStore.role === 'ORGANIZER' || authStore.role === 'ADMIN',
  )

  function replaceItem(event: EventRead): void {
    const index = items.value.findIndex((item) => item.id === event.id)
    if (index !== -1) {
      items.value[index] = event
    }
  }

  async function fetchEvents(
    overrides: Partial<EventListQuery> = {},
  ): Promise<void> {
    if (overrides.page !== undefined) page.value = overrides.page
    if (overrides.size !== undefined) size.value = overrides.size
    if (overrides.search !== undefined) search.value = overrides.search
    if (overrides.status !== undefined) statusFilter.value = overrides.status
    if (overrides.mine !== undefined) mineOnly.value = overrides.mine

    const params: EventListQuery = {
      page: page.value,
      size: size.value,
    }
    const normalizedSearch = search.value.trim()
    if (normalizedSearch) {
      params.search = normalizedSearch
    }
    if (statusFilter.value) {
      params.status = statusFilter.value
    }
    if (mineOnly.value) {
      params.mine = true
    }

    isLoading.value = true
    errorMessage.value = ''
    try {
      const response = await fetchEventsApi(params)
      items.value = response.items
      total.value = response.total
      page.value = response.page
      size.value = response.size
      pages.value = response.pages
    } catch (error: unknown) {
      items.value = []
      total.value = 0
      pages.value = 0
      errorMessage.value = resolveErrorMessage(
        error,
        'No se pudo cargar el catálogo de eventos',
      )
    } finally {
      isLoading.value = false
    }
  }

  async function fetchEventById(id: number): Promise<void> {
    isLoading.value = true
    errorMessage.value = ''
    try {
      const event = await fetchEventByIdApi(id)
      currentEvent.value = event
      replaceItem(event)
    } catch (error: unknown) {
      currentEvent.value = null
      errorMessage.value = resolveErrorMessage(error, 'Evento no encontrado')
    } finally {
      isLoading.value = false
    }
  }

  async function createEvent(
    payload: EventCreatePayload,
  ): Promise<EventRead> {
    isSubmitting.value = true
    errorMessage.value = ''
    try {
      const event = await createEventApi(payload)
      currentEvent.value = event
      items.value = [event, ...items.value]
      total.value += 1
      return event
    } catch (error: unknown) {
      errorMessage.value = resolveErrorMessage(
        error,
        'No se pudo crear el evento',
      )
      throw error
    } finally {
      isSubmitting.value = false
    }
  }

  async function updateEvent(
    id: number,
    payload: EventUpdatePayload,
  ): Promise<EventRead> {
    isSubmitting.value = true
    errorMessage.value = ''
    try {
      const event = await updateEventApi(id, payload)
      currentEvent.value = event
      replaceItem(event)
      return event
    } catch (error: unknown) {
      errorMessage.value = resolveErrorMessage(
        error,
        'No se pudo actualizar el evento',
      )
      throw error
    } finally {
      isSubmitting.value = false
    }
  }

  async function deleteEvent(id: number): Promise<void> {
    isSubmitting.value = true
    errorMessage.value = ''
    try {
      await deleteEventApi(id)
      items.value = items.value.filter((item) => item.id !== id)
      total.value = Math.max(0, total.value - 1)
      if (currentEvent.value?.id === id) {
        currentEvent.value = null
      }
    } catch (error: unknown) {
      errorMessage.value = resolveErrorMessage(
        error,
        'No se pudo eliminar el evento',
      )
      throw error
    } finally {
      isSubmitting.value = false
    }
  }

  async function uploadEventImage(
    id: number,
    file: File,
  ): Promise<EventRead> {
    isSubmitting.value = true
    errorMessage.value = ''
    try {
      const event = await uploadEventImageApi(id, file)
      currentEvent.value = event
      replaceItem(event)
      return event
    } catch (error: unknown) {
      errorMessage.value = resolveErrorMessage(
        error,
        'No se pudo subir la imagen del evento',
      )
      throw error
    } finally {
      isSubmitting.value = false
    }
  }

  function resetFilters(): void {
    search.value = ''
    statusFilter.value = ''
    mineOnly.value = false
    page.value = 1
  }

  function clearCurrentEvent(): void {
    currentEvent.value = null
    errorMessage.value = ''
  }

  return {
    items,
    total,
    page,
    size,
    pages,
    search,
    statusFilter,
    mineOnly,
    currentEvent,
    isLoading,
    isSubmitting,
    errorMessage,
    hasEvents,
    canCreate,
    fetchEvents,
    fetchEventById,
    createEvent,
    updateEvent,
    deleteEvent,
    uploadEventImage,
    resetFilters,
    clearCurrentEvent,
  }
})
