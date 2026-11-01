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
  SessionRead,
} from '@/types/api'
import ProfileView from '@/views/ProfileView.vue'
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

const mockedFetchMine = vi.mocked(
  registrationsService.fetchMyRegistrationsApi,
)
const mockedFetchEventRegistrations = vi.mocked(
  registrationsService.fetchEventRegistrationsApi,
)
const mockedRegisterEvent = vi.mocked(
  registrationsService.registerForEventApi,
)
const mockedRegisterSession = vi.mocked(
  registrationsService.registerForSessionApi,
)
const mockedCancel = vi.mocked(
  registrationsService.cancelRegistrationApi,
)
const mockedFetchEventById = vi.mocked(eventsService.fetchEventByIdApi)
const mockedFetchSessions = vi.mocked(sessionsService.fetchSessionsApi)

const attendee: AuthUser = {
  id: 7,
  email: 'attendee@example.com',
  full_name: 'Ana Asistente',
  role: 'ATTENDEE',
  is_active: true,
  created_at: '2026-10-31T10:00:00Z',
  updated_at: '2026-10-31T10:00:00Z',
}

const eventRegistration: RegistrationRead = {
  id: 41,
  user_id: 7,
  event_id: 1,
  session_id: null,
  status: 'ACTIVE',
  event: {
    id: 1,
    title: 'Conferencia de Tecnología 2026',
    date: '2026-11-15T14:00:00Z',
    status: 'PUBLISHED',
  },
  session: null,
  created_at: '2026-11-01T10:00:00Z',
  updated_at: '2026-11-01T10:00:00Z',
}

const sessionRegistration: RegistrationRead = {
  ...eventRegistration,
  id: 42,
  session_id: 10,
  session: {
    id: 10,
    title: 'Apertura y bienvenida',
    speaker: 'Ana Torres',
    start_time: '2026-11-15T14:00:00Z',
    end_time: '2026-11-15T15:00:00Z',
  },
  status: 'CANCELLED',
  created_at: '2026-11-01T10:05:00Z',
  updated_at: '2026-11-01T10:05:00Z',
}

const activeSessionRegistration: RegistrationRead = {
  ...sessionRegistration,
  status: 'ACTIVE',
}

const emptyPage: RegistrationListResponse = {
  items: [],
  total: 0,
  page: 1,
  size: 10,
  pages: 0,
}

const dateFormatter = new Intl.DateTimeFormat('es-CO', {
  dateStyle: 'long',
  timeZone: 'UTC',
})

function formatDate(isoDate: string): string {
  return dateFormatter.format(new Date(isoDate))
}

let pinia: Pinia

async function mountProfile() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'home', component: { template: '<div />' } },
      {
        path: '/profile',
        name: 'profile',
        component: { template: '<div />' },
      },
      {
        path: '/login',
        name: 'login',
        component: { template: '<div />' },
      },
    ],
  })
  await router.push('/profile')
  await router.isReady()
  const wrapper = mount(ProfileView, {
    global: { plugins: [pinia, router] },
  })
  await flushPromises()
  return { wrapper, router }
}

