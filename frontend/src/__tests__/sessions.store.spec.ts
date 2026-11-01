import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import type {
  SessionCreatePayload,
  SessionListResponse,
  SessionRead,
} from '@/types/api'
import apiClient from '@/services/api'
import { useSessionStore } from '@/stores/sessions'
import * as sessionsService from '@/services/sessions'

vi.mock('@/services/sessions', () => ({
  fetchSessionsApi: vi.fn(),
  fetchSessionByIdApi: vi.fn(),
  createSessionApi: vi.fn(),
  updateSessionApi: vi.fn(),
  deleteSessionApi: vi.fn(),
}))

const mockedFetchSessions = vi.mocked(sessionsService.fetchSessionsApi)
const mockedFetchSessionById = vi.mocked(sessionsService.fetchSessionByIdApi)
const mockedCreateSession = vi.mocked(sessionsService.createSessionApi)
const mockedUpdateSession = vi.mocked(sessionsService.updateSessionApi)
const mockedDeleteSession = vi.mocked(sessionsService.deleteSessionApi)

const baseSession: SessionRead = {
  id: 10,
  event_id: 5,
  title: 'Apertura y bienvenida',
  description: 'Presentación del programa del día.',
  speaker: 'Ana Torres',
  start_time: '2026-11-15T15:00:00Z',
  end_time: '2026-11-15T16:00:00Z',
  capacity: 100,
  registered_count: 25,
  // Deliberately inconsistent with capacity - registered (75) to prove the
  // client never recomputes the value (R2.5): the API value must be kept.
  available_capacity: 60,
  created_at: '2026-10-31T18:00:00Z',
  updated_at: '2026-10-31T18:00:00Z',
}

const listResponse: SessionListResponse = {
  items: [baseSession],
  total: 1,
}

const createPayload: SessionCreatePayload = {
  title: 'Taller de FastAPI',
  speaker: 'Luis Gómez',
  description: 'Taller práctico de la API.',
  start_time: '2026-11-15T17:00:00Z',
  end_time: '2026-11-15T18:00:00Z',
  capacity: 40,
}

