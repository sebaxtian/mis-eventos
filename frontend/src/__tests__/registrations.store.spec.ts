import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import type {
  RegistrationListResponse,
  RegistrationRead,
} from '@/types/api'
import apiClient from '@/services/api'
import { useRegistrationStore } from '@/stores/registrations'
import * as registrationsService from '@/services/registrations'

vi.mock('@/services/registrations', () => ({
  fetchMyRegistrationsApi: vi.fn(),
  fetchEventRegistrationsApi: vi.fn(),
  fetchRegistrationByIdApi: vi.fn(),
  registerForEventApi: vi.fn(),
  registerForSessionApi: vi.fn(),
  cancelRegistrationApi: vi.fn(),
}))

const mockedFetchMine = vi.mocked(
  registrationsService.fetchMyRegistrationsApi,
)
const mockedFetchEventRegistrations = vi.mocked(
  registrationsService.fetchEventRegistrationsApi,
)
const mockedFetchById = vi.mocked(
  registrationsService.fetchRegistrationByIdApi,
)
const mockedRegisterEvent = vi.mocked(
  registrationsService.registerForEventApi,
)
const mockedRegisterSession = vi.mocked(
  registrationsService.registerForSessionApi,
)
const mockedCancel = vi.mocked(registrationsService.cancelRegistrationApi)

