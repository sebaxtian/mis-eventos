import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import type { AxiosError, InternalAxiosRequestConfig } from 'axios'
import type { ApiError } from '@/types/api'
import {
  apiClient,
  attachAuthToken,
  configureApiNavigation,
  handleApiResponseError,
} from '@/services/api'
import { useAuthStore } from '@/stores/auth'
import { useNotificationStore } from '@/stores/notification'

function makeAxiosError(
  status: number | undefined,
  url: string,
  detail?: string,
): AxiosError<ApiError> {
  const config = {
    url,
    headers: {},
  } as InternalAxiosRequestConfig

  const error = new Error('Request failed') as AxiosError<ApiError>
  error.config = config
  error.isAxiosError = true
  if (status !== undefined) {
    error.response = {
      status,
      statusText: String(status),
      headers: {},
      config,
      data: detail ? { detail } : { detail: '' },
    }
  }
  return error
}

describe('Axios API client and error interceptor', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('PLAT-AC-13 clears auth session and redirects to login on 401 except on login endpoint', async () => {
    const authStore = useAuthStore()
    const notificationStore = useNotificationStore()
    authStore.setSession('jwt-token-123', {
      id: 1,
      email: 'user@example.com',
      full_name: 'Usuario Test',
      role: 'ATTENDEE',
      is_active: true,
      created_at: '2026-10-31T12:00:00Z',
      updated_at: '2026-10-31T12:00:00Z',
    })

    const redirectSpy = vi.fn()
    configureApiNavigation(redirectSpy, () => '/eventos/42')

    expect(apiClient.defaults.baseURL).toBe('/api')

    await expect(
      handleApiResponseError(
        makeAxiosError(401, '/events/42/register', 'No autenticado o sesión expirada'),
      ),
    ).rejects.toThrow()

    expect(authStore.isAuthenticated).toBe(false)
    expect(authStore.token).toBeNull()
    expect(notificationStore.lastMessage).toContain('sesión')
    expect(redirectSpy).toHaveBeenCalledWith({
      name: 'login',
      query: { redirect: '/eventos/42' },
    })

    redirectSpy.mockClear()
    notificationStore.clear()

    await expect(
      handleApiResponseError(
        makeAxiosError(401, '/auth/login', 'Credenciales inválidas'),
      ),
    ).rejects.toThrow()

    expect(redirectSpy).not.toHaveBeenCalled()
    expect(notificationStore.lastMessage).toBe('Credenciales inválidas')
  })

  it('PLAT-AC-14 preserves active session and shows Spanish warning on 403', async () => {
    const authStore = useAuthStore()
    const notificationStore = useNotificationStore()
    authStore.setSession('jwt-token-active', {
      id: 2,
      email: 'attendee@example.com',
      full_name: 'Asistente Test',
      role: 'ATTENDEE',
      is_active: true,
      created_at: '2026-10-31T12:00:00Z',
      updated_at: '2026-10-31T12:00:00Z',
    })

    const redirectSpy = vi.fn()
    configureApiNavigation(redirectSpy, () => '/admin')

    await expect(
      handleApiResponseError(makeAxiosError(403, '/events')),
    ).rejects.toThrow()

    expect(authStore.isAuthenticated).toBe(true)
    expect(authStore.token).toBe('jwt-token-active')
    expect(redirectSpy).not.toHaveBeenCalled()
    expect(notificationStore.lastMessage).toBe(
      'No tienes permisos para realizar esta acción',
    )
  })

  it('PLAT-AC-15 notifies API Spanish detail on 404/409/422 and generic Spanish message on 5xx or network error', async () => {
    const notificationStore = useNotificationStore()

    await expect(
      handleApiResponseError(
        makeAxiosError(404, '/events/999', 'Evento no encontrado'),
      ),
    ).rejects.toThrow()
    expect(notificationStore.lastMessage).toBe('Evento no encontrado')

    await expect(
      handleApiResponseError(
        makeAxiosError(409, '/events/1/register', 'El evento no tiene cupos disponibles'),
      ),
    ).rejects.toThrow()
    expect(notificationStore.lastMessage).toBe(
      'El evento no tiene cupos disponibles',
    )

    await expect(
      handleApiResponseError(
        makeAxiosError(422, '/events', 'Error de validación en los datos enviados'),
      ),
    ).rejects.toThrow()
    expect(notificationStore.lastMessage).toBe(
      'Error de validación en los datos enviados',
    )

    await expect(
      handleApiResponseError(
        makeAxiosError(500, '/events', 'Database stack trace'),
      ),
    ).rejects.toThrow()
    expect(notificationStore.lastMessage).toBe(
      'No se pudo completar la operación. Inténtalo de nuevo más tarde.',
    )

    notificationStore.clear()
    await expect(
      handleApiResponseError(makeAxiosError(undefined, '/events')),
    ).rejects.toThrow()
    expect(notificationStore.lastMessage).toBe(
      'No se pudo completar la operación. Inténtalo de nuevo más tarde.',
    )
  })

  it('AUTH-AC-25 handles concurrent 401 responses with one notice and redirect preserving redirect query', async () => {
    const authStore = useAuthStore()
    const notificationStore = useNotificationStore()
    authStore.setSession('jwt-token-concurrent', {
      id: 7,
      email: 'ana@example.com',
      full_name: 'Ana Pérez',
      role: 'ATTENDEE',
      is_active: true,
      created_at: '2026-10-31T12:00:00Z',
      updated_at: '2026-10-31T12:00:00Z',
    })

    const redirectSpy = vi.fn()
    configureApiNavigation(redirectSpy, () => '/profile?tab=info')

    const results = await Promise.allSettled([
      handleApiResponseError(
        makeAxiosError(401, '/auth/me', 'No autenticado o sesión expirada'),
      ),
      handleApiResponseError(
        makeAxiosError(401, '/events/10', 'No autenticado o sesión expirada'),
      ),
      handleApiResponseError(
        makeAxiosError(401, '/users', 'No autenticado o sesión expirada'),
      ),
    ])

    expect(results.every((r) => r.status === 'rejected')).toBe(true)
    expect(authStore.isAuthenticated).toBe(false)
    expect(window.sessionStorage.getItem('mis_eventos.auth.token')).toBeNull()
    expect(notificationStore.notifications).toHaveLength(1)
    expect(redirectSpy).toHaveBeenCalledTimes(1)
    expect(redirectSpy).toHaveBeenCalledWith({
      name: 'login',
      query: { redirect: '/profile?tab=info' },
    })
  })

  it('AUTH-AC-26 keeps session and shows Spanish notice on 403 while login 401 does not redirect', async () => {
    const authStore = useAuthStore()
    const notificationStore = useNotificationStore()
    authStore.setSession('jwt-session-26', {
      id: 8,
      email: 'attendee@example.com',
      full_name: 'Ana Pérez',
      role: 'ATTENDEE',
      is_active: true,
      created_at: '2026-10-31T12:00:00Z',
      updated_at: '2026-10-31T12:00:00Z',
    })

    const redirectSpy = vi.fn()
    configureApiNavigation(redirectSpy, () => '/admin/users')

    await expect(
      handleApiResponseError(
        makeAxiosError(
          403,
          '/users',
          'No tienes permisos para realizar esta acción',
        ),
      ),
    ).rejects.toThrow()

    expect(authStore.isAuthenticated).toBe(true)
    expect(window.sessionStorage.getItem('mis_eventos.auth.token')).toBe(
      'jwt-session-26',
    )
    expect(redirectSpy).not.toHaveBeenCalled()
    expect(notificationStore.lastMessage).toBe(
      'No tienes permisos para realizar esta acción',
    )

    notificationStore.clear()
    await expect(
      handleApiResponseError(
        makeAxiosError(401, '/auth/login', 'Credenciales inválidas'),
      ),
    ).rejects.toThrow()

    expect(redirectSpy).not.toHaveBeenCalled()
    expect(notificationStore.lastMessage).toBe('Credenciales inválidas')

    const validationErr = makeAxiosError(
      422,
      '/auth/register',
      'Error de validación en los datos enviados',
    )
    if (validationErr.response) {
      validationErr.response.data = {
        detail: 'Error de validación en los datos enviados',
        errors: [
          { field: 'email', message: 'El correo electrónico no es válido' },
        ],
      }
    }
    await expect(handleApiResponseError(validationErr)).rejects.toThrow()
    expect(notificationStore.lastMessage).toBe(
      'El correo electrónico no es válido',
    )
  })
})


