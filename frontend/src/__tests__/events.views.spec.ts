import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import type {
  AuthUser,
  EventListResponse,
  EventRead,
} from '@/types/api'
import { createAppRouter, routes } from '@/router'
import { useAuthStore } from '@/stores/auth'
import { useNotificationStore } from '@/stores/notification'
import EventsListView from '@/views/EventsListView.vue'
import EventDetailView from '@/views/EventDetailView.vue'
import EventFormView from '@/views/EventFormView.vue'
import * as eventsService from '@/services/events'
import * as sessionsService from '@/services/sessions'
import * as registrationsService from '@/services/registrations'

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

vi.mock('@/services/registrations', () => ({
  fetchMyRegistrationsApi: vi.fn(),
  fetchEventRegistrationsApi: vi.fn(),
  fetchRegistrationByIdApi: vi.fn(),
  registerForEventApi: vi.fn(),
  registerForSessionApi: vi.fn(),
  cancelRegistrationApi: vi.fn(),
}))

const mockedFetchEvents = vi.mocked(eventsService.fetchEventsApi)
const mockedFetchEventById = vi.mocked(eventsService.fetchEventByIdApi)
const mockedCreateEvent = vi.mocked(eventsService.createEventApi)
const mockedUpdateEvent = vi.mocked(eventsService.updateEventApi)
const mockedDeleteEvent = vi.mocked(eventsService.deleteEventApi)
const mockedUploadImage = vi.mocked(eventsService.uploadEventImageApi)
const mockedFetchSessions = vi.mocked(sessionsService.fetchSessionsApi)
const mockedFetchMyRegistrations = vi.mocked(
  registrationsService.fetchMyRegistrationsApi,
)
const mockedFetchEventRegistrations = vi.mocked(
  registrationsService.fetchEventRegistrationsApi,
)

beforeEach(() => {
  mockedFetchSessions.mockResolvedValue({ items: [], total: 0 })
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

const attendee: AuthUser = {
  ...organizer,
  id: 3,
  email: 'attendee@example.com',
  full_name: 'Ana Asistente',
  role: 'ATTENDEE',
}

const sampleEvent: EventRead = {
  id: 1,
  title: 'Conferencia Python Colombia',
  description: 'Encuentro anual de desarrollo con FastAPI y Vue.',
  date: '2026-11-15T14:00:00Z',
  total_capacity: 100,
  registered_count: 25,
  available_capacity: 60,
  status: 'PUBLISHED',
  organizer_id: 2,
  image_urls: null,
  created_at: '2026-10-31T15:00:00Z',
  updated_at: '2026-10-31T15:05:00Z',
}

function pageResponse(
  overrides: Partial<EventListResponse> = {},
): EventListResponse {
  return {
    items: [sampleEvent],
    total: 1,
    page: 1,
    size: 10,
    pages: 1,
    ...overrides,
  }
}

let pinia: Pinia

async function mountList() {
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
    ],
  })
  await router.push('/')
  await router.isReady()
  return mount(EventsListView, {
    global: { plugins: [pinia, router] },
  })
}

