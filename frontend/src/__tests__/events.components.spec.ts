import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import EventCard from '@/components/events/EventCard.vue'
import EventForm from '@/components/events/EventForm.vue'
import type { EventRead } from '@/types/api'

const imageUrls = {
  w400: '/api/media/events/abc_400w.webp',
  w800: '/api/media/events/abc_800w.webp',
  w1200: '/api/media/events/abc_1200w.webp',
}

const publishedEvent: EventRead = {
  id: 1,
  title: 'Conferencia Python Colombia',
  description: 'Encuentro anual de desarrollo con FastAPI y Vue.',
  date: '2026-11-15T14:00:00Z',
  total_capacity: 100,
  registered_count: 25,
  // API value intentionally differs from total - registered (75) to prove
  // that the card never recomputes capacity on the client (R2.5).
  available_capacity: 60,
  status: 'PUBLISHED',
  organizer_id: 2,
  image_urls: imageUrls,
  created_at: '2026-10-31T15:00:00Z',
  updated_at: '2026-10-31T15:05:00Z',
}

function createTestRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div />' } },
      {
        path: '/events/:id',
        name: 'event-detail',
        component: { template: '<div />' },
      },
    ],
  })
}

async function mountCard(event: EventRead) {
  const router = createTestRouter()
  await router.push('/')
  await router.isReady()
  return mount(EventCard, {
    props: { event },
    global: { plugins: [router] },
  })
}

describe('EventCard responsive images, Spanish labels and API capacity', () => {
  it('EVT-AC-27 renders EventCard with responsive WebP srcset, Spanish status and API capacity', async () => {
    const wrapper = await mountCard(publishedEvent)

    expect(wrapper.text()).toContain('Conferencia Python Colombia')
    expect(wrapper.text()).toContain('Publicado')
    expect(wrapper.text()).toContain('60')
    expect(wrapper.text()).toContain('100')
    expect(wrapper.text()).not.toContain('75')
    expect(wrapper.text()).toContain('2026')

    const image = wrapper.find('img')
    expect(image.exists()).toBe(true)
    expect(image.attributes('src')).toBe(imageUrls.w800)
    expect(image.attributes('srcset')).toContain(
      `${imageUrls.w400} 400w`,
    )
    expect(image.attributes('srcset')).toContain(
      `${imageUrls.w800} 800w`,
    )
    expect(image.attributes('srcset')).toContain(
      `${imageUrls.w1200} 1200w`,
    )
    expect(image.attributes('sizes')).toBeTruthy()
    expect(image.attributes('loading')).toBe('lazy')
    expect(image.attributes('decoding')).toBe('async')
    expect(image.attributes('alt')).toBe(publishedEvent.title)
    expect(image.attributes('width')).toBeTruthy()
    expect(image.attributes('height')).toBeTruthy()

    const link = wrapper.find('a[href="/events/1"]')
    expect(link.exists()).toBe(true)

    const source = readFileSync(
      resolve(process.cwd(), 'src/components/events/EventCard.vue'),
      'utf-8',
    )
    expect(source).not.toContain('v-html')

    const draftWrapper = await mountCard({
      ...publishedEvent,
      status: 'DRAFT',
      image_urls: null,
    })
    expect(draftWrapper.text()).toContain('Borrador')
    expect(draftWrapper.find('img').exists()).toBe(false)
    expect(
      draftWrapper.find('[data-testid="event-image-placeholder"]').exists(),
    ).toBe(true)

    const cancelledWrapper = await mountCard({
      ...publishedEvent,
      status: 'CANCELLED',
    })
    expect(cancelledWrapper.text()).toContain('Cancelado')
  })
})