describe('ProfileView My registrations section', () => {
  beforeEach(() => {
    pinia = createPinia()
    setActivePinia(pinia)
    window.sessionStorage.clear()
    vi.clearAllMocks()
  })

  it('REG-AC-35 renders My registrations section with pagination and cancellation', async () => {
    const authStore = useAuthStore()
    authStore.setSession('token-attendee', attendee)

    mockedFetchMine.mockResolvedValueOnce({
      items: [sessionRegistration, eventRegistration],
      total: 12,
      page: 1,
      size: 10,
      pages: 2,
    })
    const { wrapper } = await mountProfile()

    expect(mockedFetchMine).toHaveBeenCalledWith({ page: 1, size: 10 })
    expect(
      wrapper.find('[data-testid="registrations-section"]').exists(),
    ).toBe(true)
    expect(wrapper.text()).toContain('Mis inscripciones')
    expect(wrapper.text()).toContain('Conferencia de Tecnología 2026')
    expect(wrapper.text()).toContain('Apertura y bienvenida')
    expect(wrapper.text()).toContain('Activa')
    expect(wrapper.text()).toContain('Cancelada')
    expect(wrapper.text()).toContain(
      formatDate(eventRegistration.event.date),
    )
    expect(wrapper.text()).toContain(
      formatDate(sessionRegistration.event.date),
    )
    expect(
      wrapper.findAll('[data-testid="registration-item"]'),
    ).toHaveLength(2)
    expect(
      wrapper.findAll('[data-testid="registration-cancel-button"]'),
    ).toHaveLength(2)
    expect(
      wrapper.find('[data-testid="registrations-page"]').text(),
    ).toContain('Página 1 de 2')

    mockedFetchMine.mockResolvedValueOnce({
      items: [eventRegistration],
      total: 12,
      page: 2,
      size: 10,
      pages: 2,
    })
    await wrapper
      .find('[data-testid="registrations-next"]')
      .trigger('click')
    await flushPromises()
    expect(mockedFetchMine).toHaveBeenLastCalledWith({
      page: 2,
      size: 10,
    })
    expect(
      wrapper.find('[data-testid="registrations-page"]').text(),
    ).toContain('Página 2 de 2')

    mockedFetchMine.mockResolvedValueOnce({
      items: [sessionRegistration, eventRegistration],
      total: 12,
      page: 1,
      size: 10,
      pages: 2,
    })
    await wrapper
      .find('[data-testid="registrations-prev"]')
      .trigger('click')
    await flushPromises()
    expect(mockedFetchMine).toHaveBeenLastCalledWith({
      page: 1,
      size: 10,
    })

    mockedFetchMine.mockResolvedValueOnce({
      items: [sessionRegistration],
      total: 1,
      page: 1,
      size: 10,
      pages: 1,
    })
    await wrapper
      .find('select#registrations-status-filter')
      .setValue('CANCELLED')
    await flushPromises()
    expect(mockedFetchMine).toHaveBeenLastCalledWith({
      page: 1,
      size: 10,
      status: 'CANCELLED',
    })
    expect(
      wrapper.findAll('[data-testid="registration-item"]'),
    ).toHaveLength(1)

    vi.spyOn(window, 'confirm').mockReturnValueOnce(true)
    mockedCancel.mockResolvedValueOnce(undefined)
    mockedFetchMine.mockResolvedValueOnce({
      items: [sessionRegistration],
      total: 1,
      page: 1,
      size: 10,
      pages: 1,
    })
    await wrapper
      .find('[data-testid="registration-cancel-button"]')
      .trigger('click')
    await flushPromises()
    expect(mockedCancel).toHaveBeenCalledWith(42)
    expect(wrapper.text()).toContain('Inscripción cancelada correctamente.')
    expect(mockedFetchMine).toHaveBeenCalledTimes(5)

    // A rejected confirmation must not call the API.
    vi.spyOn(window, 'confirm').mockReturnValueOnce(false)
    await wrapper
      .find('[data-testid="registration-cancel-button"]')
      .trigger('click')
    await flushPromises()
    expect(mockedCancel).toHaveBeenCalledTimes(1)

    vi.spyOn(window, 'confirm').mockReturnValueOnce(true)
    mockedCancel.mockRejectedValueOnce({
      response: {
        status: 404,
        data: { detail: 'Inscripción no encontrada' },
      },
    })
    await wrapper
      .find('[data-testid="registration-cancel-button"]')
      .trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Inscripción no encontrada')

    mockedFetchMine.mockResolvedValueOnce(emptyPage)
    const emptyView = await mountProfile()
    expect(
      emptyView.wrapper
        .find('[data-testid="registrations-empty"]')
        .text(),
    ).toContain('Todavía no tienes inscripciones.')
    expect(
      emptyView.wrapper
        .findAll('[data-testid="registration-item"]'),
    ).toHaveLength(0)

    mockedFetchMine.mockRejectedValueOnce({
      response: {
        status: 500,
        data: { detail: 'No se pudieron cargar tus inscripciones' },
      },
    })
    const errorView = await mountProfile()
    expect(
      errorView.wrapper
        .find('[data-testid="registrations-error"]')
        .text(),
    ).toContain('No se pudieron cargar tus inscripciones')
    mockedFetchMine.mockResolvedValueOnce(emptyPage)
    await errorView.wrapper
      .find('[data-testid="registrations-retry"]')
      .trigger('click')
    await flushPromises()
    expect(
      errorView.wrapper.find('[data-testid="registrations-error"]').exists(),
    ).toBe(false)
    expect(
      errorView.wrapper.find('[data-testid="registrations-empty"]').exists(),
    ).toBe(true)

    let resolvePending!: (value: RegistrationListResponse) => void
    mockedFetchMine.mockReturnValueOnce(
      new Promise<RegistrationListResponse>((resolve) => {
        resolvePending = resolve
      }),
    )
    const loadingView = await mountProfile()
    expect(
      loadingView.wrapper
        .find('[data-testid="registrations-loading"]')
        .exists(),
    ).toBe(true)
    resolvePending(emptyPage)
    await flushPromises()
    expect(
      loadingView.wrapper
        .find('[data-testid="registrations-loading"]')
        .exists(),
    ).toBe(false)
  })
})

