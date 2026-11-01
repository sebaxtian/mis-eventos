import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import type {
  AuthUser,
  EventListResponse,
  EventRead,
} from '@/types/api'
import apiClient from '@/services/api'
import { useAuthStore } from '@/stores/auth'
import { useEventStore } from '@/stores/events'
import * as eventsService from '@/services/events'

vi.mock('@/services/events', () => ({
  fetchEventsApi: vi.fn(),
  fetchEventByIdApi: vi.fn(),
  createEventApi: vi.fn(),
  updateEventApi: vi.fn(),
  deleteEventApi: vi.fn(),
  uploadEventImageApi: vi.fn(),
}))

const mockedFetchEvents = vi.mocked(eventsService.fetchEventsApi)
const mockedFetchEventById = vi.mocked(eventsService.fetchEventByIdApi)
const mockedCreateEvent = vi.mocked(eventsService.createEventApi)
const mockedUpdateEvent = vi.mocked(eventsService.updateEventApi)
const mockedDeleteEvent = vi.mocked(eventsService.deleteEventApi)
const mockedUploadImage = vi.mocked(eventsService.uploadEventImageApi)

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

const baseEvent: EventRead = {
  id: 1,
  title: 'Conferencia Python Colombia',
  description: 'Encuentro anual de desarrollo con FastAPI y Vue.',
  date: '2026-11-15T14:00:00Z',
  total_capacity: 100,
  registered_count: 25,
  // Deliberately inconsistent with total - registered to prove the client
  // never recomputes the value (R2.5): the API value must be preserved.
  available_capacity: 60,
  status: 'PUBLISHED',
  organizer_id: 2,
  image_urls: null,
  created_at: '2026-10-31T15:00:00Z',
  updated_at: '2026-10-31T15:05:00Z',
}

const listResponse: EventListResponse = {
  items: [baseEvent],
  total: 1,
  page: 2,
  size: 5,
  pages: 3,
}