describe('EventForm validation, Spanish errors and optional image upload', () => {
  it('EVT-AC-30 validates and submits EventForm with optional image upload and Spanish field errors', async () => {
    const wrapper = mount(EventForm)

    const fileInput = wrapper.find('input#event-image')
    expect(fileInput.exists()).toBe(true)
    expect(fileInput.attributes('accept')).toBe(
      'image/jpeg,image/png,image/webp',
    )
    expect(fileInput.attributes('type')).toBe('file')

    await wrapper.find('form').trigger('submit.prevent')
    expect(wrapper.emitted('submit')).toBeUndefined()
    expect(wrapper.text()).toContain(
      'El título debe tener entre 3 y 160 caracteres',
    )
    expect(wrapper.text()).toContain(
      'La descripción debe tener entre 10 y 5000 caracteres',
    )
    expect(wrapper.text()).toContain(
      'La capacidad total debe estar entre 1 y 100000',
    )
    expect(wrapper.find('input#event-title').attributes('aria-invalid')).toBe(
      'true',
    )

    await wrapper.find('input#event-title').setValue('Conferencia Vue')
    await wrapper
      .find('textarea#event-description')
      .setValue('Encuentro de la comunidad Vue en Colombia')
    await wrapper.find('input#event-date').setValue('2026-12-01T10:00')
    await wrapper.find('input#event-capacity').setValue('30')
    await wrapper.find('select#event-status').setValue('PUBLISHED')

    const file = new File(['binary'], 'portada.png', { type: 'image/png' })
    const fileInputElement = wrapper.find('input#event-image')
      .element as HTMLInputElement
    Object.defineProperty(fileInputElement, 'files', {
      value: [file],
      configurable: true,
    })
    await wrapper.find('input#event-image').trigger('change')

    await wrapper.find('form').trigger('submit.prevent')

    const submitted = wrapper.emitted('submit')
    expect(submitted).toBeTruthy()
    expect(submitted?.[0]?.[0]).toEqual({
      title: 'Conferencia Vue',
      description: 'Encuentro de la comunidad Vue en Colombia',
      date: new Date('2026-12-01T10:00').toISOString(),
      total_capacity: 30,
      status: 'PUBLISHED',
    })
    expect(submitted?.[0]?.[1]).toBe(file)
  })

  it('EVT-AC-30 renders 422 field errors and conflict details from the API in Spanish', () => {
    const wrapper = mount(EventForm, {
      props: {
        initialEvent: publishedEvent,
        errorMessage: 'No se puede regresar un evento publicado a borrador',
        fieldErrors: {
          title: 'El título ya está en uso por otro evento',
        },
      },
    })

    expect(wrapper.text()).toContain(
      'No se puede regresar un evento publicado a borrador',
    )
    expect(wrapper.text()).toContain(
      'El título ya está en uso por otro evento',
    )
    expect(wrapper.find('input#event-title').attributes('aria-invalid')).toBe(
      'true',
    )

    const optionValues = wrapper
      .find('select#event-status')
      .findAll('option')
      .map((option) => option.attributes('value'))
    expect(optionValues).toEqual(['PUBLISHED'])
  })

  it('EVT-AC-30 disables a cancelled event form and keeps DRAFT to PUBLISHED transitions', () => {
    const cancelledWrapper = mount(EventForm, {
      props: {
        initialEvent: { ...publishedEvent, status: 'CANCELLED' },
      },
    })
    expect(cancelledWrapper.text()).toContain(
      'Un evento cancelado no puede cambiar de estado ni editarse',
    )
    expect(
      cancelledWrapper.find('input#event-title').attributes('disabled'),
    ).toBeDefined()
    expect(
      cancelledWrapper.find('select#event-status').attributes('disabled'),
    ).toBeDefined()
    expect(
      cancelledWrapper.find('button[data-testid="event-submit"]').attributes(
        'disabled',
      ),
    ).toBeDefined()

    const draftWrapper = mount(EventForm, {
      props: {
        initialEvent: { ...publishedEvent, status: 'DRAFT' },
      },
    })
    const draftOptions = draftWrapper
      .find('select#event-status')
      .findAll('option')
      .map((option) => option.attributes('value'))
    expect(draftOptions).toEqual(['DRAFT', 'PUBLISHED'])
  })
})
