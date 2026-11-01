import apiClient from '@/services/api'
import type {
  EventCreatePayload,
  EventListQuery,
  EventListResponse,
  EventRead,
  EventUpdatePayload,
} from '@/types/api'

export async function fetchEventsApi(
  params: EventListQuery = {},
): Promise<EventListResponse> {
  const response = await apiClient.get<EventListResponse>('/events', {
    params,
  })
  return response.data
}

export async function fetchEventByIdApi(id: number): Promise<EventRead> {
  const response = await apiClient.get<EventRead>(`/events/${id}`)
  return response.data
}

export async function createEventApi(
  payload: EventCreatePayload,
): Promise<EventRead> {
  const response = await apiClient.post<EventRead>('/events', payload)
  return response.data
}

export async function updateEventApi(
  id: number,
  payload: EventUpdatePayload,
): Promise<EventRead> {
  const response = await apiClient.patch<EventRead>(`/events/${id}`, payload)
  return response.data
}

export async function deleteEventApi(id: number): Promise<void> {
  await apiClient.delete(`/events/${id}`)
}

export async function uploadEventImageApi(
  id: number,
  file: File,
): Promise<EventRead> {
  const formData = new FormData()
  formData.append('file', file)
  const response = await apiClient.post<EventRead>(
    `/events/${id}/image`,
    formData,
    {
      // The shared client defaults to application/json. Unset it for this
      // request so Axios keeps FormData and the runtime adds the multipart
      // boundary instead of serializing the form to JSON.
      headers: { 'Content-Type': undefined },
    },
  )
  return response.data
}
