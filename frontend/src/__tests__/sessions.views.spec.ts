import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import type {
  AuthUser,
  EventRead,
  SessionListResponse,
  SessionRead,
} from '@/types/api'
import EventDetailView from '@/views/EventDetailView.vue'
import { useAuthStore } from '@/stores/auth'
import * as eventsService from '@/services/events'
import * as sessionsService from '@/services/sessions'

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

const mockedFetchEventById = vi.mocked(eventsService.fetchEventByIdApi)
const mockedFetchSessions = vi.mocked(sessionsService.fetchSessionsApi)
const mockedCreateSession = vi.mocked(sessionsService.createSessionApi)
const mockedUpdateSession = vi.mocked(sessionsService.updateSessionApi)
const mockedDeleteSession = vi.mocked(sessionsService.deleteSessionApi)

const organizer: AuthUser = {
  id: 2,
  email: 'organizer@example.com',
  full_name: 'Olga Organizadora',
  role: 'ORGANIZER',
  is_active: true,
  created_at: '2026-10-31T10:00:00Z',
  updated_at: '2026-10-31T10:00:00Z',
}

const attendee: AuthUser = {
  ...organizer,
  id: 3,
  email: 'attendee@example.com',
  full_name: 'Ana Asistente',
  role: 'ATTENDEE',
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
  capacity: 100,
  registered_count: 25,
  // API value deliberately differs from capacity - registered (75) to prove
  // the view never recomputes capacity on the client (R2.5).
  available_capacity: 60,
  created_at: '2026-10-31T18:00:00Z',
  updated_at: '2026-10-31T18:00:00Z',
}

const workshopSession: SessionRead = {
  ...openingSession,
  id: 11,
  title: 'Taller de FastAPI',
  description: null,
  speaker: 'Luis Gómez',
  start_time: '2026-11-15T17:00:00Z',
  end_time: '2026-11-15T18:30:00Z',
  capacity: 40,
  registered_count: 0,
  available_capacity: 40,
}

function emptySessions(): SessionListResponse {
  return { items: [], total: 0 }
}

let pinia: Pinia

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

