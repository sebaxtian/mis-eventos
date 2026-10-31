import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { resetUnauthorizedState } from '@/services/api'
import { getMe, loginUser, registerUser, updateMe } from '@/services/auth'
import type {
  AuthUser,
  LoginPayload,
  RegisterPayload,
  UpdateProfilePayload,
  UserRole,
} from '@/types/api'

export const AUTH_TOKEN_STORAGE_KEY = 'mis_eventos.auth.token'
export const AUTH_USER_STORAGE_KEY = 'mis_eventos.auth.user'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(null)
  const user = ref<AuthUser | null>(null)
  const initialized = ref(false)
  let initializingPromise: Promise<void> | null = null

  const isAuthenticated = computed(() => Boolean(token.value && user.value))
  const role = computed<UserRole | null>(() => user.value?.role ?? null)
  const isAdmin = computed(() => role.value === 'ADMIN')

  function writeStorage(newToken: string, newUser: AuthUser): void {
    try {
      window.sessionStorage.setItem(AUTH_TOKEN_STORAGE_KEY, newToken)
      window.sessionStorage.setItem(
        AUTH_USER_STORAGE_KEY,
        JSON.stringify(newUser),
      )
    } catch {
      // Ignore storage write failures
    }
  }

  function setSession(newToken: string, newUser: AuthUser): void {
    token.value = newToken
    user.value = newUser
    initialized.value = true
    writeStorage(newToken, newUser)
    resetUnauthorizedState()
  }

  function clearSession(): void {
    token.value = null
    user.value = null
    resetUnauthorizedState()
    try {
      window.sessionStorage.removeItem(AUTH_TOKEN_STORAGE_KEY)
      window.sessionStorage.removeItem(AUTH_USER_STORAGE_KEY)
    } catch {
      // Ignore storage removal failures
    }
  }

  function logout(): void {
    clearSession()
  }

  async function fetchMe(): Promise<AuthUser | null> {
    const profile = await getMe()
    if (token.value) {
      setSession(token.value, profile)
    }
    return profile
  }

  async function initialize(): Promise<void> {
    if (initialized.value) return
    if (initializingPromise) return initializingPromise

    initializingPromise = (async () => {
      try {
        const storedToken = window.sessionStorage.getItem(AUTH_TOKEN_STORAGE_KEY)
        if (!storedToken) {
          return
        }
        token.value = storedToken
          const storedUserRaw = window.sessionStorage.getItem(AUTH_USER_STORAGE_KEY)
        if (storedUserRaw) {
          try {
            user.value = JSON.parse(storedUserRaw) as AuthUser
          } catch {
            user.value = null
            window.sessionStorage.removeItem(AUTH_USER_STORAGE_KEY)
          }
        }
        try {
          await fetchMe()
        } catch (err: unknown) {
          const status = (err as { response?: { status?: number } })?.response
            ?.status
          if (status === 401) {
            clearSession()
          }
        }
      } finally {
        initialized.value = true
        initializingPromise = null
      }
    })()

    return initializingPromise
  }

  async function login(payload: LoginPayload): Promise<AuthUser> {
    const data = await loginUser(payload)
    setSession(data.access_token, data.user)
    return data.user
  }

  async function register(payload: RegisterPayload): Promise<AuthUser> {
    return registerUser(payload)
  }

  async function updateProfile(
    payload: UpdateProfilePayload,
  ): Promise<AuthUser> {
    const updated = await updateMe(payload)
    if (token.value) {
      setSession(token.value, updated)
    } else {
      user.value = updated
    }
    return updated
  }

  return {
    token,
    user,
    initialized,
    isAuthenticated,
    role,
    isAdmin,
    setSession,
    clearSession,
    logout,
    fetchMe,
    initialize,
    login,
    register,
    updateProfile,
  }
})
