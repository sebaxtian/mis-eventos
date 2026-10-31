import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import type { AuthUser } from '@/types/api'
import { createAppRouter } from '@/router'
import apiClient from '@/services/api'
import { useAuthStore } from '@/stores/auth'
import { useNotificationStore } from '@/stores/notification'
import LoginView from '@/views/LoginView.vue'
import ProfileView from '@/views/ProfileView.vue'
import RegisterView from '@/views/RegisterView.vue'

const registeredUser: AuthUser = {
  id: 1,
  email: 'ana@example.com',
  full_name: 'Ana Pérez',
  role: 'ATTENDEE',
  is_active: true,
  created_at: '2026-10-31T12:00:00Z',
  updated_at: '2026-10-31T12:00:00Z',
}

describe('Auth views (Register, Login, Profile)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    window.sessionStorage.clear()
    vi.restoreAllMocks()
  })

  it('AUTH-AC-01 register view submits full_name, email and password and redirects to login', async () => {
    const router = createAppRouter(true)
    await router.push('/register')
    await router.isReady()

    const postSpy = vi
      .spyOn(apiClient, 'post')
      .mockResolvedValueOnce({ data: registeredUser })

    const wrapper = mount(RegisterView, {
      global: {
        plugins: [router],
      },
    })

    const pushSpy = vi.spyOn(router, 'push')
    await wrapper.find('input#register-full-name').setValue('Ana Pérez')
    await wrapper.find('input#register-email').setValue('ana@example.com')
    await wrapper.find('input#register-password').setValue('Secreto123')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()
    await Promise.all(pushSpy.mock.results.map((r) => r.value))

    expect(postSpy).toHaveBeenCalledWith('/auth/register', {
      full_name: 'Ana Pérez',
      email: 'ana@example.com',
      password: 'Secreto123',
    })

    const authStore = useAuthStore()
    const notificationStore = useNotificationStore()
    expect(authStore.isAuthenticated).toBe(false)
    expect(window.sessionStorage.getItem('mis_eventos.auth.token')).toBeNull()
    expect(notificationStore.lastMessage).toContain('Cuenta creada')
    expect(router.currentRoute.value.name).toBe('login')

    postSpy.mockRejectedValueOnce({
      response: {
        status: 409,
        data: { detail: 'Ya existe una cuenta con este correo electrónico' },
      },
    })
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()
    expect(wrapper.text()).toContain(
      'Ya existe una cuenta con este correo electrónico',
    )
  })

  it('AUTH-AC-06 login view stores session and redirects to redirect target', async () => {
    const router = createAppRouter(true)
    await router.push('/login?redirect=/profile')
    await router.isReady()

    const postSpy = vi.spyOn(apiClient, 'post').mockResolvedValueOnce({
      data: {
        access_token: 'jwt-login-06',
        token_type: 'bearer',
        expires_in: 28800,
        user: registeredUser,
      },
    })
    const pushSpy = vi.spyOn(router, 'push')

    const wrapper = mount(LoginView, {
      global: {
        plugins: [router],
      },
    })

    await wrapper.find('input#login-email').setValue('ana@example.com')
    await wrapper.find('input#login-password').setValue('Secreto123')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()
    await Promise.all(pushSpy.mock.results.map((r) => r.value))

    expect(postSpy).toHaveBeenCalledWith('/auth/login', {
      email: 'ana@example.com',
      password: 'Secreto123',
    })

    const authStore = useAuthStore()
    expect(authStore.isAuthenticated).toBe(true)
    expect(window.sessionStorage.getItem('mis_eventos.auth.token')).toBe(
      'jwt-login-06',
    )
    expect(router.currentRoute.value.fullPath).toBe('/profile')
  })

  it('AUTH-AC-07 login view shows generic credentials error without redirect', async () => {
    const router = createAppRouter(true)
    await router.push('/login?redirect=/profile')
    await router.isReady()

    vi.spyOn(apiClient, 'post').mockRejectedValueOnce({
      response: {
        status: 401,
        data: { detail: 'Credenciales inválidas' },
      },
    })
    const pushSpy = vi.spyOn(router, 'push')

    const wrapper = mount(LoginView, {
      global: {
        plugins: [router],
      },
    })

    await wrapper.find('input#login-email').setValue('noexiste@example.com')
    await wrapper.find('input#login-password').setValue('Incorrecta123')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    expect(pushSpy).not.toHaveBeenCalled()
    expect(router.currentRoute.value.name).toBe('login')
    expect(wrapper.text()).toContain('Credenciales inválidas')
  })

  it('AUTH-AC-14 profile view shows read-only email/role and updates full_name', async () => {
    const authStore = useAuthStore()
    authStore.setSession('jwt-profile-14', registeredUser)

    const router = createAppRouter(true)
    await router.push('/profile')
    await router.isReady()

    const updatedUser: AuthUser = {
      ...registeredUser,
      full_name: 'Ana María Pérez',
    }
    const patchSpy = vi
      .spyOn(apiClient, 'patch')
      .mockResolvedValueOnce({ data: updatedUser })
    const pushSpy = vi.spyOn(router, 'push')

    const wrapper = mount(ProfileView, {
      global: {
        plugins: [router],
      },
    })

    expect(wrapper.text()).toContain('ana@example.com')
    expect(wrapper.text()).toContain('Asistente')
    expect(wrapper.text()).toContain('Activa')
    expect(wrapper.find('input#profile-email').exists()).toBe(false)
    expect(wrapper.find('select#profile-role').exists()).toBe(false)

    await wrapper.find('input#profile-full-name').setValue('Ana María Pérez')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    expect(patchSpy).toHaveBeenCalledWith('/auth/me', {
      full_name: 'Ana María Pérez',
    })
    expect(authStore.user?.full_name).toBe('Ana María Pérez')
    expect(wrapper.text()).toContain('Perfil actualizado')

    await wrapper.find('button[data-testid="logout-button"]').trigger('click')
    await flushPromises()
    await Promise.all(pushSpy.mock.results.map((r) => r.value))

    expect(authStore.isAuthenticated).toBe(false)
    expect(window.sessionStorage.getItem('mis_eventos.auth.token')).toBeNull()
    expect(router.currentRoute.value.name).toBe('login')
  })
})
