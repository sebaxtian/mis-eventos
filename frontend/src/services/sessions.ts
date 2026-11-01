import apiClient from '@/services/api'
import type {
  SessionCreatePayload,
  SessionListResponse,
  SessionRead,
  SessionUpdatePayload,
} from '@/types/api'

export async function fetchSessionsApi(
  eventId: number,
): Promise<SessionListResponse> {
  const response = await apiClient.get<SessionListResponse>(
    `/events/${eventId}/sessions`,
  )
  return response.data
}

export async function fetchSessionByIdApi(
  eventId: number,
  sessionId: number,
): Promise<SessionRead> {
  const response = await apiClient.get<SessionRead>(
    `/events/${eventId}/sessions/${sessionId}`,
  )
  return response.data
}

export async function createSessionApi(
  eventId: number,
  payload: SessionCreatePayload,
): Promise<SessionRead> {
  const response = await apiClient.post<SessionRead>(
    `/events/${eventId}/sessions`,
    payload,
  )
  return response.data
}

export async function updateSessionApi(
  eventId: number,
  sessionId: number,
  payload: SessionUpdatePayload,
): Promise<SessionRead> {
  const response = await apiClient.patch<SessionRead>(
    `/events/${eventId}/sessions/${sessionId}`,
    payload,
  )
  return response.data
}

export async function deleteSessionApi(
  eventId: number,
  sessionId: number,
): Promise<void> {
  await apiClient.delete(`/events/${eventId}/sessions/${sessionId}`)
}
