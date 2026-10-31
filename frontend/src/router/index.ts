import {
  createMemoryHistory,
  createRouter,
  createWebHistory,
  type RouteRecordRaw,
  type Router,
} from 'vue-router'
import type { UserRole } from '@/types/api'
import { useAuthStore } from '@/stores/auth'
import { useNotificationStore } from '@/stores/notification'

declare module 'vue-router' {
  interface RouteMeta {
    requiresAuth?: boolean
    roles?: UserRole[]
  }
}

export const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'home',
    component: () => import('@/views/HomePlaceholderView.vue'),
  },
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginPlaceholderView.vue'),
  },
  {
    path: '/admin',
    name: 'admin',
    component: () => import('@/views/AdminPlaceholderView.vue'),
    meta: {
      requiresAuth: true,
      roles: ['ADMIN'],
    },
  },
]

export function registerNavigationGuards(routerInstance: Router): Router {
  routerInstance.beforeEach((to) => {
    const authStore = useAuthStore()
    const notificationStore = useNotificationStore()

    if (to.meta.requiresAuth && !authStore.isAuthenticated) {
      return {
        name: 'login',
        query: { redirect: to.fullPath },
      }
    }

    if (
      to.meta.roles &&
      to.meta.roles.length > 0 &&
      (!authStore.role || !to.meta.roles.includes(authStore.role))
    ) {
      notificationStore.notify(
        'No tienes permisos para acceder a esta sección',
        'warning',
      )
      return { name: 'home' }
    }

    return true
  })

  return routerInstance
}

export function createAppRouter(useMemory = false): Router {
  const instance = createRouter({
    history: useMemory ? createMemoryHistory() : createWebHistory(),
    routes,
  })
  return registerNavigationGuards(instance)
}

const router = createAppRouter()

export default router