describe('useSessionStore session state, CRUD and API contract', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('SES-AC-26 loads session types, service and store without recalculating capacity', async () => {
    const store = useSessionStore()

    expect(store.items).toEqual([])
    expect(store.total).toBe(0)
    expect(store.currentSession).toBeNull()
    expect(store.isLoading).toBe(false)
    expect(store.isSubmitting).toBe(false)
    expect(store.errorMessage).toBe('')
    expect(store.fieldErrors).toEqual([])

    mockedFetchSessions.mockResolvedValueOnce(listResponse)
    const fetchPromise = store.fetchSessions(5)
    expect(store.isLoading).toBe(true)
    await fetchPromise

    expect(mockedFetchSessions).toHaveBeenCalledWith(5)
    expect(store.isLoading).toBe(false)
    expect(store.items).toEqual([baseSession])
    expect(store.total).toBe(1)
    // R2.5: capacity fields are consumed exactly as delivered by the API.
    expect(store.items[0]?.available_capacity).toBe(60)
    expect(store.items[0]?.registered_count).toBe(25)
    expect(store.items[0]?.capacity).toBe(100)

    mockedFetchSessionById.mockResolvedValueOnce(baseSession)
    await store.fetchSessionById(5, 10)
    expect(mockedFetchSessionById).toHaveBeenCalledWith(5, 10)
    expect(store.currentSession).toEqual(baseSession)

    const createdSession: SessionRead = {
      ...baseSession,
      id: 11,
      title: createPayload.title,
      speaker: createPayload.speaker,
      start_time: createPayload.start_time,
      end_time: createPayload.end_time,
      capacity: 40,
      registered_count: 0,
      available_capacity: 40,
    }
    mockedCreateSession.mockResolvedValueOnce(createdSession)
    const created = await store.createSession(5, createPayload)
    expect(created).toEqual(createdSession)
    expect(mockedCreateSession).toHaveBeenCalledWith(5, createPayload)
    const sentCreatePayload = mockedCreateSession.mock.calls[0]?.[1] ?? {}
    expect('event_id' in sentCreatePayload).toBe(false)
    expect(store.items).toHaveLength(2)
    expect(store.total).toBe(2)
    expect(store.currentSession).toEqual(createdSession)
    expect(store.items.find((item) => item.id === 11)).toEqual(
      createdSession,
    )

    const updatedSession: SessionRead = {
      ...createdSession,
      title: 'Taller de FastAPI avanzado',
    }
    mockedUpdateSession.mockResolvedValueOnce(updatedSession)
    const updated = await store.updateSession(5, 11, {
      title: 'Taller de FastAPI avanzado',
    })
    expect(mockedUpdateSession).toHaveBeenCalledWith(5, 11, {
      title: 'Taller de FastAPI avanzado',
    })
    expect(updated).toEqual(updatedSession)
    expect(store.items.find((item) => item.id === 11)).toEqual(
      updatedSession,
    )
    expect(store.total).toBe(2)

    mockedDeleteSession.mockResolvedValueOnce(undefined)
    await store.deleteSession(5, 11)
    expect(mockedDeleteSession).toHaveBeenCalledWith(5, 11)
    expect(store.items.find((item) => item.id === 11)).toBeUndefined()
    expect(store.total).toBe(1)
    expect(store.currentSession).toBeNull()

    mockedFetchSessions.mockRejectedValueOnce({
      response: {
        status: 500,
        data: { detail: 'No se pudo cargar la agenda del evento' },
      },
    })
    await store.fetchSessions(5)
    expect(store.errorMessage).toBe(
      'No se pudo cargar la agenda del evento',
    )
    expect(store.isLoading).toBe(false)
    expect(store.items).toEqual([])
    expect(store.total).toBe(0)

    mockedCreateSession.mockRejectedValueOnce({
      response: {
        status: 422,
        data: {
          detail: 'Error de validación en los datos enviados',
          errors: [
            {
              field: 'start_time',
              message:
                'La fecha y hora debe incluir zona horaria (por ejemplo, Z)',
            },
          ],
        },
      },
    })
    await expect(store.createSession(5, createPayload)).rejects.toBeTruthy()
    expect(store.errorMessage).toBe(
      'Error de validación en los datos enviados',
    )
    expect(store.fieldErrors).toEqual([
      {
        field: 'start_time',
        message:
          'La fecha y hora debe incluir zona horaria (por ejemplo, Z)',
      },
    ])
    expect(store.isSubmitting).toBe(false)

    mockedFetchSessionById.mockRejectedValueOnce({
      response: {
        status: 404,
        data: { detail: 'Sesión no encontrada' },
      },
    })
    await store.fetchSessionById(5, 99)
    expect(store.currentSession).toBeNull()
    expect(store.errorMessage).toBe('Sesión no encontrada')

    mockedUpdateSession.mockRejectedValueOnce({
      response: {
        status: 409,
        data: {
          detail: 'La sesión se solapa con otra sesión del evento',
        },
      },
    })
    await expect(
      store.updateSession(5, 10, { title: 'Solapada' }),
    ).rejects.toBeTruthy()
    expect(store.errorMessage).toBe(
      'La sesión se solapa con otra sesión del evento',
    )

    mockedDeleteSession.mockRejectedValueOnce({
      response: {
        status: 409,
        data: {
          detail:
            'No se puede eliminar una sesión con asistentes inscritos',
        },
      },
    })
    await expect(store.deleteSession(5, 10)).rejects.toBeTruthy()
    expect(store.errorMessage).toBe(
      'No se puede eliminar una sesión con asistentes inscritos',
    )

    mockedUpdateSession.mockResolvedValueOnce({
      ...baseSession,
      id: 12,
      title: 'Fuera de la lista',
    })
    await store.updateSession(5, 12, { title: 'Fuera de la lista' })
    expect(store.items.some((item) => item.id === 12)).toBe(true)

    store.clearErrors()
    expect(store.errorMessage).toBe('')
    expect(store.fieldErrors).toEqual([])

    store.reset()
    expect(store.items).toEqual([])
    expect(store.total).toBe(0)
    expect(store.currentSession).toBeNull()

    const storeSource = readFileSync(
      resolve(process.cwd(), 'src/stores/sessions.ts'),
      'utf-8',
    )
    expect(storeSource).not.toMatch(/available_capacity\s*-/)
    expect(storeSource).not.toMatch(/capacity\s*-\s*registered_count/)
  })

  it('SES-AC-26 calls the /api/events/{id}/sessions endpoints through the typed sessions service', async () => {
    const actualService =
      await vi.importActual<typeof import('@/services/sessions')>(
        '@/services/sessions',
      )

    expect(apiClient.defaults.baseURL).toBe('/api')

    const getSpy = vi
      .spyOn(apiClient, 'get')
      .mockResolvedValueOnce({ data: listResponse })
      .mockResolvedValueOnce({ data: baseSession })
    const postSpy = vi
      .spyOn(apiClient, 'post')
      .mockResolvedValueOnce({ data: baseSession })
    const patchSpy = vi
      .spyOn(apiClient, 'patch')
      .mockResolvedValueOnce({ data: baseSession })
    const deleteSpy = vi
      .spyOn(apiClient, 'delete')
      .mockResolvedValueOnce({ data: undefined })

    await actualService.fetchSessionsApi(5)
    expect(getSpy).toHaveBeenNthCalledWith(1, '/events/5/sessions')

    await actualService.fetchSessionByIdApi(5, 10)
    expect(getSpy).toHaveBeenNthCalledWith(2, '/events/5/sessions/10')

    await actualService.createSessionApi(5, createPayload)
    expect(postSpy).toHaveBeenCalledWith('/events/5/sessions', createPayload)
    expect('event_id' in createPayload).toBe(false)

    await actualService.updateSessionApi(5, 10, {
      title: 'Taller de FastAPI avanzado',
    })
    expect(patchSpy).toHaveBeenCalledWith('/events/5/sessions/10', {
      title: 'Taller de FastAPI avanzado',
    })

    await actualService.deleteSessionApi(5, 10)
    expect(deleteSpy).toHaveBeenCalledWith('/events/5/sessions/10')
  })
})