describe('useEventStore events state, CRUD and API contract', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    window.sessionStorage.clear()
    vi.restoreAllMocks()
    vi.clearAllMocks()
  })

  it('EVT-AC-26 fetches paginated events with filters and manages CRUD and image upload in useEventStore', async () => {
    const authStore = useAuthStore()
    authStore.setSession('token-organizer', organizer)

    const store = useEventStore()
    expect(store.hasEvents).toBe(false)
    expect(store.canCreate).toBe(true)

    mockedFetchEvents.mockResolvedValueOnce(listResponse)

    const fetchPromise = store.fetchEvents({
      page: 2,
      size: 5,
      search: 'python',
      status: 'PUBLISHED',
      mine: true,
    })
    expect(store.isLoading).toBe(true)
    await fetchPromise

    expect(store.isLoading).toBe(false)
    expect(mockedFetchEvents).toHaveBeenCalledWith({
      page: 2,
      size: 5,
      search: 'python',
      status: 'PUBLISHED',
      mine: true,
    })
    expect(store.items).toEqual([baseEvent])
    expect(store.total).toBe(1)
    expect(store.page).toBe(2)
    expect(store.size).toBe(5)
    expect(store.pages).toBe(3)
    expect(store.search).toBe('python')
    expect(store.statusFilter).toBe('PUBLISHED')
    expect(store.mineOnly).toBe(true)
    expect(store.hasEvents).toBe(true)

    // R2.5: capacity fields are consumed exactly as delivered by the API.
    expect(store.items[0]?.available_capacity).toBe(60)
    expect(store.items[0]?.registered_count).toBe(25)
    expect(store.items[0]?.total_capacity).toBe(100)

    const detailEvent: EventRead = { ...baseEvent, id: 9 }
    mockedFetchEventById.mockResolvedValueOnce(detailEvent)
    await store.fetchEventById(9)
    expect(mockedFetchEventById).toHaveBeenCalledWith(9)
    expect(store.currentEvent).toEqual(detailEvent)

    const createdEvent: EventRead = {
      ...baseEvent,
      id: 10,
      title: 'Nuevo evento',
      status: 'DRAFT',
      organizer_id: 2,
    }
    const createPayload = {
      title: 'Nuevo evento',
      description: 'Descripción válida para el evento',
      date: '2026-12-01T10:00:00Z',
      total_capacity: 50,
    }
    mockedCreateEvent.mockResolvedValueOnce(createdEvent)
    const created = await store.createEvent(createPayload)
    expect(mockedCreateEvent).toHaveBeenCalledWith(createPayload)
    expect(created).toEqual(createdEvent)
    expect(store.currentEvent).toEqual(createdEvent)
    expect(store.items[0]).toEqual(createdEvent)

    const updatedEvent: EventRead = {
      ...createdEvent,
      title: 'Evento actualizado',
      status: 'PUBLISHED',
    }
    mockedUpdateEvent.mockResolvedValueOnce(updatedEvent)
    const updated = await store.updateEvent(10, {
      title: 'Evento actualizado',
      status: 'PUBLISHED',
    })
    expect(mockedUpdateEvent).toHaveBeenCalledWith(10, {
      title: 'Evento actualizado',
      status: 'PUBLISHED',
    })
    expect(updated).toEqual(updatedEvent)
    expect(store.currentEvent).toEqual(updatedEvent)
    expect(store.items.find((item) => item.id === 10)).toEqual(updatedEvent)

    const imageUrls = {
      w400: '/api/media/events/abc_400w.webp',
      w800: '/api/media/events/abc_800w.webp',
      w1200: '/api/media/events/abc_1200w.webp',
    }
    const withImage: EventRead = { ...updatedEvent, image_urls: imageUrls }
    const file = new File(['binary'], 'foto.png', { type: 'image/png' })
    mockedUploadImage.mockResolvedValueOnce(withImage)
    const uploaded = await store.uploadEventImage(10, file)
    expect(mockedUploadImage).toHaveBeenCalledWith(10, file)
    expect(uploaded).toEqual(withImage)
    expect(store.currentEvent?.image_urls).toEqual(imageUrls)
    expect(store.items.find((item) => item.id === 10)?.image_urls).toEqual(
      imageUrls,
    )

    mockedDeleteEvent.mockResolvedValueOnce(undefined)
    await store.deleteEvent(10)
    expect(mockedDeleteEvent).toHaveBeenCalledWith(10)
    expect(store.currentEvent).toBeNull()
    expect(store.items.find((item) => item.id === 10)).toBeUndefined()

    store.resetFilters()
    expect(store.search).toBe('')
    expect(store.statusFilter).toBe('')
    expect(store.mineOnly).toBe(false)
    expect(store.page).toBe(1)

    authStore.setSession('token-attendee', attendee)
    expect(store.canCreate).toBe(false)

    mockedFetchEvents.mockRejectedValueOnce({
      response: {
        status: 500,
        data: { detail: 'No se pudo cargar el catálogo de eventos' },
      },
    })
    await store.fetchEvents()
    expect(store.errorMessage).toBe('No se pudo cargar el catálogo de eventos')
    expect(store.isLoading).toBe(false)

    const storeSource = readFileSync(
      resolve(process.cwd(), 'src/stores/events.ts'),
      'utf-8',
    )
    expect(storeSource).not.toMatch(/total_capacity\s*-\s*registered_count/)
  })

  it('EVT-AC-26 calls the /api/events endpoints through the typed events service', async () => {
    const actualService =
      await vi.importActual<typeof import('@/services/events')>(
        '@/services/events',
      )

    const getSpy = vi
      .spyOn(apiClient, 'get')
      .mockResolvedValueOnce({ data: listResponse })
      .mockResolvedValueOnce({ data: baseEvent })
    const postSpy = vi
      .spyOn(apiClient, 'post')
      .mockResolvedValueOnce({ data: baseEvent })
      .mockResolvedValueOnce({ data: baseEvent })
    const patchSpy = vi
      .spyOn(apiClient, 'patch')
      .mockResolvedValueOnce({ data: baseEvent })
    const deleteSpy = vi
      .spyOn(apiClient, 'delete')
      .mockResolvedValueOnce({ data: undefined })

    await actualService.fetchEventsApi({ page: 1, search: 'vue' })
    expect(getSpy).toHaveBeenNthCalledWith(1, '/events', {
      params: { page: 1, search: 'vue' },
    })

    await actualService.fetchEventByIdApi(7)
    expect(getSpy).toHaveBeenNthCalledWith(2, '/events/7')

    await actualService.createEventApi({
      title: 'Evento de prueba',
      description: 'Descripción del evento de prueba',
      date: '2026-12-01T10:00:00Z',
      total_capacity: 30,
    })
    expect(postSpy).toHaveBeenNthCalledWith(1, '/events', {
      title: 'Evento de prueba',
      description: 'Descripción del evento de prueba',
      date: '2026-12-01T10:00:00Z',
      total_capacity: 30,
    })

    await actualService.updateEventApi(7, { status: 'PUBLISHED' })
    expect(patchSpy).toHaveBeenCalledWith('/events/7', {
      status: 'PUBLISHED',
    })

    await actualService.deleteEventApi(7)
    expect(deleteSpy).toHaveBeenCalledWith('/events/7')

    const file = new File(['binary'], 'foto.webp', { type: 'image/webp' })
    await actualService.uploadEventImageApi(7, file)
    expect(postSpy).toHaveBeenNthCalledWith(
      2,
      '/events/7/image',
      expect.any(FormData),
      expect.objectContaining({
        headers: expect.objectContaining({
          'Content-Type': undefined,
        }),
      }),
    )
    const formData = postSpy.mock.calls[1]?.[1] as FormData
    expect(formData.get('file')).toBe(file)
  })
})
