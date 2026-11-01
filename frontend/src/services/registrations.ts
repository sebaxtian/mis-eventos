import apiClient from '@/services/api'
import type {
  EventRegistrationListQuery,
  RegistrationListQuery,
  RegistrationListResponse,
  RegistrationRead,
} from '@/types/api'

export interface RegistrationMutationResult {
  registration: RegistrationRead
  created: boolean
}

export async function fetchMyRegistrationsApi(
  params: RegistrationListQuery = {},
): Promise<RegistrationListResponse> {
  const response = await apiClient.get<RegistrationListResponse>(
    '/registrations/me',
    { params },
  )
  return response.data
}

export async function fetchEventRegistrationsApi(
  eventId: number,
  params: EventRegistrationListQuery = {},
): Promise<RegistrationListResponse> {
  const response = await apiClient.get<RegistrationListResponse>(
    `/events/${eventId}/registrations`,
    { params },
  )
  return response.data
}

export async function fetchRegistrationByIdApi(
  id: number,
): Promise<RegistrationRead> {
  const response = await apiClient.get<RegistrationRead>(
    `/registrations/${id}`,
  )
  return response.data
}

export async function registerForEventApi(
  eventId: number,
): Promise<RegistrationMutationResult> {
  const response = await apiClient.post<RegistrationRead>(
    `/events/${eventId}/registrations`,
  )
  return {
    registration: response.data,
    created: response.status === 201,
  }
}

export async function registerForSessionApi(
  eventId: number,
  sessionId: number,
): Promise<RegistrationMutationResult> {
  const response = await apiClient.post<RegistrationRead>(
    `/events/${eventId}/sessions/${sessionId}/registrations`,
  )
  return {
    registration: response.data,
    created: response.status === 201,
  }
}

export async function cancelRegistrationApi(id: number): Promise<void> {
  await apiClient.delete(`/registrations/${id}`)
}