describe('EventsListView catalog, filters and role-aware controls', () => {
  beforeEach(() => {
    pinia = createPinia()
    setActivePinia(pinia)
    window.sessionStorage.clear()
    vi.restoreAllMocks()
    vi.clearAllMocks()
  })

  it('EVT-AC-28 renders EventsListView with search, pagination, role filters and create button for organizers', async () => {
    const authStore = useAuthStore()
    authStore.setSession('token-organizer', organizer)

    mockedFetchEvents.mockResolvedValueOnce(
      pageResponse({ total: 2, pages: 2 }),
    )

    const wrapper = await mountList()
    await flushPromises()

    expect(mockedFetchEvents).toHaveBeenCalledWith({ page: 1, size: 10 })
    expect(wrapper.text()).toContain(sampleEvent.title)
    expect(
      wrapper.find('[data-testid="event-create-link"]').exists(),
    ).toBe(true)
    expect(wrapper.find('#event-status-filter').exists()).toBe(true)
    expect(wrapper.find('#event-mine-filter').exists()).toBe(true)

    mockedFetchEvents.mockResolvedValueOnce(
      pageResponse({ total: 2, pages: 2 }),
    )
    await wrapper.find('#event-search').setValue('python')
    await wrapper
      .find('form[data-testid="event-search-form"]')
      .trigger('submit.prevent')
    await flushPromises()
    expect(mockedFetchEvents).toHaveBeenLastCalledWith(
      expect.objectContaining({ page: 1, search: 'python' }),
    )

    mockedFetchEvents.mockResolvedValueOnce(
      pageResponse({ total: 2, pages: 2 }),
    )
    await wrapper.find('#event-status-filter').setValue('PUBLISHED')
    await flushPromises()
    expect(mockedFetchEvents).toHaveBeenLastCalledWith(
      expect.objectContaining({ page: 1, status: 'PUBLISHED' }),
    )

    mockedFetchEvents.mockResolvedValueOnce(
      pageResponse({ total: 2, pages: 2 }),
    )
    await wrapper.find('#event-mine-filter').setValue(true)
    await flushPromises()
    expect(mockedFetchEvents).toHaveBeenLastCalledWith(
      expect.objectContaining({ page: 1, mine: true }),
    )

    mockedFetchEvents.mockResolvedValueOnce(
      pageResponse({ total: 2, pages: 2, page: 2 }),
    )
    await wrapper.find('[data-testid="next-page"]').trigger('click')
    await flushPromises()
    expect(mockedFetchEvents).toHaveBeenLastCalledWith(
      expect.objectContaining({ page: 2 }),
    )
    expect(wrapper.text()).toContain('Página 2 de 2')

    const homeRoute = routes.find((route) => route.name === 'home')
    expect(homeRoute).toBeTruthy()
    const loader = homeRoute?.component as () => Promise<{
      default: unknown
    }>
    const loaded = await loader()
    expect(loaded.default).toBe(EventsListView)
  })

  it('EVT-AC-28 shows BaseSkeleton while loading and an empty state without events', async () => {
    const authStore = useAuthStore()
    authStore.setSession('token-attendee', attendee)

    let resolveFetch!: (value: EventListResponse) => void
    mockedFetchEvents.mockReturnValueOnce(
      new Promise<EventListResponse>((resolve) => {
        resolveFetch = resolve
      }),
    )

    const wrapper = await mountList()
    await flushPromises()
    expect(wrapper.find('[data-testid="events-loading"]').exists()).toBe(
      true,
    )

    resolveFetch(pageResponse({ items: [], total: 0, pages: 0 }))
    await flushPromises()
    expect(wrapper.find('[data-testid="events-loading"]').exists()).toBe(
      false,
    )
    expect(wrapper.find('[data-testid="events-empty"]').exists()).toBe(
      true,
    )
  })

  it('EVT-AC-28 hides organizer filters and the create link from attendees', async () => {
    const authStore = useAuthStore()
    authStore.setSession('token-attendee', attendee)

    mockedFetchEvents.mockResolvedValueOnce(pageResponse())

    const wrapper = await mountList()
    await flushPromises()

    expect(
      wrapper.find('[data-testid="event-create-link"]').exists(),
    ).toBe(false)
    expect(wrapper.find('#event-status-filter').exists()).toBe(false)
    expect(wrapper.find('#event-mine-filter').exists()).toBe(false)
    expect(wrapper.find('#event-search').exists()).toBe(true)
    expect(wrapper.text()).toContain(sampleEvent.title)
  })
})

const detailEvent: EventRead = {
  ...sampleEvent,
  status: 'DRAFT',
  registered_count: 0,
  total_capacity: 100,
  // API value deliberately differs from total - registered (100) to prove
  // the detail view never recomputes capacity on the client (R2.5).
  available_capacity: 60,
  image_urls: {
    w400: '/api/media/events/abc_400w.webp',
    w800: '/api/media/events/abc_800w.webp',
    w1200: '/api/media/events/abc_1200w.webp',
  },
}

