import { ref } from 'vue'
import { defineStore } from 'pinia'
import type { AxiosError } from 'axios'
import type {
  ApiError,
  SessionCreatePayload,
  SessionRead,
  SessionUpdatePayload,
  ValidationFieldError,
} from '@/types/api'
import {
  createSessionApi,
  deleteSessionApi,
  fetchSessionByIdApi,
  fetchSessionsApi,
  updateSessionApi,
} from '@/services/sessions'

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

function sortSessions(sessions: SessionRead[]): SessionRead[] {
  return [...sessions].sort(
    (first, second) =>
      first.start_time.localeCompare(second.start_time) ||
      first.id - second.id,
  )
}

export const useSessionStore = defineStore('sessions', () => {
  const items = ref<SessionRead[]>([])
  const total = ref(0)
  const currentSession = ref<SessionRead | null>(null)
  const isLoading = ref(false)
  const isSubmitting = ref(false)
  const errorMessage = ref('')
  const fieldErrors = ref<ValidationFieldError[]>([])

  function clearErrors(): void {
    errorMessage.value = ''
    fieldErrors.value = []
  }

  function reset(): void {
    items.value = []
    total.value = 0
    currentSession.value = null
    isLoading.value = false
    isSubmitting.value = false
    clearErrors()
  }

  async function fetchSessions(eventId: number): Promise<void> {
    isLoading.value = true
    clearErrors()
    try {
      const response = await fetchSessionsApi(eventId)
      items.value = sortSessions(response.items)
      total.value = response.total
    } catch (error: unknown) {
      items.value = []
      total.value = 0
      errorMessage.value = resolveErrorMessage(
        error,
        'No se pudo cargar la agenda del evento',
      )
      fieldErrors.value = resolveFieldErrors(error)
    } finally {
      isLoading.value = false
    }
  }

  async function fetchSessionById(
    eventId: number,
    sessionId: number,
  ): Promise<void> {
    isLoading.value = true
    clearErrors()
    try {
      currentSession.value = await fetchSessionByIdApi(eventId, sessionId)
    } catch (error: unknown) {
      currentSession.value = null
      errorMessage.value = resolveErrorMessage(
        error,
        'Sesión no encontrada',
      )
      fieldErrors.value = resolveFieldErrors(error)
    } finally {
      isLoading.value = false
    }
  }

  async function createSession(
    eventId: number,
    payload: SessionCreatePayload,
  ): Promise<SessionRead> {
    isSubmitting.value = true
    clearErrors()
    try {
      const created = await createSessionApi(eventId, payload)
      items.value = sortSessions([...items.value, created])
      total.value += 1
      currentSession.value = created
      return created
    } catch (error: unknown) {
      errorMessage.value = resolveErrorMessage(
        error,
        'No se pudo crear la sesión',
      )
      fieldErrors.value = resolveFieldErrors(error)
      throw error
    } finally {
      isSubmitting.value = false
    }
  }

  async function updateSession(
    eventId: number,
    sessionId: number,
    payload: SessionUpdatePayload,
  ): Promise<SessionRead> {
    isSubmitting.value = true
    clearErrors()
    try {
      const updated = await updateSessionApi(
        eventId,
        sessionId,
        payload,
      )
      const index = items.value.findIndex(
        (item) => item.id === updated.id,
      )
      if (index === -1) {
        items.value = sortSessions([...items.value, updated])
      } else {
        items.value[index] = updated
      }
      currentSession.value = updated
      return updated
    } catch (error: unknown) {
      errorMessage.value = resolveErrorMessage(
        error,
        'No se pudo actualizar la sesión',
      )
      fieldErrors.value = resolveFieldErrors(error)
      throw error
    } finally {
      isSubmitting.value = false
    }
  }

  async function deleteSession(
    eventId: number,
    sessionId: number,
  ): Promise<void> {
    isSubmitting.value = true
    clearErrors()
    try {
      await deleteSessionApi(eventId, sessionId)
      items.value = items.value.filter((item) => item.id !== sessionId)
      total.value = Math.max(0, total.value - 1)
      if (currentSession.value?.id === sessionId) {
        currentSession.value = null
      }
    } catch (error: unknown) {
      errorMessage.value = resolveErrorMessage(
        error,
        'No se pudo eliminar la sesión',
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
    currentSession,
    isLoading,
    isSubmitting,
    errorMessage,
    fieldErrors,
    fetchSessions,
    fetchSessionById,
    createSession,
    updateSession,
    deleteSession,
    clearErrors,
    reset,
  }
})