const eventRegistration: RegistrationRead = {
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

const sessionRegistration: RegistrationRead = {
  ...eventRegistration,
  id: 42,
  session_id: 10,
  event: {
    ...eventRegistration.event,
    title: 'Conferencia de Tecnología 2026',
  },
  session: {
    id: 10,
    title: 'Apertura y bienvenida',
    speaker: 'Ana Torres',
    start_time: '2026-11-15T14:00:00Z',
    end_time: '2026-11-15T15:00:00Z',
  },
  created_at: '2026-11-01T10:05:00Z',
  updated_at: '2026-11-01T10:05:00Z',
}

const listResponse: RegistrationListResponse = {
  items: [sessionRegistration, eventRegistration],
  total: 12,
  page: 1,
  size: 10,
  pages: 2,
}

const emptyPage: RegistrationListResponse = {
  items: [],
  total: 0,
  page: 1,
  size: 10,
  pages: 0,
}

describe('useRegistrationStore registration state, DTOs and API contract', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('REG-AC-35 loads registration types, service and store without recalculating capacity', async () => {
    const store = useRegistrationStore()

    expect(store.items).toEqual([])
    expect(store.total).toBe(0)
    expect(store.page).toBe(1)
    expect(store.size).toBe(10)
    expect(store.pages).toBe(0)
    expect(store.currentRegistration).toBeNull()
    expect(store.isLoading).toBe(false)
    expect(store.isSubmitting).toBe(false)
    expect(store.errorMessage).toBe('')
    expect(store.fieldErrors).toEqual([])
    expect(store.lastCreatedStatus).toBeNull()

    mockedFetchMine.mockResolvedValueOnce(listResponse)
    const fetchPromise = store.fetchMyRegistrations({
      page: 1,
      size: 10,
    })
    expect(store.isLoading).toBe(true)
    await fetchPromise

    expect(mockedFetchMine).toHaveBeenCalledWith({
      page: 1,
      size: 10,
    })
    expect(store.isLoading).toBe(false)
    expect(store.items).toEqual([
      sessionRegistration,
      eventRegistration,
    ])
    expect(store.total).toBe(12)
    expect(store.page).toBe(1)
    expect(store.size).toBe(10)
    expect(store.pages).toBe(2)

    // DTOs are consumed exactly as the API delivers them (R2.5, D13).
    expect(store.items[0]?.event).toEqual(
      sessionRegistration.event,
    )
    expect(store.items[0]?.session).toEqual(
      sessionRegistration.session,
    )
    expect(store.items[0]?.user_id).toBe(7)
    expect(store.items[0]?.status).toBe('ACTIVE')
    const serialized = JSON.stringify(store.items)
    expect(serialized).not.toContain('full_name')
    expect(serialized).not.toContain('email')
    expect(serialized).not.toContain('password_hash')

    mockedFetchMine.mockResolvedValueOnce({
      ...listResponse,
      items: [eventRegistration],
      total: 1,
      page: 2,
      size: 5,
      pages: 1,
    })
    await store.fetchMyRegistrations({
      page: 2,
      size: 5,
      status: 'ACTIVE',
      event_id: 5,
    })
    expect(mockedFetchMine).toHaveBeenLastCalledWith({
      page: 2,
      size: 5,
      status: 'ACTIVE',
      event_id: 5,
    })

    mockedFetchEventRegistrations.mockResolvedValueOnce({
      items: [eventRegistration],
      total: 1,
      page: 1,
      size: 10,
      pages: 1,
    })
    await store.fetchEventRegistrations(5, {
      page: 1,
      size: 10,
      status: 'CANCELLED',
    })
    expect(mockedFetchEventRegistrations).toHaveBeenCalledWith(5, {
      page: 1,
      size: 10,
      status: 'CANCELLED',
    })
    expect(store.items).toEqual([eventRegistration])

    mockedFetchById.mockResolvedValueOnce(sessionRegistration)
    await store.fetchRegistrationById(42)
    expect(mockedFetchById).toHaveBeenCalledWith(42)
    expect(store.currentRegistration).toEqual(sessionRegistration)

    mockedFetchById.mockRejectedValueOnce({
      response: {
        status: 404,
        data: { detail: 'Inscripción no encontrada' },
      },
    })
    await store.fetchRegistrationById(99)
    expect(store.currentRegistration).toBeNull()
    expect(store.errorMessage).toBe('Inscripción no encontrada')

    mockedRegisterEvent.mockResolvedValueOnce({
      registration: eventRegistration,
      created: true,
    })
    const created = await store.registerForEvent(5)
    expect(mockedRegisterEvent).toHaveBeenCalledWith(5)
    expect(created).toEqual(eventRegistration)
    expect(store.currentRegistration).toEqual(eventRegistration)
    expect(store.lastCreatedStatus).toBe('created')
    expect(store.items).toEqual([])
    expect(store.total).toBe(0)
    expect(store.pages).toBe(0)

    mockedRegisterSession.mockResolvedValueOnce({
      registration: sessionRegistration,
      created: false,
    })
    const reactivated = await store.registerForSession(5, 10)
    expect(mockedRegisterSession).toHaveBeenCalledWith(5, 10)
    expect(reactivated).toEqual(sessionRegistration)
    expect(store.currentRegistration).toEqual(sessionRegistration)
    expect(store.lastCreatedStatus).toBe('reactivated')

    mockedCancel.mockResolvedValueOnce(undefined)
    await store.cancelRegistration(42)
    expect(mockedCancel).toHaveBeenCalledWith(42)
    expect(store.currentRegistration).toBeNull()
    expect(store.items).toEqual([])

    mockedCancel.mockRejectedValueOnce({
      response: {
        status: 404,
        data: { detail: 'Inscripción no encontrada' },
      },
    })
    await expect(store.cancelRegistration(99)).rejects.toBeTruthy()
    expect(store.errorMessage).toBe('Inscripción no encontrada')
    expect(store.isSubmitting).toBe(false)

    mockedFetchMine.mockRejectedValueOnce({
      response: {
        status: 500,
        data: { detail: 'No se pudieron cargar tus inscripciones' },
      },
    })
    await store.fetchMyRegistrations({ page: 1 })
    expect(store.errorMessage).toBe(
      'No se pudieron cargar tus inscripciones',
    )
    expect(store.items).toEqual([])
    expect(store.total).toBe(0)
    expect(store.isLoading).toBe(false)

    mockedRegisterEvent.mockRejectedValueOnce({
      response: {
        status: 409,
        data: { detail: 'Ya estás inscrito en este evento' },
      },
    })
    await expect(store.registerForEvent(5)).rejects.toBeTruthy()
    expect(store.errorMessage).toBe('Ya estás inscrito en este evento')
    expect(store.isSubmitting).toBe(false)

    mockedRegisterSession.mockRejectedValueOnce({
      response: {
        status: 422,
        data: {
          detail: 'Error de validación en los datos enviados',
          errors: [
            {
              field: 'session_id',
              message: 'El valor debe ser mayor o igual a 1',
            },
          ],
        },
      },
    })
    await expect(store.registerForSession(5, 0)).rejects.toBeTruthy()
    expect(store.errorMessage).toBe(
      'Error de validación en los datos enviados',
    )
    expect(store.fieldErrors).toEqual([
      {
        field: 'session_id',
        message: 'El valor debe ser mayor o igual a 1',
      },
    ])

    store.clearErrors()
    expect(store.errorMessage).toBe('')
    expect(store.fieldErrors).toEqual([])

    mockedFetchMine.mockResolvedValueOnce(emptyPage)
    await store.fetchMyRegistrations({ page: 1, size: 10 })
    store.reset()
    expect(store.items).toEqual([])
    expect(store.total).toBe(0)
    expect(store.currentRegistration).toBeNull()
    expect(store.lastCreatedStatus).toBeNull()

    const storeSource = readFileSync(
      resolve(process.cwd(), 'src/stores/registrations.ts'),
      'utf-8',
    )
    expect(storeSource).not.toContain('full_name')
    expect(storeSource).not.toContain('password_hash')
    expect(storeSource).not.toMatch(/available_capacity\s*-/)
    expect(storeSource).not.toMatch(/capacity\s*-\s*registered_count/)
  })

  it('REG-AC-35 calls the registration endpoints through the typed registrations service', async () => {
    const actualService =
      await vi.importActual<typeof import('@/services/registrations')>(
        '@/services/registrations',
      )

    expect(apiClient.defaults.baseURL).toBe('/api')

    const getSpy = vi
      .spyOn(apiClient, 'get')
      .mockResolvedValueOnce({ data: listResponse })
      .mockResolvedValueOnce({ data: listResponse })
      .mockResolvedValueOnce({ data: eventRegistration })
    const postSpy = vi
      .spyOn(apiClient, 'post')
      .mockResolvedValueOnce({ data: eventRegistration, status: 201 })
      .mockResolvedValueOnce({ data: sessionRegistration, status: 200 })
    const deleteSpy = vi
      .spyOn(apiClient, 'delete')
      .mockResolvedValueOnce({ data: undefined })

    await actualService.fetchMyRegistrationsApi({
      page: 1,
      size: 10,
      status: 'ACTIVE',
      event_id: 5,
    })
    expect(getSpy).toHaveBeenNthCalledWith(1, '/registrations/me', {
      params: { page: 1, size: 10, status: 'ACTIVE', event_id: 5 },
    })

    await actualService.fetchEventRegistrationsApi(5, {
      page: 2,
      size: 10,
      status: 'CANCELLED',
    })
    expect(getSpy).toHaveBeenNthCalledWith(
      2,
      '/events/5/registrations',
      {
        params: { page: 2, size: 10, status: 'CANCELLED' },
      },
    )

    await actualService.fetchRegistrationByIdApi(41)
    expect(getSpy).toHaveBeenNthCalledWith(3, '/registrations/41')

    const created = await actualService.registerForEventApi(5)
    expect(postSpy).toHaveBeenNthCalledWith(
      1,
      '/events/5/registrations',
    )
    expect(created).toEqual({
      registration: eventRegistration,
      created: true,
    })

    const reactivated = await actualService.registerForSessionApi(5, 10)
    expect(postSpy).toHaveBeenNthCalledWith(
      2,
      '/events/5/sessions/10/registrations',
    )
    expect(reactivated).toEqual({
      registration: sessionRegistration,
      created: false,
    })

    await actualService.cancelRegistrationApi(41)
    expect(deleteSpy).toHaveBeenCalledWith('/registrations/41')
  })
})
