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
    component: () => import('@/views/EventsListView.vue'),
  },
  {
    path: '/events/new',
    name: 'event-create',
    component: () => import('@/views/EventFormView.vue'),
    meta: {
      requiresAuth: true,
      roles: ['ORGANIZER', 'ADMIN'],
    },
  },
  {
    path: '/events/:id',
    name: 'event-detail',
    component: () => import('@/views/EventDetailView.vue'),
  },
  {
    path: '/events/:id/edit',
    name: 'event-edit',
    component: () => import('@/views/EventFormView.vue'),
    meta: {
      requiresAuth: true,
      roles: ['ORGANIZER', 'ADMIN'],
    },
  },
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
  },
  {
    path: '/register',
    name: 'register',
    component: () => import('@/views/RegisterView.vue'),
  },
  {
    path: '/profile',
    name: 'profile',
    component: () => import('@/views/ProfileView.vue'),
    meta: {
      requiresAuth: true,
    },
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
  {
    path: '/admin/users',
    name: 'admin-users',
    component: () => import('@/views/AdminUsersView.vue'),
    meta: {
      requiresAuth: true,
      roles: ['ADMIN'],
    },
  },
  {
    path: '/_placeholder/login',
    name: 'login-placeholder',
    component: () => import('@/views/LoginPlaceholderView.vue'),
  },
]

export function resolveSafeRedirect(rawRedirect: unknown): string {
  if (typeof rawRedirect !== 'string') return '/'
  const trimmed = rawRedirect.trim()
  if (!trimmed.startsWith('/') || trimmed.startsWith('//')) {
    return '/'
  }
  return trimmed
}

export function registerNavigationGuards(routerInstance: Router): Router {
  routerInstance.beforeEach((to) => {
    const authStore = useAuthStore()
    const notificationStore = useNotificationStore()

    const evaluateGuard = () => {
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
    }

    if (!authStore.initialized) {
      return authStore.initialize().then(() => evaluateGuard())
    }

    return evaluateGuard()
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