describe('EventDetailView agenda integration and session permissions', () => {
  beforeEach(() => {
    pinia = createPinia()
    setActivePinia(pinia)
    window.sessionStorage.clear()
    vi.clearAllMocks()
    mockedFetchSessions.mockResolvedValue(emptySessions())
  })

  it('SES-AC-27 composes EventDetailView with event and sessions calls and loading state', async () => {
    const authStore = useAuthStore()
    authStore.setSession('token-organizer', organizer)

    mockedFetchEventById.mockResolvedValueOnce(publishedEvent)
    let resolveSessions!: (value: SessionListResponse) => void
    mockedFetchSessions.mockReturnValueOnce(
      new Promise<SessionListResponse>((resolve) => {
        resolveSessions = resolve
      }),
    )

    const { wrapper } = await mountDetail()

    expect(mockedFetchEventById).toHaveBeenCalledWith(1)
    expect(mockedFetchSessions).toHaveBeenCalledWith(1)
    expect(mockedFetchEventById).toHaveBeenCalledTimes(1)
    expect(mockedFetchSessions).toHaveBeenCalledTimes(1)

    expect(wrapper.find('[data-testid="detail-loading"]').exists()).toBe(
      false,
    )
    expect(
      wrapper.find('[data-testid="session-agenda"]').exists(),
    ).toBe(true)
    expect(
      wrapper.find('[data-testid="sessions-loading"]').exists(),
    ).toBe(true)

    resolveSessions({ items: [workshopSession, openingSession], total: 2 })
    await flushPromises()

    expect(
      wrapper.find('[data-testid="sessions-loading"]').exists(),
    ).toBe(false)
    expect(
      wrapper.find('[data-testid="sessions-error"]').exists(),
    ).toBe(false)

    const items = wrapper.findAll('[data-testid="session-item"]')
    expect(items).toHaveLength(2)
    expect(items[0]?.text()).toContain('Apertura y bienvenida')
    expect(items[0]?.text()).toContain('Ana Torres')
    expect(items[0]?.text()).toContain('15:00')
    expect(items[0]?.text()).toContain('60')
    expect(items[0]?.text()).not.toContain('75')
    expect(items[1]?.text()).toContain('Taller de FastAPI')

    // No duplicated requests while mounting.
    expect(mockedFetchEventById).toHaveBeenCalledTimes(1)
    expect(mockedFetchSessions).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain(publishedEvent.title)
  })

  it('SES-AC-28 hides session write controls for non-owners and cancelled events', async () => {
    const authStore = useAuthStore()

    authStore.setSession('token-organizer', organizer)
    mockedFetchEventById.mockResolvedValueOnce(publishedEvent)
    mockedFetchSessions.mockResolvedValueOnce({
      items: [openingSession],
      total: 1,
    })
    const ownerView = await mountDetail()
    expect(
      ownerView.wrapper
        .find('[data-testid="session-add-button"]')
        .exists(),
    ).toBe(true)
    expect(
      ownerView.wrapper.find('[data-testid="session-form"]').exists(),
    ).toBe(false)
    expect(
      ownerView.wrapper
        .find('[data-testid="session-edit-button"]')
        .exists(),
    ).toBe(true)
    expect(
      ownerView.wrapper
        .find('[data-testid="session-delete-button"]')
        .exists(),
    ).toBe(true)

    await ownerView.wrapper
      .find('[data-testid="session-add-button"]')
      .trigger('click')
    await vi.waitFor(() => {
      if (
        !ownerView.wrapper.find('[data-testid="session-form"]').exists()
      ) {
        throw new Error('Session form not ready')
      }
    })
    expect(
      ownerView.wrapper.find('[data-testid="session-form"]').exists(),
    ).toBe(true)

    authStore.setSession('token-attendee', attendee)
    mockedFetchEventById.mockResolvedValueOnce(publishedEvent)
    mockedFetchSessions.mockResolvedValueOnce({
      items: [openingSession],
      total: 1,
    })
    const attendeeView = await mountDetail()
    expect(
      attendeeView.wrapper
        .find('[data-testid="session-add-button"]')
        .exists(),
    ).toBe(false)
    expect(
      attendeeView.wrapper
        .find('[data-testid="session-edit-button"]')
        .exists(),
    ).toBe(false)
    expect(
      attendeeView.wrapper
        .find('[data-testid="session-delete-button"]')
        .exists(),
    ).toBe(false)
    expect(
      attendeeView.wrapper.find('[data-testid="session-form"]').exists(),
    ).toBe(false)

    authStore.setSession('token-other-organizer', {
      ...organizer,
      id: 99,
      email: 'otro@example.com',
    })
    mockedFetchEventById.mockResolvedValueOnce(publishedEvent)
    mockedFetchSessions.mockResolvedValueOnce({
      items: [openingSession],
      total: 1,
    })
    const otherOrganizerView = await mountDetail()
    expect(
      otherOrganizerView.wrapper
        .find('[data-testid="session-add-button"]')
        .exists(),
    ).toBe(false)
    expect(
      otherOrganizerView.wrapper
        .find('[data-testid="session-form"]')
        .exists(),
    ).toBe(false)

    authStore.setSession('token-organizer', organizer)
    mockedFetchEventById.mockResolvedValueOnce({
      ...publishedEvent,
      status: 'CANCELLED',
    })
    mockedFetchSessions.mockResolvedValueOnce({
      items: [openingSession],
      total: 1,
    })
    const cancelledView = await mountDetail()
    expect(
      cancelledView.wrapper
        .find('[data-testid="session-add-button"]')
        .exists(),
    ).toBe(false)
    expect(
      cancelledView.wrapper
        .find('[data-testid="session-edit-button"]')
        .exists(),
    ).toBe(false)
    expect(
      cancelledView.wrapper
        .find('[data-testid="session-delete-button"]')
        .exists(),
    ).toBe(false)
    expect(
      cancelledView.wrapper.find('[data-testid="session-form"]').exists(),
    ).toBe(false)
    expect(
      cancelledView.wrapper
        .find('[data-testid="sessions-cancelled-warning"]')
        .exists(),
    ).toBe(true)
    expect(cancelledView.wrapper.text()).toContain(
      'Un evento cancelado no permite modificar sus sesiones',
    )

    authStore.setSession('token-admin', admin)
    mockedFetchEventById.mockResolvedValueOnce(publishedEvent)
    mockedFetchSessions.mockResolvedValueOnce({
      items: [openingSession],
      total: 1,
    })
    const adminView = await mountDetail()
    expect(
      adminView.wrapper
        .find('[data-testid="session-add-button"]')
        .exists(),
    ).toBe(true)
  })

  it('SES-AC-28 loads SessionForm lazily with defineAsyncComponent', async () => {
    const source = readFileSync(
      resolve(process.cwd(), 'src/views/EventDetailView.vue'),
      'utf-8',
    )
    expect(source).toContain('defineAsyncComponent')
    expect(source).toContain(
      "import('@/components/sessions/SessionForm.vue')",
    )
    expect(source).toContain('BaseSpinner')
    expect(source).toContain('loadingComponent')
    expect(source).not.toMatch(
      /import SessionForm from '@\/components\/sessions\/SessionForm\.vue'/,
    )

    const authStore = useAuthStore()
    authStore.setSession('token-organizer', organizer)
    mockedFetchEventById.mockResolvedValueOnce(publishedEvent)
    mockedFetchSessions.mockResolvedValueOnce({
      items: [openingSession],
      total: 1,
    })

    const { wrapper } = await mountDetail()

    expect(
      wrapper.find('[data-testid="session-form"]').exists(),
    ).toBe(false)

    await wrapper.find('[data-testid="session-add-button"]').trigger('click')
    await vi.waitFor(() => {
      if (!wrapper.find('[data-testid="session-form"]').exists()) {
        throw new Error('Session form not ready')
      }
    })

    expect(
      wrapper.find('[data-testid="session-form"]').exists(),
    ).toBe(true)
  })

  it('SES-AC-27 shows skeletons and Spanish alerts while sessions load or fail', async () => {
    const authStore = useAuthStore()
    authStore.setSession('token-attendee', attendee)

    mockedFetchEventById.mockResolvedValueOnce(publishedEvent)
    mockedFetchSessions.mockRejectedValueOnce({
      response: {
        status: 409,
        data: {
          detail: 'La sesión se solapa con otra sesión del evento',
        },
      },
    })
    const conflictView = await mountDetail()
    expect(
      conflictView.wrapper
        .find('[data-testid="sessions-error"]')
        .exists(),
    ).toBe(true)
    expect(conflictView.wrapper.text()).toContain(
      'La sesión se solapa con otra sesión del evento',
    )
    expect(
      conflictView.wrapper
        .find('[data-testid="sessions-retry"]')
        .exists(),
    ).toBe(true)

    let resolveRetry!: (value: SessionListResponse) => void
    mockedFetchSessions.mockReturnValueOnce(
      new Promise<SessionListResponse>((resolve) => {
        resolveRetry = resolve
      }),
    )
    await conflictView.wrapper
      .find('[data-testid="sessions-retry"]')
      .trigger('click')
    await flushPromises()

    expect(
      conflictView.wrapper
        .find('[data-testid="sessions-error"]')
        .exists(),
    ).toBe(false)
    expect(
      conflictView.wrapper
        .find('[data-testid="sessions-loading"]')
        .exists(),
    ).toBe(true)

    resolveRetry({ items: [openingSession], total: 1 })
    await flushPromises()

    expect(
      conflictView.wrapper
        .find('[data-testid="sessions-loading"]')
        .exists(),
    ).toBe(false)
    expect(
      conflictView.wrapper.findAll('[data-testid="session-item"]'),
    ).toHaveLength(1)
    expect(mockedFetchSessions).toHaveBeenCalledTimes(2)

    mockedFetchEventById.mockResolvedValueOnce(publishedEvent)
    mockedFetchSessions.mockRejectedValueOnce({
      response: {
        status: 422,
        data: {
          detail: 'Error de validación en los datos enviados',
          errors: [
            {
              field: 'event_id',
              message: 'El valor debe ser un número entero válido',
            },
          ],
        },
      },
    })
    const invalidView = await mountDetail()
    expect(
      invalidView.wrapper
        .find('[data-testid="sessions-error"]')
        .exists(),
    ).toBe(true)
    expect(invalidView.wrapper.text()).toContain(
      'Error de validación en los datos enviados',
    )
    expect(invalidView.wrapper.text()).toContain(
      'El valor debe ser un número entero válido',
    )

    mockedFetchEventById.mockRejectedValueOnce({
      response: {
        status: 404,
        data: { detail: 'Evento no encontrado' },
      },
    })
    mockedFetchSessions.mockRejectedValueOnce({
      response: {
        status: 404,
        data: { detail: 'Evento no encontrado' },
      },
    })
    const missingView = await mountDetail()
    expect(missingView.wrapper.text()).toContain('Evento no encontrado')
  })

  it('SES-AC-28 manages session create, edit and delete flows from the detail view', async () => {
    const authStore = useAuthStore()
    authStore.setSession('token-organizer', organizer)

    mockedFetchEventById.mockResolvedValueOnce(publishedEvent)
    mockedFetchSessions.mockResolvedValueOnce({
      items: [openingSession],
      total: 1,
    })

    const { wrapper } = await mountDetail()

    await wrapper.find('[data-testid="session-edit-button"]').trigger('click')
    await vi.waitFor(() => {
      if (!wrapper.find('[data-testid="session-form"]').exists()) {
        throw new Error('Session form not ready')
      }
    })
    const titleInput = wrapper.find('input#session-title')
    expect((titleInput.element as HTMLInputElement).value).toBe(
      openingSession.title,
    )

    const updatedSession = {
      ...openingSession,
      title: 'Apertura actualizada',
    }
    mockedUpdateSession.mockResolvedValueOnce(updatedSession)
    mockedFetchSessions.mockResolvedValueOnce({
      items: [updatedSession],
      total: 1,
    })
    await titleInput.setValue('Apertura actualizada')
    await wrapper
      .find('form[data-testid="session-form"]')
      .trigger('submit.prevent')
    await vi.waitFor(() => {
      if (mockedUpdateSession.mock.calls.length === 0) {
        throw new Error('Update not called')
      }
    })
    await flushPromises()

    expect(mockedUpdateSession).toHaveBeenCalledWith(
      1,
      openingSession.id,
      expect.objectContaining({ title: 'Apertura actualizada' }),
    )
    expect(wrapper.text()).toContain('Sesión actualizada correctamente.')
    expect(
      wrapper.find('[data-testid="session-form"]').exists(),
    ).toBe(false)

    mockedCreateSession.mockResolvedValueOnce(workshopSession)
    mockedFetchSessions.mockResolvedValueOnce({
      items: [openingSession, workshopSession],
      total: 2,
    })
    await wrapper.find('[data-testid="session-add-button"]').trigger('click')
    await vi.waitFor(() => {
      if (!wrapper.find('[data-testid="session-form"]').exists()) {
        throw new Error('Session form not ready')
      }
    })
    await wrapper.find('input#session-title').setValue('Taller de FastAPI')
    await wrapper
      .find('input#session-speaker')
      .setValue('Luis Gómez')
    await wrapper
      .find('input#session-start-time')
      .setValue('2026-11-15T17:00')
    await wrapper
      .find('input#session-end-time')
      .setValue('2026-11-15T18:30')
    await wrapper.find('input#session-capacity').setValue('40')
    await wrapper
      .find('form[data-testid="session-form"]')
      .trigger('submit.prevent')
    await vi.waitFor(() => {
      if (mockedCreateSession.mock.calls.length === 0) {
        throw new Error('Create not called')
      }
    })
    await flushPromises()

    expect(mockedCreateSession).toHaveBeenCalledWith(
      1,
      expect.objectContaining({
        title: 'Taller de FastAPI',
        speaker: 'Luis Gómez',
        capacity: 40,
      }),
    )
    expect(wrapper.text()).toContain('Sesión creada correctamente.')

    await wrapper.find('[data-testid="session-add-button"]').trigger('click')
    await vi.waitFor(() => {
      if (!wrapper.find('[data-testid="session-form"]').exists()) {
        throw new Error('Session form not ready')
      }
    })
    const cancelButton = wrapper
      .findAll('button')
      .find((button) => button.text() === 'Cancelar')
    expect(cancelButton).toBeTruthy()
    await cancelButton?.trigger('click')
    expect(
      wrapper.find('[data-testid="session-form"]').exists(),
    ).toBe(false)

    vi.spyOn(window, 'confirm').mockReturnValueOnce(true)
    mockedDeleteSession.mockResolvedValueOnce(undefined)
    mockedFetchSessions.mockResolvedValueOnce({
      items: [workshopSession],
      total: 1,
    })
    await wrapper
      .findAll('[data-testid="session-delete-button"]')[0]
      ?.trigger('click')
    await vi.waitFor(() => {
      if (mockedDeleteSession.mock.calls.length === 0) {
        throw new Error('Delete not called')
      }
    })
    await flushPromises()

    expect(mockedDeleteSession).toHaveBeenCalledWith(
      1,
      openingSession.id,
    )
    expect(wrapper.text()).toContain('Sesión eliminada correctamente.')

    mockedCreateSession.mockRejectedValueOnce({
      response: {
        status: 409,
        data: {
          detail: 'La sesión se solapa con otra sesión del evento',
        },
      },
    })
    await wrapper.find('[data-testid="session-add-button"]').trigger('click')
    await vi.waitFor(() => {
      if (!wrapper.find('[data-testid="session-form"]').exists()) {
        throw new Error('Session form not ready')
      }
    })
    await wrapper.find('input#session-title').setValue('Sesión solapada')
    await wrapper.find('input#session-speaker').setValue('Ana Torres')
    await wrapper
      .find('input#session-start-time')
      .setValue('2026-11-15T17:00')
    await wrapper
      .find('input#session-end-time')
      .setValue('2026-11-15T18:00')
    await wrapper.find('input#session-capacity').setValue('20')
    await wrapper
      .find('form[data-testid="session-form"]')
      .trigger('submit.prevent')
    await vi.waitFor(() => {
      if (mockedCreateSession.mock.calls.length < 2) {
        throw new Error('Create not called')
      }
    })
    await flushPromises()

    expect(wrapper.text()).toContain(
      'La sesión se solapa con otra sesión del evento',
    )
    expect(
      wrapper.find('[data-testid="session-form"]').exists(),
    ).toBe(true)
  })
})
