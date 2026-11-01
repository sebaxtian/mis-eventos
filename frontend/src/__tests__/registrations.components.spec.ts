import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import type {
  AuthUser,
  EventRead,
  RegistrationListResponse,
  RegistrationRead,
  SessionListResponse,
} from '@/types/api'
import EventRegistrationsList from '@/components/registrations/EventRegistrationsList.vue'
import EventDetailView from '@/views/EventDetailView.vue'
import { useAuthStore } from '@/stores/auth'
import * as registrationsService from '@/services/registrations'
import * as eventsService from '@/services/events'
import * as sessionsService from '@/services/sessions'

vi.mock('@/services/registrations', () => ({
  fetchMyRegistrationsApi: vi.fn(),
  fetchEventRegistrationsApi: vi.fn(),
  fetchRegistrationByIdApi: vi.fn(),
  registerForEventApi: vi.fn(),
  registerForSessionApi: vi.fn(),
  cancelRegistrationApi: vi.fn(),
}))

vi.mock('@/services/events', () => ({
  fetchEventsApi: vi.fn(),
  fetchEventByIdApi: vi.fn(),
  createEventApi: vi.fn(),
  updateEventApi: vi.fn(),
  deleteEventApi: vi.fn(),
  uploadEventImageApi: vi.fn(),
}))

vi.mock('@/services/sessions', () => ({
  fetchSessionsApi: vi.fn(),
  fetchSessionByIdApi: vi.fn(),
  createSessionApi: vi.fn(),
  updateSessionApi: vi.fn(),
  deleteSessionApi: vi.fn(),
}))

const mockedFetchEventRegistrations = vi.mocked(
  registrationsService.fetchEventRegistrationsApi,
)
const mockedFetchMine = vi.mocked(
  registrationsService.fetchMyRegistrationsApi,
)
const mockedFetchEventById = vi.mocked(eventsService.fetchEventByIdApi)
const mockedFetchSessions = vi.mocked(sessionsService.fetchSessionsApi)

const admin: AuthUser = {
  id: 1,
  email: 'admin@example.com',
  full_name: 'Ada Administradora',
  role: 'ADMIN',
  is_active: true,
  created_at: '2026-10-31T10:00:00Z',
  updated_at: '2026-10-31T10:00:00Z',
}

const registrationA: RegistrationRead = {
  id: 41,
  user_id: 7,
  event_id: 5,
  session_id: null,
  status: 'ACTIVE',
  event: {
    id: 5,
    title: 'Conferencia de Tecnología 2026',
    date: '2026-11-15T14:00:00Z',
    status: 'PUBLISHED',
  },
  session: null,
  created_at: '2026-11-01T10:00:00Z',
  updated_at: '2026-11-01T10:00:00Z',
}

const registrationB: RegistrationRead = {
  ...registrationA,
  id: 42,
  user_id: 8,
  status: 'CANCELLED',
  created_at: '2026-11-02T11:30:00Z',
  updated_at: '2026-11-02T11:30:00Z',
}

const emptyPage: RegistrationListResponse = {
  items: [],
  total: 0,
  page: 1,
  size: 10,
  pages: 0,
}

const dateFormatter = new Intl.DateTimeFormat('es-CO', {
  dateStyle: 'medium',
  timeStyle: 'short',
  timeZone: 'UTC',
})

function formatDate(isoDate: string): string {
  return dateFormatter.format(new Date(isoDate))
}

let pinia: Pinia

function mountList(props = { eventId: 5, canManage: true }) {
  return mount(EventRegistrationsList, {
    props,
    global: { plugins: [pinia] },
  })
}