const organizer: AuthUser = {
  id: 2,
  email: 'organizer@example.com',
  full_name: 'Olga Organizadora',
  role: 'ORGANIZER',
  is_active: true,
  created_at: '2026-10-31T10:00:00Z',
  updated_at: '2026-10-31T10:00:00Z',
}

const admin: AuthUser = {
  ...organizer,
  id: 1,
  email: 'admin@example.com',
  full_name: 'Ada Administradora',
  role: 'ADMIN',
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

const openingSession: SessionRead = {
  id: 10,
  event_id: 1,
  title: 'Apertura y bienvenida',
  description: 'Presentación del programa del día.',
  speaker: 'Ana Torres',
  start_time: '2026-11-15T15:00:00Z',
  end_time: '2026-11-15T16:00:00Z',
  capacity: 40,
  registered_count: 5,
  available_capacity: 35,
  created_at: '2026-10-31T18:00:00Z',
  updated_at: '2026-10-31T18:00:00Z',
}

const apiFullSession: SessionRead = {
  ...openingSession,
  id: 11,
  title: 'Sesión sin cupo según la API',
  start_time: '2026-11-15T17:00:00Z',
  end_time: '2026-11-15T18:00:00Z',
  capacity: 40,
  // The API value is authoritative even if the raw numbers suggest room.
  registered_count: 0,
  available_capacity: 0,
}

const apiHasRoomSession: SessionRead = {
  ...openingSession,
  id: 12,
  title: 'Sesión con cupo según la API',
  start_time: '2026-11-15T19:00:00Z',
  end_time: '2026-11-15T20:00:00Z',
  capacity: 10,
  // The API value is authoritative even if the raw numbers look full.
  registered_count: 10,
  available_capacity: 5,
}

async function mountDetail() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'home', component: { template: '<div />' } },
      {
        path: '/events/new',
        name: 'event-create',
        component: { template: '<div />' },
      },
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
  return { wrapper, router }
}

