import { ref } from 'vue'
import { defineStore } from 'pinia'
import type { AxiosError } from 'axios'
import type {
  ApiError,
  EventRegistrationListQuery,
  RegistrationListQuery,
  RegistrationRead,
  RegistrationStatus,
  ValidationFieldError,
} from '@/types/api'
import {
  cancelRegistrationApi,
  fetchEventRegistrationsApi,
  fetchMyRegistrationsApi,
  fetchRegistrationByIdApi,
  registerForEventApi,
  registerForSessionApi,
} from '@/services/registrations'

function resolveErrorMessage(error: unknown, fallback: string): string {
  const axiosError = error as AxiosError<ApiError>
  return (
    axiosError.response?.data?.detail ||
    axiosError.response?.data?.errors?.[0]?.message ||
    fallback
  )
}

function resolveFieldErrors(error: unknown): ValidationFieldError[] {
  const axiosError = error as AxiosError<ApiError>
  return axiosError.response?.data?.errors ?? []
}

export type RegistrationStoreQuery = Omit<
  RegistrationListQuery,
  'status'
> & {
  status?: RegistrationStatus | ''
}

export type EventRegistrationStoreQuery = Omit<
  EventRegistrationListQuery,
  'status'
> & {
  status?: RegistrationStatus | ''
}

export const useRegistrationStore = defineStore('registrations', () => {
  const items = ref<RegistrationRead[]>([])
  const total = ref(0)
  const page = ref(1)
  const size = ref(10)
  const pages = ref(0)
  const statusFilter = ref<RegistrationStatus | ''>('')
  const eventIdFilter = ref<number | null>(null)
  const currentRegistration = ref<RegistrationRead | null>(null)
  const isLoading = ref(false)
  const isSubmitting = ref(false)
  const errorMessage = ref('')
  const fieldErrors = ref<ValidationFieldError[]>([])
  const lastCreatedStatus = ref<'created' | 'reactivated' | null>(null)

  function clearErrors(): void {
    errorMessage.value = ''
    fieldErrors.value = []
  }

  function reset(): void {
    items.value = []
    total.value = 0
    page.value = 1
    size.value = 10
    pages.value = 0
    statusFilter.value = ''
    eventIdFilter.value = null
    currentRegistration.value = null
    isLoading.value = false
    isSubmitting.value = false
    lastCreatedStatus.value = null
    clearErrors()
  }

  function invalidateList(): void {
    items.value = []
    total.value = 0
    pages.value = 0
  }

  async function fetchMyRegistrations(
    query: RegistrationStoreQuery = {},
  ): Promise<void> {
    if (query.page !== undefined) page.value = query.page
    if (query.size !== undefined) size.value = query.size
    if (query.status !== undefined) statusFilter.value = query.status
    if (query.event_id !== undefined) eventIdFilter.value = query.event_id

    const params: RegistrationListQuery = {
      page: page.value,
      size: size.value,
    }
    if (statusFilter.value) params.status = statusFilter.value
    if (eventIdFilter.value !== null) params.event_id = eventIdFilter.value

    isLoading.value = true
    clearErrors()
    try {
      const response = await fetchMyRegistrationsApi(params)
      items.value = response.items
      total.value = response.total
      page.value = response.page
      size.value = response.size
      pages.value = response.pages
    } catch (error: unknown) {
      invalidateList()
      errorMessage.value = resolveErrorMessage(
        error,
        'No se pudieron cargar tus inscripciones',
      )
      fieldErrors.value = resolveFieldErrors(error)
    } finally {
      isLoading.value = false
    }
  }

  async function fetchEventRegistrations(
    eventId: number,
    query: EventRegistrationStoreQuery = {},
  ): Promise<void> {
    if (query.page !== undefined) page.value = query.page
    if (query.size !== undefined) size.value = query.size
    if (query.status !== undefined) statusFilter.value = query.status

    const params: EventRegistrationListQuery = {
      page: page.value,
      size: size.value,
    }
    if (statusFilter.value) params.status = statusFilter.value

    isLoading.value = true
    clearErrors()
    try {
      const response = await fetchEventRegistrationsApi(eventId, params)
      items.value = response.items
      total.value = response.total
      page.value = response.page
      size.value = response.size
      pages.value = response.pages
    } catch (error: unknown) {
      invalidateList()
      errorMessage.value = resolveErrorMessage(
        error,
        'No se pudieron cargar las inscripciones del evento',
      )
      fieldErrors.value = resolveFieldErrors(error)
    } finally {
      isLoading.value = false
    }
  }

  async function fetchRegistrationById(id: number): Promise<void> {
    isLoading.value = true
    clearErrors()
    try {
      currentRegistration.value = await fetchRegistrationByIdApi(id)
    } catch (error: unknown) {
      currentRegistration.value = null
      errorMessage.value = resolveErrorMessage(
        error,
        'Inscripción no encontrada',
      )
      fieldErrors.value = resolveFieldErrors(error)
    } finally {
      isLoading.value = false
    }
  }

  async function registerForEvent(
    eventId: number,
  ): Promise<RegistrationRead> {
    isSubmitting.value = true
    clearErrors()
    try {
      const result = await registerForEventApi(eventId)
      currentRegistration.value = result.registration
      lastCreatedStatus.value = result.created ? 'created' : 'reactivated'
      invalidateList()
      return result.registration
    } catch (error: unknown) {
      errorMessage.value = resolveErrorMessage(
        error,
        'No se pudo completar la inscripción al evento',
      )
      fieldErrors.value = resolveFieldErrors(error)
      throw error
    } finally {
      isSubmitting.value = false
    }
  }

  async function registerForSession(
    eventId: number,
    sessionId: number,
  ): Promise<RegistrationRead> {
    isSubmitting.value = true
    clearErrors()
    try {
      const result = await registerForSessionApi(eventId, sessionId)
      currentRegistration.value = result.registration
      lastCreatedStatus.value = result.created ? 'created' : 'reactivated'
      invalidateList()
      return result.registration
    } catch (error: unknown) {
      errorMessage.value = resolveErrorMessage(
        error,
        'No se pudo completar la inscripción a la sesión',
      )
      fieldErrors.value = resolveFieldErrors(error)
      throw error
    } finally {
      isSubmitting.value = false
    }
  }

  async function cancelRegistration(id: number): Promise<void> {
    isSubmitting.value = true
    clearErrors()
    try {
      await cancelRegistrationApi(id)
      if (currentRegistration.value?.id === id) {
        currentRegistration.value = null
      }
      invalidateList()
    } catch (error: unknown) {
      errorMessage.value = resolveErrorMessage(
        error,
        'No se pudo cancelar la inscripción',
      )
      fieldErrors.value = resolveFieldErrors(error)
      throw error
    } finally {
      isSubmitting.value = false
    }
  }

  return {
    items,
    total,
    page,
    size,
    pages,
    statusFilter,
    eventIdFilter,
    currentRegistration,
    isLoading,
    isSubmitting,
    errorMessage,
    fieldErrors,
    lastCreatedStatus,
    fetchMyRegistrations,
    fetchEventRegistrations,
    fetchRegistrationById,
    registerForEvent,
    registerForSession,
    cancelRegistration,
    clearErrors,
    reset,
  }
})