describe('EventRegistrationsList privacy, pagination and lazy loading', () => {
  beforeEach(() => {
    pinia = createPinia()
    setActivePinia(pinia)
    window.sessionStorage.clear()
    vi.clearAllMocks()
    mockedFetchEventRegistrations.mockResolvedValue(emptyPage)
    mockedFetchMine.mockResolvedValue(emptyPage)
  })

  it('REG-AC-38 renders lazy event registrations list with user_id and status filter', async () => {
    mockedFetchEventRegistrations.mockResolvedValueOnce({
      items: [registrationA, registrationB],
      total: 12,
      page: 1,
      size: 10,
      pages: 2,
    })

    const wrapper = mountList()
    await flushPromises()

    expect(mockedFetchEventRegistrations).toHaveBeenCalledWith(5, {
      page: 1,
      size: 10,
    })
    expect(
      wrapper.find('[data-testid="event-registrations"]').exists(),
    ).toBe(true)
    expect(
      wrapper.findAll('[data-testid="event-registration-row"]'),
    ).toHaveLength(2)
    expect(wrapper.text()).toContain('Usuario #7')
    expect(wrapper.text()).toContain('Usuario #8')
    expect(wrapper.text()).toContain('Activa')
    expect(wrapper.text()).toContain('Cancelada')
    expect(wrapper.text()).toContain(formatDate(registrationA.created_at))
    expect(wrapper.text()).toContain(formatDate(registrationB.created_at))
    expect(wrapper.text()).not.toContain('full_name')
    expect(wrapper.text()).not.toContain('email')
    expect(wrapper.text()).not.toContain('password_hash')
    expect(wrapper.text()).not.toContain('Ana Asistente')
    expect(
      wrapper.find('[data-testid="event-registrations-page"]').text(),
    ).toContain('Página 1 de 2')

    mockedFetchEventRegistrations.mockResolvedValueOnce({
      items: [registrationB],
      total: 12,
      page: 2,
      size: 10,
      pages: 2,
    })
    await wrapper
      .find('[data-testid="event-registrations-next"]')
      .trigger('click')
    await flushPromises()
    expect(mockedFetchEventRegistrations).toHaveBeenLastCalledWith(5, {
      page: 2,
      size: 10,
    })
    expect(
      wrapper.find('[data-testid="event-registrations-page"]').text(),
    ).toContain('Página 2 de 2')

    mockedFetchEventRegistrations.mockResolvedValueOnce({
      items: [registrationA, registrationB],
      total: 12,
      page: 1,
      size: 10,
      pages: 2,
    })
    await wrapper
      .find('[data-testid="event-registrations-prev"]')
      .trigger('click')
    await flushPromises()
    expect(mockedFetchEventRegistrations).toHaveBeenLastCalledWith(5, {
      page: 1,
      size: 10,
    })

    mockedFetchEventRegistrations.mockResolvedValueOnce({
      items: [registrationB],
      total: 1,
      page: 1,
      size: 10,
      pages: 1,
    })
    await wrapper
      .find('select#event-registrations-status-filter')
      .setValue('CANCELLED')
    await flushPromises()
    expect(mockedFetchEventRegistrations).toHaveBeenLastCalledWith(5, {
      page: 1,
      size: 10,
      status: 'CANCELLED',
    })
    expect(
      wrapper.findAll('[data-testid="event-registration-row"]'),
    ).toHaveLength(1)

    mockedFetchEventRegistrations.mockResolvedValueOnce(emptyPage)
    await wrapper.setProps({ eventId: 6 })
    await flushPromises()
    expect(mockedFetchEventRegistrations).toHaveBeenLastCalledWith(6, {
      page: 1,
      size: 10,
    })

    const hidden = mountList({ eventId: 5, canManage: false })
    await flushPromises()
    expect(
      hidden.find('[data-testid="event-registrations"]').exists(),
    ).toBe(false)

    mockedFetchEventRegistrations.mockResolvedValueOnce(emptyPage)
    const emptyView = mountList()
    await flushPromises()
    expect(
      emptyView
        .find('[data-testid="event-registrations-empty"]')
        .text(),
    ).toContain('Todavía no hay inscripciones a este evento.')
    expect(
      emptyView.findAll('[data-testid="event-registration-row"]'),
    ).toHaveLength(0)

    mockedFetchEventRegistrations.mockRejectedValueOnce({
      response: {
        status: 500,
        data: {
          detail: 'No se pudieron cargar las inscripciones del evento',
        },
      },
    })
    const errorView = mountList()
    await flushPromises()
    expect(
      errorView
        .find('[data-testid="event-registrations-error"]')
        .text(),
    ).toContain('No se pudieron cargar las inscripciones del evento')
    mockedFetchEventRegistrations.mockResolvedValueOnce(emptyPage)
    await errorView
      .find('[data-testid="event-registrations-retry"]')
      .trigger('click')
    await flushPromises()
    expect(
      errorView
        .find('[data-testid="event-registrations-error"]')
        .exists(),
    ).toBe(false)

    let resolvePending!: (value: RegistrationListResponse) => void
    mockedFetchEventRegistrations.mockReturnValueOnce(
      new Promise<RegistrationListResponse>((resolve) => {
        resolvePending = resolve
      }),
    )
    const loadingView = mountList()
    await flushPromises()
    expect(
      loadingView
        .find('[data-testid="event-registrations-loading"]')
        .exists(),
    ).toBe(true)
    resolvePending(emptyPage)
    await flushPromises()
    expect(
      loadingView
        .find('[data-testid="event-registrations-loading"]')
        .exists(),
    ).toBe(false)
  })

  it('REG-AC-38 lazy-loads EventRegistrationsList and keeps registration views free of v-html', async () => {
    const detailSource = readFileSync(
      resolve(process.cwd(), 'src/views/EventDetailView.vue'),
      'utf-8',
    )
    expect(detailSource).toContain('defineAsyncComponent')
    expect(detailSource).toContain(
      "import('@/components/registrations/EventRegistrationsList.vue')",
    )
    expect(detailSource).toContain('BaseSpinner')
    expect(detailSource).toContain('loadingComponent')
    expect(detailSource).not.toMatch(
      /import EventRegistrationsList from '@\/components\/registrations\/EventRegistrationsList\.vue'/,
    )

    for (const file of [
      'src/views/EventDetailView.vue',
      'src/views/ProfileView.vue',
      'src/components/registrations/EventRegistrationsList.vue',
    ]) {
      const source = readFileSync(
        resolve(process.cwd(), file),
        'utf-8',
      )
      expect(source).not.toContain('v-html')
    }

    const publishedEvent: EventRead = {
      id: 1,
      title: 'Conferencia Python Colombia',
      description: 'Encuentro anual de desarrollo con FastAPI y Vue.',
      date: '2026-11-15T14:00:00Z',
      total_capacity: 100,
      registered_count: 25,
      available_capacity: 75,
      status: 'PUBLISHED',
      organizer_id: 2,
      image_urls: null,
      created_at: '2026-10-31T15:00:00Z',
      updated_at: '2026-10-31T15:05:00Z',
    }
    const sessionsResponse: SessionListResponse = {
      items: [],
      total: 0,
    }
    mockedFetchEventById.mockResolvedValue(publishedEvent)
    mockedFetchSessions.mockResolvedValue(sessionsResponse)

    const authStore = useAuthStore()
    authStore.setSession('token-admin', admin)
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', name: 'home', component: { template: '<div />' } },
        {
          path: '/events/:id',
          name: 'event-detail',
          component: { template: '<div />' },
        },
        {
          path: '/events/:id/edit',
          name: 'event-edit',
          component: { template: '<div />' },
        },
      ],
    })
    await router.push('/events/1')
    await router.isReady()
    const wrapper = mount(EventDetailView, {
      global: { plugins: [pinia, router] },
    })
    await flushPromises()

    await vi.waitFor(() => {
      if (
        !wrapper.find('[data-testid="event-registrations"]').exists()
      ) {
        throw new Error('Event registrations list not loaded')
      }
    })
    expect(
      wrapper.find('[data-testid="event-registrations"]').exists(),
    ).toBe(true)
    expect(mockedFetchEventRegistrations).toHaveBeenCalledWith(1, {
      page: 1,
      size: 10,
    })
  })
})
