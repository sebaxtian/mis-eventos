import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { createAppRouter, routes } from '@/router'
import { useAuthStore } from '@/stores/auth'
import { useNotificationStore } from '@/stores/notification'

describe('Vue Router lazy loading and UX navigation guards', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    window.sessionStorage.clear()
  })

  it('PLAT-AC-16 enforces UX navigation guards for requiresAuth and role restrictions with lazy-loaded routes', async () => {
    for (const route of routes) {
      expect(typeof route.component).toBe('function')
    }

    const authStore = useAuthStore()
    const notificationStore = useNotificationStore()
    const router = createAppRouter(true)

    await router.push('/admin')
    await router.isReady()

    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.redirect).toBe('/admin')

    authStore.setSession('token-attendee', {
      id: 10,
      email: 'attendee@example.com',
      full_name: 'Asistente',
      role: 'ATTENDEE',
      is_active: true,
      created_at: '2026-10-31T12:00:00Z',
      updated_at: '2026-10-31T12:00:00Z',
    })

    await router.push('/admin')
    expect(router.currentRoute.value.name).toBe('home')
    expect(notificationStore.lastMessage).toBe(
      'No tienes permisos para acceder a esta sección',
    )

    authStore.setSession('token-admin', {
      id: 1,
      email: 'admin@example.com',
      full_name: 'Administrador',
      role: 'ADMIN',
      is_active: true,
      created_at: '2026-10-31T12:00:00Z',
      updated_at: '2026-10-31T12:00:00Z',
    })

    await router.push('/admin')
    expect(router.currentRoute.value.name).toBe('admin')
  })

  it('PLAT-AC-18 configures lazy route chunks and builds minified bundle without public sourcemaps', async () => {
    for (const route of routes) {
      expect(typeof route.component).toBe('function')
      const loader = route.component as () => Promise<{ default: unknown }>
      const loadedModule = await loader()
      expect(loadedModule.default).toBeDefined()
    }

    const viteConfigSource = readFileSync(
      resolve(process.cwd(), 'vite.config.ts'),
      'utf-8',
    )
    expect(viteConfigSource).toContain("minify: 'esbuild'")
    expect(viteConfigSource).toContain('cssMinify: true')
    expect(viteConfigSource).toContain('sourcemap: false')
    expect(viteConfigSource).toContain("'/api'")

    const readmePath = resolve(process.cwd(), 'README.md')
    expect(existsSync(readmePath)).toBe(true)
    expect(readFileSync(readmePath, 'utf-8').trim().length).toBeGreaterThan(100)

    const distAssetsDir = resolve(process.cwd(), 'dist/assets')
    if (existsSync(distAssetsDir)) {
      const files = readdirSync(distAssetsDir)
      expect(files.some((f) => f.endsWith('.map'))).toBe(false)
      expect(files.some((f) => f.startsWith('EventsListView-'))).toBe(true)
      expect(files.some((f) => f.startsWith('LoginPlaceholderView-'))).toBe(true)
      expect(files.some((f) => f.startsWith('AdminPlaceholderView-'))).toBe(true)
    }
  })

  it('AUTH-AC-27 guard redirects unauthenticated to login and returns to original route after login', async () => {
    const authStore = useAuthStore()
    const router = createAppRouter(true)

    await router.push('/profile')
    await router.isReady()

    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.redirect).toBe('/profile')

    authStore.setSession('token-attendee', {
      id: 10,
      email: 'attendee@example.com',
      full_name: 'Ana Pérez',
      role: 'ATTENDEE',
      is_active: true,
      created_at: '2026-10-31T12:00:00Z',
      updated_at: '2026-10-31T12:00:00Z',
    })

    const target = String(router.currentRoute.value.query.redirect || '/')
    await router.push(target)
    expect(router.currentRoute.value.name).toBe('profile')
    expect(router.currentRoute.value.fullPath).toBe('/profile')
  })

  it('AUTH-AC-27 guard redirects role mismatch to home and ignores external redirect targets', async () => {
    const { resolveSafeRedirect } = await import('@/router')
    const authStore = useAuthStore()
    const notificationStore = useNotificationStore()
    const router = createAppRouter(true)

    authStore.setSession('token-organizer', {
      id: 20,
      email: 'org@example.com',
      full_name: 'Organizador',
      role: 'ORGANIZER',
      is_active: true,
      created_at: '2026-10-31T12:00:00Z',
      updated_at: '2026-10-31T12:00:00Z',
    })

    await router.push('/admin/users')
    await router.isReady()

    expect(router.currentRoute.value.name).toBe('home')
    expect(notificationStore.lastMessage).toBe(
      'No tienes permisos para acceder a esta sección',
    )

    expect(resolveSafeRedirect('/profile')).toBe('/profile')
    expect(resolveSafeRedirect('/admin/users?page=2')).toBe(
      '/admin/users?page=2',
    )
    expect(resolveSafeRedirect('https://evil.example.com')).toBe('/')
    expect(resolveSafeRedirect('http://evil.example.com/phish')).toBe('/')
    expect(resolveSafeRedirect('//evil.example.com')).toBe('/')
    expect(resolveSafeRedirect('javascript:alert(1)')).toBe('/')
    expect(resolveSafeRedirect(undefined)).toBe('/')
  })
})

