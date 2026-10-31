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
      role: 'ATTENDEE',
    })

    await router.push('/admin')
    expect(router.currentRoute.value.name).toBe('home')
    expect(notificationStore.lastMessage).toBe(
      'No tienes permisos para acceder a esta sección',
    )

    authStore.setSession('token-admin', {
      id: 1,
      email: 'admin@example.com',
      role: 'ADMIN',
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
      expect(files.some((f) => f.startsWith('HomePlaceholderView-'))).toBe(true)
      expect(files.some((f) => f.startsWith('LoginPlaceholderView-'))).toBe(true)
      expect(files.some((f) => f.startsWith('AdminPlaceholderView-'))).toBe(true)
    }
  })
})