const admin: AuthUser = {
  ...organizer,
  id: 1,
  email: 'admin@example.com',
  full_name: 'Ada Administradora',
  role: 'ADMIN',
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

describe('EventDetailView detail, responsive image and role-aware actions', () => {
  beforeEach(() => {
    pinia = createPinia()
    setActivePinia(pinia)
    window.sessionStorage.clear()
    vi.restoreAllMocks()
    vi.clearAllMocks()
    mockedFetchMyRegistrations.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      size: 50,
      pages: 0,
    })
    mockedFetchEventRegistrations.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      size: 10,
      pages: 0,
    })
  })

  it('EVT-AC-29 renders EventDetailView with owner/admin actions and hides registration button for organizers', async () => {
    const authStore = useAuthStore()
    authStore.setSession('token-organizer', organizer)

    mockedFetchEventById.mockResolvedValueOnce(detailEvent)
    mockedUpdateEvent.mockImplementation(async (_id, payload) => ({
      ...detailEvent,
      ...payload,
    }))
    mockedDeleteEvent.mockResolvedValueOnce(undefined)

    const { wrapper, router } = await mountDetail()

    expect(mockedFetchEventById).toHaveBeenCalledWith(1)
    expect(wrapper.text()).toContain(detailEvent.title)
    expect(wrapper.text()).toContain(detailEvent.description)
    expect(wrapper.text()).toContain('Borrador')
    expect(wrapper.text()).toContain('60')
    expect(wrapper.text()).toContain('100')
    expect(wrapper.text()).toContain('Organizador #2')
    expect(wrapper.text()).not.toContain('75')

    const image = wrapper.find('img')
    expect(image.exists()).toBe(true)
    expect(image.attributes('src')).toBe(detailEvent.image_urls?.w800)
    expect(image.attributes('srcset')).toContain(
      `${detailEvent.image_urls?.w400} 400w`,
    )
    expect(image.attributes('srcset')).toContain(
      `${detailEvent.image_urls?.w1200} 1200w`,
    )
    expect(image.attributes('sizes')).toBeTruthy()
    expect(image.attributes('loading')).toBe('lazy')
    expect(image.attributes('decoding')).toBe('async')

    expect(
      wrapper.find('[data-testid="event-edit-link"]').exists(),
    ).toBe(true)
    expect(
      wrapper.find('[data-testid="event-publish-button"]').exists(),
    ).toBe(true)
    expect(
      wrapper.find('[data-testid="event-cancel-button"]').exists(),
    ).toBe(true)
    expect(
      wrapper.find('[data-testid="event-delete-button"]').exists(),
    ).toBe(true)
    expect(
      wrapper.find('[data-testid="registration-placeholder"]').exists(),
    ).toBe(false)

    await wrapper
      .find('[data-testid="event-publish-button"]')
      .trigger('click')
    await flushPromises()
    expect(mockedUpdateEvent).toHaveBeenCalledWith(1, {
      status: 'PUBLISHED',
    })
    expect(wrapper.text()).toContain('Publicado')

    vi.spyOn(window, 'confirm').mockReturnValueOnce(true)
    await wrapper
      .find('[data-testid="event-cancel-button"]')
      .trigger('click')
    await flushPromises()
    expect(mockedUpdateEvent).toHaveBeenLastCalledWith(1, {
      status: 'CANCELLED',
    })
    expect(wrapper.text()).toContain('Cancelado')

    vi.spyOn(window, 'confirm').mockReturnValueOnce(true)
    await wrapper
      .find('[data-testid="event-delete-button"]')
      .trigger('click')
    await flushPromises()
    expect(mockedDeleteEvent).toHaveBeenCalledWith(1)
    expect(router.currentRoute.value.name).toBe('home')

    const detailRoute = routes.find((route) => route.name === 'event-detail')
    expect(detailRoute).toBeTruthy()
    const loader = detailRoute?.component as () => Promise<{
      default: unknown
    }>
    const loaded = await loader()
    expect(loaded.default).toBe(EventDetailView)

    const createIndex = routes.findIndex(
      (route) => route.name === 'event-create',
    )
    const detailIndex = routes.findIndex(
      (route) => route.name === 'event-detail',
    )
    expect(createIndex).toBeLessThan(detailIndex)

    const source = readFileSync(
      resolve(process.cwd(), 'src/views/EventDetailView.vue'),
      'utf-8',
    )
    expect(source).not.toContain('v-html')
    expect(source).not.toMatch(/total_capacity\s*-\s*registered_count/)
  })

  it('EVT-AC-29 hides management actions from a non-owner organizer', async () => {
    const authStore = useAuthStore()
    authStore.setSession('token-other-organizer', {
      ...organizer,
      id: 99,
      email: 'otro@example.com',
    })

    mockedFetchEventById.mockResolvedValueOnce(detailEvent)

    const { wrapper } = await mountDetail()

    expect(wrapper.text()).toContain(detailEvent.title)
    expect(
      wrapper.find('[data-testid="event-edit-link"]').exists(),
    ).toBe(false)
    expect(
      wrapper.find('[data-testid="event-publish-button"]').exists(),
    ).toBe(false)
    expect(
      wrapper.find('[data-testid="event-cancel-button"]').exists(),
    ).toBe(false)
    expect(
      wrapper.find('[data-testid="event-delete-button"]').exists(),
    ).toBe(false)
    expect(
      wrapper.find('[data-testid="registration-placeholder"]').exists(),
    ).toBe(false)
  })

  it('EVT-AC-29 shows management actions to an admin for another organizer event', async () => {
    const authStore = useAuthStore()
    authStore.setSession('token-admin', admin)

    mockedFetchEventById.mockResolvedValueOnce(detailEvent)

    const { wrapper } = await mountDetail()

    expect(
      wrapper.find('[data-testid="event-edit-link"]').exists(),
    ).toBe(true)
    expect(
      wrapper.find('[data-testid="event-delete-button"]').exists(),
    ).toBe(true)
    expect(
      wrapper.find('[data-testid="registration-placeholder"]').exists(),
    ).toBe(false)
  })

  it('EVT-AC-29 shows the registration action only to attendees', async () => {
    const authStore = useAuthStore()
    authStore.setSession('token-attendee', attendee)

    mockedFetchEventById.mockResolvedValueOnce({
      ...detailEvent,
      status: 'PUBLISHED',
    })

    const { wrapper } = await mountDetail()

    expect(
      wrapper.find('[data-testid="registration-block"]').exists(),
    ).toBe(true)
    expect(
      wrapper.find('[data-testid="registration-button"]').exists(),
    ).toBe(true)
    expect(
      wrapper.find('[data-testid="event-edit-link"]').exists(),
    ).toBe(false)
    expect(
      wrapper.find('[data-testid="event-publish-button"]').exists(),
    ).toBe(false)
    expect(
      wrapper.find('[data-testid="event-cancel-button"]').exists(),
    ).toBe(false)
    expect(
      wrapper.find('[data-testid="event-delete-button"]').exists(),
    ).toBe(false)
    expect(wrapper.text()).toContain('Inscribirme')
  })

  it('EVT-AC-29 shows Evento no encontrado when the API responds 404', async () => {
    const authStore = useAuthStore()
    authStore.setSession('token-attendee', attendee)

    mockedFetchEventById.mockRejectedValueOnce({
      response: {
        status: 404,
        data: { detail: 'Evento no encontrado' },
      },
    })

    const { wrapper } = await mountDetail()

    expect(wrapper.text()).toContain('Evento no encontrado')
    expect(wrapper.find('h1').exists()).toBe(false)
  })

  it('EVT-AC-29 shows the image upload control to the owner and updates the event image', async () => {
    const authStore = useAuthStore()
    authStore.setSession('token-organizer', organizer)

    mockedFetchEventById.mockResolvedValueOnce(detailEvent)
    const updatedImage = {
      w400: '/api/media/events/new_400w.webp',
      w800: '/api/media/events/new_800w.webp',
      w1200: '/api/media/events/new_1200w.webp',
    }
    mockedUploadImage.mockResolvedValueOnce({
      ...detailEvent,
      image_urls: updatedImage,
    })

    const { wrapper } = await mountDetail()

    const fileInput = wrapper.find('input#event-image-upload')
    expect(fileInput.exists()).toBe(true)
    expect(fileInput.attributes('accept')).toBe(
      'image/jpeg,image/png,image/webp',
    )
    const uploadButton = wrapper.find(
      '[data-testid="event-image-submit"]',
    )
    expect(uploadButton.exists()).toBe(true)

    const file = new File(['binary'], 'nueva.png', { type: 'image/png' })
    const fileInputElement = fileInput.element as HTMLInputElement
    Object.defineProperty(fileInputElement, 'files', {
      value: [file],
      configurable: true,
    })
    Object.defineProperty(fileInputElement, 'value', {
      value: 'C:\\fakepath\\nueva.png',
      writable: true,
      configurable: true,
    })
    await fileInput.trigger('change')
    await uploadButton.trigger('click')
    await flushPromises()

    expect(mockedUploadImage).toHaveBeenCalledWith(1, file)
    expect(wrapper.text()).toContain('Imagen actualizada correctamente')
    expect(wrapper.find('img').attributes('src')).toBe(updatedImage.w800)
    expect(fileInputElement.value).toBe('')
    expect(
      wrapper.find('[data-testid="event-image-submit"]').attributes(
        'disabled',
      ),
    ).toBeUndefined()
  })

  it('EVT-AC-29 shows the Spanish upload error detail in the detail view', async () => {
    const authStore = useAuthStore()
    authStore.setSession('token-organizer', organizer)

    mockedFetchEventById.mockResolvedValueOnce(detailEvent)
    mockedUploadImage.mockRejectedValueOnce({
      response: {
        status: 413,
        data: { detail: 'La imagen no debe superar los 5 MB' },
      },
    })

    const { wrapper } = await mountDetail()

    const fileInput = wrapper.find('input#event-image-upload')
    const fileInputElement = fileInput.element as HTMLInputElement
    const file = new File(['binary'], 'grande.png', {
      type: 'image/png',
    })
    Object.defineProperty(fileInputElement, 'files', {
      value: [file],
      configurable: true,
    })
    Object.defineProperty(fileInputElement, 'value', {
      value: 'C:\\fakepath\\grande.png',
      writable: true,
      configurable: true,
    })
    await fileInput.trigger('change')
    await wrapper
      .find('[data-testid="event-image-submit"]')
      .trigger('click')
    await flushPromises()

    expect(mockedUploadImage).toHaveBeenCalledWith(1, file)
    expect(wrapper.text()).toContain(
      'La imagen no debe superar los 5 MB',
    )
    expect(fileInputElement.value).toBe('C:\\fakepath\\grande.png')
    expect(
      wrapper.find('[data-testid="event-image-submit"]').attributes(
        'disabled',
      ),
    ).toBeUndefined()
  })

  it('EVT-AC-29 shows the image upload control to an admin', async () => {
    const authStore = useAuthStore()
    authStore.setSession('token-admin', admin)
    mockedFetchEventById.mockResolvedValueOnce(detailEvent)

    const { wrapper } = await mountDetail()

    expect(wrapper.find('input#event-image-upload').exists()).toBe(
      true,
    )
    expect(
      wrapper.find('[data-testid="event-image-submit"]').exists(),
    ).toBe(true)
  })

  it('EVT-AC-29 hides the image upload control from a non-owner organizer and attendee', async () => {
    const authStore = useAuthStore()
    authStore.setSession('token-other-organizer', {
      ...organizer,
      id: 99,
      email: 'otro@example.com',
    })
    mockedFetchEventById.mockResolvedValueOnce(detailEvent)

    const organizerView = await mountDetail()
    expect(
      organizerView.wrapper.find('input#event-image-upload').exists(),
    ).toBe(false)
    expect(
      organizerView.wrapper.find(
        '[data-testid="event-image-submit"]',
      ).exists(),
    ).toBe(false)

    authStore.setSession('token-attendee', attendee)
    mockedFetchEventById.mockResolvedValueOnce({
      ...detailEvent,
      status: 'PUBLISHED',
    })
    const attendeeView = await mountDetail()
    expect(
      attendeeView.wrapper.find('input#event-image-upload').exists(),
    ).toBe(false)
    expect(
      attendeeView.wrapper.find(
        '[data-testid="event-image-submit"]',
      ).exists(),
    ).toBe(false)
  })

  it('EVT-AC-29 hides the image upload control for a cancelled event', async () => {
    const authStore = useAuthStore()
    authStore.setSession('token-organizer', organizer)
    mockedFetchEventById.mockResolvedValueOnce({
      ...detailEvent,
      status: 'CANCELLED',
    })

    const { wrapper } = await mountDetail()

    expect(wrapper.find('input#event-image-upload').exists()).toBe(
      false,
    )
    expect(
      wrapper.find('[data-testid="event-image-submit"]').exists(),
    ).toBe(false)
  })
})

