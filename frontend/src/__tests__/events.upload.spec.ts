import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import type { InternalAxiosRequestConfig } from 'axios'
import apiClient from '@/services/api'
import { uploadEventImageApi } from '@/services/events'
import type { EventRead } from '@/types/api'

const uploadedEvent: EventRead = {
  id: 1,
  title: 'Conferencia Python Colombia',
  description: 'Encuentro anual de desarrollo con FastAPI y Vue.',
  date: '2026-11-15T14:00:00Z',
  total_capacity: 100,
  registered_count: 0,
  available_capacity: 100,
  status: 'PUBLISHED',
  organizer_id: 2,
  image_urls: {
    w400: '/api/media/events/abc_400w.webp',
    w800: '/api/media/events/abc_800w.webp',
    w1200: '/api/media/events/abc_1200w.webp',
  },
  created_at: '2026-10-31T15:00:00Z',
  updated_at: '2026-10-31T15:05:00Z',
}

describe('EVT-AC-30 event image upload uses multipart FormData', () => {
  let originalAdapter: typeof apiClient.defaults.adapter

  beforeEach(() => {
    setActivePinia(createPinia())
    window.sessionStorage.clear()
    originalAdapter = apiClient.defaults.adapter
  })

  afterEach(() => {
    apiClient.defaults.adapter = originalAdapter
  })

  it('EVT-AC-30 sends the transformed request as FormData instead of JSON', async () => {
    let capturedConfig: InternalAxiosRequestConfig | undefined

    apiClient.defaults.adapter = async (config) => {
      capturedConfig = config
      return {
        data: uploadedEvent,
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      }
    }

    const file = new File(['binary'], 'portada.png', {
      type: 'image/png',
    })

    const result = await uploadEventImageApi(1, file)

    expect(result).toEqual(uploadedEvent)
    expect(capturedConfig).toBeDefined()
    expect(capturedConfig?.url).toBe('/events/1/image')

    // The adapter receives the request after Axios transformRequest runs.
    // It must still be FormData, never a JSON string.
    expect(capturedConfig?.data).toBeInstanceOf(FormData)
    expect(typeof capturedConfig?.data).not.toBe('string')

    const formData = capturedConfig?.data as FormData
    expect(formData.get('file')).toBe(file)

    const contentType = capturedConfig?.headers.get('Content-Type')
    expect(contentType).not.toBe('application/json')
  })
})
