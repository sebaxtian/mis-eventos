import axios, {
  type AxiosError,
  type AxiosInstance,
  type InternalAxiosRequestConfig,
} from 'axios'
import type { ApiError } from '@/types/api'
import { useAuthStore } from '@/stores/auth'
import { useNotificationStore } from '@/stores/notification'

export type NavigationRedirectHandler = (location: {
  name: string
  query?: Record<string, string>
}) => void

let redirectHandler: NavigationRedirectHandler | null = null
let currentRoutePathGetter: (() => string) | null = null

export function configureApiNavigation(
  onRedirect: NavigationRedirectHandler,
  getCurrentPath?: () => string,
): void {
  redirectHandler = onRedirect
  currentRoutePathGetter = getCurrentPath ?? null
}

function isLoginEndpoint(url?: string): boolean {
  if (!url) return false
  return url.includes('/auth/login')
}

export function attachAuthToken(
  config: InternalAxiosRequestConfig,
): InternalAxiosRequestConfig {
  const authStore = useAuthStore()
  if (authStore.token && config.headers) {
    config.headers.Authorization = `Bearer ${authStore.token}`
  }
  return config
}

export async function handleApiResponseError(
  error: AxiosError<ApiError>,
): Promise<never> {
  const authStore = useAuthStore()
  const notificationStore = useNotificationStore()
  const status = error.response?.status
  const detail = error.response?.data?.detail
  const requestUrl = error.config?.url

  if (status === 401) {
    if (isLoginEndpoint(requestUrl)) {
      notificationStore.notify(
        detail || 'Credenciales inválidas',
        'error',
      )
    } else {
      authStore.clearSession()
      notificationStore.notify(
        'Tu sesión ha expirado. Inicia sesión nuevamente.',
        'warning',
      )
      const originPath =
        currentRoutePathGetter?.() || window.location.pathname || '/'
      redirectHandler?.({
        name: 'login',
        query: { redirect: originPath },
      })
    }
  } else if (status === 403) {
    notificationStore.notify(
      detail || 'No tienes permisos para realizar esta acción',
      'warning',
    )
  } else if (status === 400 || status === 404 || status === 409 || status === 422) {
    notificationStore.notify(
      detail || 'Error al procesar la solicitud',
      'error',
    )
  } else if (!status || status >= 500) {
    notificationStore.notify(
      'No se pudo completar la operación. Inténtalo de nuevo más tarde.',
      'error',
    )
  }

  return Promise.reject(error)
}

export const apiClient: AxiosInstance = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
})

apiClient.interceptors.request.use((config) => attachAuthToken(config))
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ApiError>) => handleApiResponseError(error),
)

export default apiClient
