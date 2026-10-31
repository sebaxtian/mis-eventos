import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import type { AuthUser } from '@/types/api'
import apiClient from '@/services/api'
import { useAuthStore } from '@/stores/auth'

const sampleUser: AuthUser = {
  id: 1,
  email: 'ana@example.com',
  full_name: 'Ana Pérez',
  role: 'ATTENDEE',
  is_active: true,
  created_at: '2026-10-31T12:00:00Z',
  updated_at: '2026-10-31T12:00:00Z',
}

describe('Auth store session persistence and initialization', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    window.sessionStorage.clear()
    vi.restoreAllMocks()
  })

  it('AUTH-AC-24 persists token and user in sessionStorage and restores session on initialize', async () => {
    const store = useAuthStore()
    store.setSession('jwt-token-abc', sampleUser)

    expect(window.sessionStorage.getItem('mis_eventos.auth.token')).toBe(
      'jwt-token-abc',
    )
    expect(
      JSON.parse(
        window.sessionStorage.getItem('mis_eventos.auth.user') || '{}',
      ),
    ).toEqual(sampleUser)
    expect(store.isAuthenticated).toBe(true)
    expect(store.isAdmin).toBe(false)

    const refreshedUser: AuthUser = {
      ...sampleUser,
      full_name: 'Ana Pérez Actualizada',
      role: 'ADMIN',
    }
    const getSpy = vi
      .spyOn(apiClient, 'get')
      .mockResolvedValueOnce({ data: refreshedUser })

    setActivePinia(createPinia())
    const freshStore = useAuthStore()
    await freshStore.initialize()

    expect(getSpy).toHaveBeenCalledWith('/auth/me')
    expect(freshStore.initialized).toBe(true)
    expect(freshStore.token).toBe('jwt-token-abc')
    expect(freshStore.user).toEqual(refreshedUser)
    expect(freshStore.isAdmin).toBe(true)
    expect(
      JSON.parse(
        window.sessionStorage.getItem('mis_eventos.auth.user') || '{}',
      ),
    ).toEqual(refreshedUser)
  })

  it('AUTH-AC-24 clears sessionStorage on clearSession and logout', async () => {
    const store = useAuthStore()
    store.setSession('jwt-token-abc', sampleUser)

    store.clearSession()
    expect(store.token).toBeNull()
    expect(store.user).toBeNull()
    expect(store.isAuthenticated).toBe(false)
    expect(window.sessionStorage.getItem('mis_eventos.auth.token')).toBeNull()
    expect(window.sessionStorage.getItem('mis_eventos.auth.user')).toBeNull()

    store.setSession('jwt-token-xyz', sampleUser)
    store.logout()
    expect(store.token).toBeNull()
    expect(store.user).toBeNull()
    expect(window.sessionStorage.getItem('mis_eventos.auth.token')).toBeNull()
    expect(window.sessionStorage.getItem('mis_eventos.auth.user')).toBeNull()

    window.sessionStorage.setItem('mis_eventos.auth.token', 'orphan-token')
    window.sessionStorage.setItem('mis_eventos.auth.user', '{corrupt-json')
    vi.spyOn(apiClient, 'get').mockRejectedValueOnce({
      response: { status: 401 },
    })

    setActivePinia(createPinia())
    const corruptStore = useAuthStore()
    await corruptStore.initialize()
    expect(corruptStore.isAuthenticated).toBe(false)
    expect(window.sessionStorage.getItem('mis_eventos.auth.token')).toBeNull()
    expect(window.sessionStorage.getItem('mis_eventos.auth.user')).toBeNull()
  })

  it('AUTH-AC-24 initializes session before router guards and refreshes user with GET /auth/me', async () => {
    const { createAppRouter } = await import('@/router')
    const adminUser: AuthUser = {
      ...sampleUser,
      role: 'ADMIN',
    }
    window.sessionStorage.setItem('mis_eventos.auth.token', 'stored-admin-jwt')
    window.sessionStorage.setItem(
      'mis_eventos.auth.user',
      JSON.stringify(sampleUser),
    )

    const getSpy = vi
      .spyOn(apiClient, 'get')
      .mockResolvedValue({ data: adminUser })

    const store = useAuthStore()
    const [p1, p2] = [store.initialize(), store.initialize()]
    await Promise.all([p1, p2])
    expect(getSpy).toHaveBeenCalledTimes(1)

    setActivePinia(createPinia())
    const router = createAppRouter(true)
    await router.push('/admin')
    await router.isReady()

    expect(router.currentRoute.value.name).toBe('admin')
    expect(getSpy).toHaveBeenCalledTimes(2)
  })

  it('AUTH-AC-28 auth DTOs match OpenAPI and expose no password_hash', async () => {
    const { readFileSync } = await import('node:fs')
    const { resolve } = await import('node:path')
    const authService = await import('@/services/auth')

    expect(typeof authService.register).toBe('function')
    expect(typeof authService.login).toBe('function')
    expect(typeof authService.getMe).toBe('function')
    expect(typeof authService.updateMe).toBe('function')

    const apiTypesSource = readFileSync(
      resolve(process.cwd(), 'src/types/api.ts'),
      'utf-8',
    )
    expect(apiTypesSource).toContain('full_name: string')
    expect(apiTypesSource).toContain('is_active: boolean')
    expect(apiTypesSource).toContain('created_at: string')
    expect(apiTypesSource).toContain('updated_at: string')
    expect(apiTypesSource).not.toContain('password_hash')

    expect(Object.keys(sampleUser).sort()).toEqual([
      'created_at',
      'email',
      'full_name',
      'id',
      'is_active',
      'role',
      'updated_at',
    ])
    expect('password_hash' in sampleUser).toBe(false)

    for (const viewFile of [
      'src/App.vue',
      'src/views/LoginView.vue',
      'src/views/RegisterView.vue',
      'src/views/ProfileView.vue',
      'src/views/AdminUsersView.vue',
    ]) {
      const source = readFileSync(resolve(process.cwd(), viewFile), 'utf-8')
      expect(source).not.toContain('v-html')
    }
  })
})