describe('EventDetailView registration actions', () => {
  beforeEach(() => {
    pinia = createPinia()
    setActivePinia(pinia)
    window.sessionStorage.clear()
    vi.clearAllMocks()
    mockedFetchEventById.mockResolvedValue(publishedEvent)
    mockedFetchSessions.mockResolvedValue({
      items: [openingSession],
      total: 1,
    })
    mockedFetchMine.mockResolvedValue(emptyPage)
    mockedFetchEventRegistrations.mockResolvedValue(emptyPage)
  })

  it('REG-AC-36 shows event registration button only for attendees with available capacity', async () => {
    const authStore = useAuthStore()
    authStore.setSession('token-attendee', attendee)

    const { wrapper } = await mountDetail()
    expect(
      wrapper.find('[data-testid="registration-block"]').exists(),
    ).toBe(true)
    const button = wrapper.find('[data-testid="registration-button"]')
    expect(button.exists()).toBe(true)
    expect(button.text()).toContain('Inscribirme')
    expect(button.attributes('disabled')).toBeUndefined()
    expect(
      wrapper.find('[data-testid="registration-full-warning"]').exists(),
    ).toBe(false)
    expect(mockedFetchMine).toHaveBeenCalledWith({
      page: 1,
      size: 50,
      status: 'ACTIVE',
      event_id: 1,
    })

    mockedFetchEventById.mockResolvedValueOnce({
      ...publishedEvent,
      available_capacity: 0,
    })
    const fullView = await mountDetail()
    const fullButton = fullView.wrapper.find(
      '[data-testid="registration-button"]',
    )
    expect(fullButton.attributes('disabled')).toBeDefined()
    expect(
      fullView.wrapper
        .find('[data-testid="registration-full-warning"]')
        .text(),
    ).toContain('No hay cupos disponibles para este evento')

    mockedFetchMine.mockResolvedValueOnce({
      items: [eventRegistration],
      total: 1,
      page: 1,
      size: 50,
      pages: 1,
    })
    const registeredView = await mountDetail()
    expect(registeredView.wrapper.text()).toContain(
      'Ya estás inscrito en este evento',
    )
    expect(
      registeredView.wrapper
        .find('[data-testid="registration-button"]')
        .exists(),
    ).toBe(false)
    expect(
      registeredView.wrapper
        .find('[data-testid="registration-cancel-button"]')
        .exists(),
    ).toBe(true)

    authStore.setSession('token-organizer', organizer)
    const organizerView = await mountDetail()
    expect(
      organizerView.wrapper
        .find('[data-testid="registration-block"]')
        .exists(),
    ).toBe(false)
    expect(organizerView.wrapper.text()).not.toContain('Inscribirme')

    authStore.setSession('token-admin', admin)
    const adminView = await mountDetail()
    expect(
      adminView.wrapper
        .find('[data-testid="registration-block"]')
        .exists(),
    ).toBe(false)

    authStore.clearSession()
    const anonymousView = await mountDetail()
    expect(
      anonymousView.wrapper
        .find('[data-testid="registration-block"]')
        .exists(),
    ).toBe(false)

    authStore.setSession('token-attendee', attendee)
    mockedFetchEventById.mockResolvedValueOnce({
      ...publishedEvent,
      status: 'DRAFT',
    })
    const draftView = await mountDetail()
    expect(
      draftView.wrapper
        .find('[data-testid="registration-block"]')
        .exists(),
    ).toBe(false)
  })

  it('REG-AC-36 refreshes event counters and shows Spanish 409 details after registering', async () => {
    const authStore = useAuthStore()
    authStore.setSession('token-attendee', attendee)

    mockedFetchMine
      .mockResolvedValueOnce(emptyPage)
      .mockResolvedValueOnce({
        items: [eventRegistration],
        total: 1,
        page: 1,
        size: 50,
        pages: 1,
      })
    mockedRegisterEvent.mockResolvedValueOnce({
      registration: eventRegistration,
      created: true,
    })

    const { wrapper } = await mountDetail()
    expect(mockedFetchEventById).toHaveBeenCalledTimes(1)
    expect(mockedFetchSessions).toHaveBeenCalledTimes(1)

    await wrapper
      .find('[data-testid="registration-button"]')
      .trigger('click')
    await flushPromises()

    expect(mockedRegisterEvent).toHaveBeenCalledWith(1)
    expect(mockedFetchEventById).toHaveBeenCalledTimes(2)
    expect(mockedFetchSessions).toHaveBeenCalledTimes(2)
    expect(mockedFetchMine).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('Inscripción realizada correctamente.')
    expect(wrapper.text()).toContain('Ya estás inscrito en este evento')

    mockedFetchMine.mockResolvedValueOnce(emptyPage)
    mockedRegisterEvent.mockRejectedValueOnce({
      response: {
        status: 409,
        data: { detail: 'Ya estás inscrito en este evento' },
      },
    })
    const conflictView = await mountDetail()
    const eventCallsBeforeConflict =
      mockedFetchEventById.mock.calls.length
    await conflictView.wrapper
      .find('[data-testid="registration-button"]')
      .trigger('click')
    await flushPromises()
    expect(conflictView.wrapper.text()).toContain(
      'Ya estás inscrito en este evento',
    )
    expect(mockedFetchEventById.mock.calls.length).toBe(
      eventCallsBeforeConflict,
    )

    mockedFetchMine
      .mockResolvedValueOnce({
        items: [eventRegistration],
        total: 1,
        page: 1,
        size: 50,
        pages: 1,
      })
      .mockResolvedValueOnce(emptyPage)
    vi.spyOn(window, 'confirm').mockReturnValueOnce(true)
    mockedCancel.mockResolvedValueOnce(undefined)
    const cancelView = await mountDetail()
    const eventCallsBeforeCancel = mockedFetchEventById.mock.calls.length
    const sessionCallsBeforeCancel =
      mockedFetchSessions.mock.calls.length
    await cancelView.wrapper
      .find('[data-testid="registration-cancel-button"]')
      .trigger('click')
    await flushPromises()
    expect(mockedCancel).toHaveBeenCalledWith(41)
    expect(mockedFetchEventById.mock.calls.length).toBe(
      eventCallsBeforeCancel + 1,
    )
    expect(mockedFetchSessions.mock.calls.length).toBe(
      sessionCallsBeforeCancel + 1,
    )
    expect(cancelView.wrapper.text()).toContain(
      'Inscripción cancelada correctamente.',
    )
  })

  it('REG-AC-37 registers sessions from the detail and warns when event registration is missing', async () => {
    const authStore = useAuthStore()
    authStore.setSession('token-attendee', attendee)

    mockedFetchSessions.mockResolvedValue({
      items: [openingSession, apiFullSession, apiHasRoomSession],
      total: 3,
    })

    mockedFetchMine.mockResolvedValueOnce(emptyPage)
    const missingView = await mountDetail()
    expect(missingView.wrapper.text()).toContain(
      'Debes inscribirte primero al evento',
    )
    expect(
      missingView.wrapper.findAll(
        '[data-testid="session-register-button"]',
      ),
    ).toHaveLength(0)
    expect(
      missingView.wrapper.findAll(
        '[data-testid="session-register-disabled"]',
      ),
    ).toHaveLength(3)

    mockedFetchMine
      .mockResolvedValueOnce({
        items: [eventRegistration],
        total: 1,
        page: 1,
        size: 50,
        pages: 1,
      })
      .mockResolvedValueOnce({
        items: [eventRegistration, activeSessionRegistration],
        total: 2,
        page: 1,
        size: 50,
        pages: 2,
      })
    mockedRegisterSession.mockResolvedValueOnce({
      registration: activeSessionRegistration,
      created: true,
    })
    const readyView = await mountDetail()
    const buttons = readyView.wrapper.findAll(
      '[data-testid="session-register-button"]',
    )
    expect(buttons).toHaveLength(3)
    expect(buttons[0]?.attributes('disabled')).toBeUndefined()
    expect(buttons[1]?.attributes('disabled')).toBeDefined()
    expect(buttons[2]?.attributes('disabled')).toBeUndefined()
    expect(
      readyView.wrapper
        .find('[data-testid="session-full-warning"]')
        .text(),
    ).toContain('No hay cupos disponibles para esta sesión')
    expect(readyView.wrapper.text()).not.toContain(
      'Debes inscribirte primero al evento',
    )

    const sessionCallsBeforeRegister =
      mockedFetchSessions.mock.calls.length
    await buttons[0]?.trigger('click')
    await flushPromises()

    expect(mockedRegisterSession).toHaveBeenCalledWith(1, 10)
    expect(mockedFetchSessions.mock.calls.length).toBe(
      sessionCallsBeforeRegister + 1,
    )
    expect(mockedFetchMine).toHaveBeenCalledTimes(3)
    expect(readyView.wrapper.text()).toContain(
      'Inscripción a la sesión realizada correctamente.',
    )

    mockedFetchMine.mockResolvedValueOnce({
      items: [eventRegistration, activeSessionRegistration],
      total: 2,
      page: 1,
      size: 50,
      pages: 2,
    })
    const alreadyView = await mountDetail()
    expect(alreadyView.wrapper.text()).toContain(
      'Ya estás inscrito',
    )
    expect(
      alreadyView.wrapper.findAll(
        '[data-testid="session-register-button"]',
      ),
    ).toHaveLength(2)

    mockedFetchMine.mockResolvedValueOnce({
      items: [eventRegistration],
      total: 1,
      page: 1,
      size: 50,
      pages: 1,
    })
    mockedRegisterSession.mockRejectedValueOnce({
      response: {
        status: 409,
        data: {
          detail: 'No hay cupos disponibles para esta sesión',
        },
      },
    })
    const conflictView = await mountDetail()
    await conflictView.wrapper
      .findAll('[data-testid="session-register-button"]')[0]
      ?.trigger('click')
    await flushPromises()
    expect(conflictView.wrapper.text()).toContain(
      'No hay cupos disponibles para esta sesión',
    )
  })
})
