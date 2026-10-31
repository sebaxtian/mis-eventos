import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import type { AuthUser, UserRole } from '@/types/api'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(null)
  const user = ref<AuthUser | null>(null)

  const isAuthenticated = computed(() => Boolean(token.value && user.value))
  const role = computed<UserRole | null>(() => user.value?.role ?? null)

  function setSession(newToken: string, newUser: AuthUser): void {
    token.value = newToken
    user.value = newUser
  }

  function clearSession(): void {
    token.value = null
    user.value = null
  }

  return {
    token,
    user,
    isAuthenticated,
    role,
    setSession,
    clearSession,
  }
})