async function mountFormView(path: string) {
  const router = createAppRouter(true)
  await router.push(path)
  await router.isReady()
  const wrapper = mount(EventFormView, {
    global: { plugins: [pinia, router] },
  })
  await flushPromises()
  await vi.waitFor(() => {
    const ready =
      wrapper.find('[data-testid="event-form"]').exists() ||
      wrapper.find('[data-testid="event-form-error"]').exists()
    if (!ready) throw new Error('Event form not ready')
  })
  await flushPromises()
  return { wrapper, router }
}

async function fillValidForm(wrapper: ReturnType<typeof mount>): Promise<void> {
  await wrapper.find('input#event-title').setValue('Concierto Vue')
  await wrapper
    .find('textarea#event-description')
    .setValue('Un evento de prueba con comunidad')
  await wrapper.find('input#event-date').setValue('2026-12-01T10:00')
  await wrapper.find('input#event-capacity').setValue('40')
  await wrapper.find('select#event-status').setValue('PUBLISHED')
}

describe('EventFormView lazy form, create/edit flows and guards', () => {
  beforeEach(() => {
    pinia = createPinia()
    setActivePinia(pinia)
    window.sessionStorage.clear()
    vi.restoreAllMocks()
    vi.clearAllMocks()
  })

  it('EVT-AC-30 loads EventForm lazily with defineAsyncComponent in EventFormView and enforces router guards', async () => {
    const authStore = useAuthStore()
    authStore.setSession('token-organizer', organizer)

    const createdEvent: EventRead = {
      ...sampleEvent,
      id: 10,
      title: 'Concierto Vue',
      status: 'PUBLISHED',
      organizer_id: 2,
    }
    mockedCreateEvent.mockResolvedValueOnce(createdEvent)
    mockedUploadImage.mockResolvedValueOnce({
      ...createdEvent,
      image_urls: {
        w400: '/api/media/events/new_400w.webp',
        w800: '/api/media/events/new_800w.webp',
        w1200: '/api/media/events/new_1200w.webp',
      },
    })

    const { wrapper, router } = await mountFormView('/events/new')

    expect(wrapper.find('[data-testid="event-form"]').exists()).toBe(true)

    await fillValidForm(wrapper)
    const file = new File(['binary'], 'portada.png', {
      type: 'image/png',
    })
    const fileInput = wrapper.find('input#event-image')
      .element as HTMLInputElement
    Object.defineProperty(fileInput, 'files', {
      value: [file],
      configurable: true,
    })
    await wrapper.find('input#event-image').trigger('change')

    await wrapper
      .find('form[data-testid="event-form"]')
      .trigger('submit.prevent')
    await flushPromises()
    await flushPromises()

    expect(mockedCreateEvent).toHaveBeenCalledWith({
      title: 'Concierto Vue',
      description: 'Un evento de prueba con comunidad',
      date: new Date('2026-12-01T10:00').toISOString(),
      total_capacity: 40,
      status: 'PUBLISHED',
    })
    expect(mockedUploadImage).toHaveBeenCalledWith(10, file)
    expect(router.currentRoute.value.name).toBe('event-detail')
    expect(router.currentRoute.value.params.id).toBe('10')

    const createRoute = routes.find(
      (route) => route.name === 'event-create',
    )
    const editRoute = routes.find((route) => route.name === 'event-edit')
    expect(createRoute?.meta?.requiresAuth).toBe(true)
    expect(createRoute?.meta?.roles).toEqual(['ORGANIZER', 'ADMIN'])
    expect(editRoute?.meta?.requiresAuth).toBe(true)
    expect(editRoute?.meta?.roles).toEqual(['ORGANIZER', 'ADMIN'])

    const editLoader = editRoute?.component as () => Promise<{
      default: unknown
    }>
    const loadedEdit = await editLoader()
    expect(loadedEdit.default).toBe(EventFormView)

    const source = readFileSync(
      resolve(process.cwd(), 'src/views/EventFormView.vue'),
      'utf-8',
    )
    expect(source).toContain('defineAsyncComponent')
    expect(source).not.toContain('v-html')
  })

  it('EVT-AC-30 loads the event in edit mode and updates it without uploading a new image', async () => {
    const authStore = useAuthStore()
    authStore.setSession('token-organizer', organizer)

    const editEvent: EventRead = {
      ...sampleEvent,
      id: 5,
      title: 'Evento original',
      status: 'DRAFT',
      organizer_id: 2,
    }
    mockedFetchEventById.mockResolvedValueOnce(editEvent)
    mockedUpdateEvent.mockResolvedValueOnce({
      ...editEvent,
      title: 'Evento editado',
    })

    const { wrapper, router } = await mountFormView('/events/5/edit')

    expect(mockedFetchEventById).toHaveBeenCalledWith(5)
    const titleInput = wrapper.find('input#event-title')
    expect((titleInput.element as HTMLInputElement).value).toBe(
      'Evento original',
    )

    await titleInput.setValue('Evento editado')
    await wrapper
      .find('form[data-testid="event-form"]')
      .trigger('submit.prevent')
    await flushPromises()
    await flushPromises()

    expect(mockedUpdateEvent).toHaveBeenCalledWith(
      5,
      expect.objectContaining({
        title: 'Evento editado',
        status: 'DRAFT',
      }),
    )
    expect(mockedUploadImage).not.toHaveBeenCalled()
    expect(router.currentRoute.value.name).toBe('event-detail')
    expect(router.currentRoute.value.params.id).toBe('5')
  })

  it('EVT-AC-30 navigates to the detail with a warning when the image upload fails after editing', async () => {
    const authStore = useAuthStore()
    authStore.setSession('token-organizer', organizer)

    const editEvent: EventRead = {
      ...sampleEvent,
      id: 5,
      title: 'Evento original',
      status: 'DRAFT',
      organizer_id: 2,
    }
    mockedFetchEventById.mockResolvedValueOnce(editEvent)
    mockedUpdateEvent.mockResolvedValueOnce({
      ...editEvent,
      title: 'Evento editado',
    })
    mockedUploadImage.mockRejectedValueOnce({
      response: {
        status: 413,
        data: { detail: 'La imagen no debe superar los 5 MB' },
      },
    })

    const { wrapper, router } = await mountFormView('/events/5/edit')

    await wrapper.find('input#event-title').setValue('Evento editado')
    const file = new File(['binary'], 'grande.png', {
      type: 'image/png',
    })
    const fileInput = wrapper.find('input#event-image')
      .element as HTMLInputElement
    Object.defineProperty(fileInput, 'files', {
      value: [file],
      configurable: true,
    })
    await wrapper.find('input#event-image').trigger('change')

    await wrapper
      .find('form[data-testid="event-form"]')
      .trigger('submit.prevent')
    await flushPromises()
    await flushPromises()

    expect(mockedUpdateEvent).toHaveBeenCalledTimes(1)
    expect(mockedUploadImage).toHaveBeenCalledWith(5, file)
    expect(mockedCreateEvent).not.toHaveBeenCalled()
    expect(router.currentRoute.value.name).toBe('event-detail')
    expect(router.currentRoute.value.params.id).toBe('5')

    const notificationStore = useNotificationStore()
    expect(notificationStore.lastMessage).toContain(
      'Los datos del evento se guardaron, pero la imagen no se pudo subir',
    )
    expect(notificationStore.lastType).toBe('warning')
  })

  it('EVT-AC-30 shows Spanish 422 field errors returned by the API without navigating away', async () => {
    const authStore = useAuthStore()
    authStore.setSession('token-organizer', organizer)

    mockedCreateEvent.mockRejectedValueOnce({
      response: {
        status: 422,
        data: {
          detail: 'Error de validación en los datos enviados',
          errors: [
            {
              field: 'title',
              message: 'El título ya está en uso por otro evento',
            },
          ],
        },
      },
    })

    const { wrapper, router } = await mountFormView('/events/new')

    await fillValidForm(wrapper)
    await wrapper
      .find('form[data-testid="event-form"]')
      .trigger('submit.prevent')
    await flushPromises()
    await flushPromises()

    expect(wrapper.text()).toContain(
      'El título ya está en uso por otro evento',
    )
    expect(wrapper.text()).toContain(
      'Error de validación en los datos enviados',
    )
    expect(router.currentRoute.value.name).toBe('event-create')
  })

  it('EVT-AC-30 redirects anonymous users to login and attendees to home from event forms', async () => {
    const anonymousRouter = createAppRouter(true)
    await anonymousRouter.push('/events/new')
    await anonymousRouter.isReady()
    expect(anonymousRouter.currentRoute.value.name).toBe('login')
    expect(anonymousRouter.currentRoute.value.query.redirect).toBe(
      '/events/new',
    )

    const anonymousEditRouter = createAppRouter(true)
    await anonymousEditRouter.push('/events/5/edit')
    await anonymousEditRouter.isReady()
    expect(anonymousEditRouter.currentRoute.value.name).toBe('login')
    expect(anonymousEditRouter.currentRoute.value.query.redirect).toBe(
      '/events/5/edit',
    )

    const authStore = useAuthStore()
    authStore.setSession('token-attendee', attendee)

    const attendeeRouter = createAppRouter(true)
    await attendeeRouter.push('/events/new')
    await attendeeRouter.isReady()
    expect(attendeeRouter.currentRoute.value.name).toBe('home')
  })

  it('EVT-AC-30 navigates to the detail with a Spanish warning when the image upload fails after creation', async () => {
    const authStore = useAuthStore()
    authStore.setSession('token-organizer', organizer)

    const createdEvent: EventRead = {
      ...sampleEvent,
      id: 11,
      title: 'Concierto sin portada',
      organizer_id: 2,
    }
    mockedCreateEvent.mockResolvedValueOnce(createdEvent)
    mockedUploadImage.mockRejectedValueOnce({
      response: {
        status: 413,
        data: { detail: 'La imagen no debe superar los 5 MB' },
      },
    })

    const { wrapper, router } = await mountFormView('/events/new')
    await fillValidForm(wrapper)

    const file = new File(['binary'], 'grande.png', {
      type: 'image/png',
    })
    const fileInput = wrapper.find('input#event-image')
      .element as HTMLInputElement
    Object.defineProperty(fileInput, 'files', {
      value: [file],
      configurable: true,
    })
    await wrapper.find('input#event-image').trigger('change')

    await wrapper
      .find('form[data-testid="event-form"]')
      .trigger('submit.prevent')
    await flushPromises()
    await flushPromises()

    expect(mockedCreateEvent).toHaveBeenCalledTimes(1)
    expect(mockedUploadImage).toHaveBeenCalledWith(11, file)
    expect(router.currentRoute.value.name).toBe('event-detail')
    expect(router.currentRoute.value.params.id).toBe('11')

    const notificationStore = useNotificationStore()
    expect(notificationStore.lastMessage).toContain(
      'El evento se creó, pero la imagen no se pudo subir',
    )
    expect(notificationStore.lastType).toBe('warning')
  })
})
