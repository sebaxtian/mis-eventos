import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import SessionTimeline from '@/components/sessions/SessionTimeline.vue'
import SessionForm from '@/components/sessions/SessionForm.vue'
import type { SessionRead } from '@/types/api'

const openingSession: SessionRead = {
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
  // timeline never recomputes capacity on the client (R2.5).
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

describe('SessionTimeline chronological agenda, UTC times and API capacity', () => {
  it('SES-AC-27 renders SessionTimeline with speaker, UTC schedule and API capacity', () => {
    // The prop is deliberately out of chronological order.
    const wrapper = mount(SessionTimeline, {
      props: { sessions: [workshopSession, openingSession] },
    })

    const items = wrapper.findAll('[data-testid="session-item"]')
    expect(items).toHaveLength(2)

    const first = items[0]
    expect(first.text()).toContain('Apertura y bienvenida')
    expect(first.text()).toContain('Ana Torres')
    expect(first.text()).toContain('15:00')
    expect(first.text()).toContain('16:00')
    expect(first.text()).toContain('UTC')
    expect(first.text()).toContain('60')
    expect(first.text()).toContain('100')
    expect(first.text()).not.toContain('75')
    expect(first.text()).toContain('Presentación del programa del día.')

    const second = items[1]
    expect(second.text()).toContain('Taller de FastAPI')
    expect(second.text()).toContain('Luis Gómez')
    expect(second.text()).toContain('17:00')
    expect(second.text()).toContain('18:30')
    expect(second.text()).toContain('40')
    expect(second.text()).not.toContain(
      'Presentación del programa del día.',
    )

    const emptyWrapper = mount(SessionTimeline, {
      props: { sessions: [] },
    })
    expect(emptyWrapper.text()).toContain(
      'Este evento todavía no tiene sesiones programadas.',
    )
    expect(
      emptyWrapper.find('[data-testid="session-item"]').exists(),
    ).toBe(false)

    const source = readFileSync(
      resolve(process.cwd(), 'src/components/sessions/SessionTimeline.vue'),
      'utf-8',
    )
    expect(source).not.toContain('v-html')
    expect(source).toContain("timeZone: 'UTC'")
  })

  it('SES-AC-28 submits SessionForm converting datetime-local to UTC and maps 422/409 errors', async () => {
    function toLocalInput(isoDate: string): string {
      const parsed = new Date(isoDate)
      const pad = (value: number): string => String(value).padStart(2, '0')
      return `${parsed.getFullYear()}-${pad(parsed.getMonth() + 1)}-${pad(
        parsed.getDate(),
      )}T${pad(parsed.getHours())}:${pad(parsed.getMinutes())}`
    }

    const createWrapper = mount(SessionForm, { props: { eventId: 5 } })
    expect(
      createWrapper.find('label[for="session-start-time"]').text(),
    ).toContain('hora local')
    expect(
      createWrapper.find('label[for="session-end-time"]').text(),
    ).toContain('hora local')
    await createWrapper
      .find('form[data-testid="session-form"]')
      .trigger('submit.prevent')

    expect(createWrapper.emitted('submit')).toBeUndefined()
    expect(createWrapper.text()).toContain(
      'El título debe tener entre 3 y 160 caracteres',
    )
    expect(createWrapper.text()).toContain(
      'El ponente debe tener entre 2 y 120 caracteres',
    )
    expect(createWrapper.text()).toContain(
      'La capacidad de la sesión debe estar entre 1 y 100000',
    )
    expect(
      createWrapper.find('input#session-title').attributes('aria-invalid'),
    ).toBe('true')

    await createWrapper
      .find('input#session-title')
      .setValue('Taller de FastAPI')
    await createWrapper
      .find('input#session-speaker')
      .setValue('Luis Gómez')
    await createWrapper
      .find('textarea#session-description')
      .setValue('Taller práctico de la API.')
    await createWrapper
      .find('input#session-start-time')
      .setValue('2026-11-15T15:00')
    await createWrapper
      .find('input#session-end-time')
      .setValue('2026-11-15T16:30')
    await createWrapper.find('input#session-capacity').setValue('40')
    await createWrapper
      .find('form[data-testid="session-form"]')
      .trigger('submit.prevent')

    const submitted = createWrapper.emitted('submit')
    expect(submitted).toBeTruthy()
    const payload = submitted?.[0]?.[0] as Record<string, unknown>
    expect(payload).toEqual({
      title: 'Taller de FastAPI',
      speaker: 'Luis Gómez',
      description: 'Taller práctico de la API.',
      start_time: new Date('2026-11-15T15:00').toISOString(),
      end_time: new Date('2026-11-15T16:30').toISOString(),
      capacity: 40,
    })
    expect(String(payload.start_time)).toMatch(/Z$/)
    expect(String(payload.end_time)).toMatch(/Z$/)
    expect('event_id' in payload).toBe(false)

    await createWrapper
      .find('textarea#session-description')
      .setValue('   ')
    await createWrapper
      .find('form[data-testid="session-form"]')
      .trigger('submit.prevent')
    const secondPayload = createWrapper.emitted('submit')?.[1]?.[0] as Record<
      string,
      unknown
    >
    expect(secondPayload.description).toBeNull()

    const editWrapper = mount(SessionForm, {
      props: { eventId: 5, session: openingSession },
    })
    const startInput = editWrapper.find('input#session-start-time')
      .element as HTMLInputElement
    expect(startInput.value).toBe(
      toLocalInput(openingSession.start_time),
    )
    const endInput = editWrapper.find('input#session-end-time')
      .element as HTMLInputElement
    expect(endInput.value).toBe(toLocalInput(openingSession.end_time))
    expect(
      (editWrapper.find('input#session-title').element as HTMLInputElement)
        .value,
    ).toBe(openingSession.title)

    await editWrapper
      .find('input#session-title')
      .setValue('Apertura actualizada')
    await editWrapper
      .find('form[data-testid="session-form"]')
      .trigger('submit.prevent')
    const editPayload = editWrapper.emitted('submit')?.[0]?.[0] as Record<
      string,
      unknown
    >
    expect(editPayload.title).toBe('Apertura actualizada')
    expect(editPayload.start_time).toBe(
      new Date(openingSession.start_time).toISOString(),
    )
    expect(editPayload.end_time).toBe(
      new Date(openingSession.end_time).toISOString(),
    )
    expect(editPayload.description).toBe(openingSession.description)
    expect('event_id' in editPayload).toBe(false)

    const errorWrapper = mount(SessionForm, {
      props: {
        eventId: 5,
        errorMessage: 'La sesión se solapa con otra sesión del evento',
        fieldErrors: [
          {
            field: 'start_time',
            message:
              'La fecha y hora debe incluir zona horaria (por ejemplo, Z)',
          },
        ],
      },
    })
    expect(errorWrapper.text()).toContain(
      'La sesión se solapa con otra sesión del evento',
    )
    expect(errorWrapper.text()).toContain(
      'La fecha y hora debe incluir zona horaria (por ejemplo, Z)',
    )
    expect(
      errorWrapper
        .find('input#session-start-time')
        .attributes('aria-invalid'),
    ).toBe('true')

    const disabledWrapper = mount(SessionForm, {
      props: { eventId: 5, disabled: true },
    })
    expect(
      disabledWrapper
        .find('input#session-title')
        .attributes('disabled'),
    ).toBeDefined()
    expect(
      disabledWrapper
        .find('button[data-testid="session-submit"]')
        .attributes('disabled'),
    ).toBeDefined()

    const orderWrapper = mount(SessionForm, { props: { eventId: 5 } })
    await orderWrapper
      .find('input#session-title')
      .setValue('Sesión invertida')
    await orderWrapper
      .find('input#session-speaker')
      .setValue('Ana Torres')
    await orderWrapper
      .find('input#session-start-time')
      .setValue('2026-11-15T18:00')
    await orderWrapper
      .find('input#session-end-time')
      .setValue('2026-11-15T17:00')
    await orderWrapper.find('input#session-capacity').setValue('10')
    await orderWrapper
      .find('form[data-testid="session-form"]')
      .trigger('submit.prevent')
    expect(orderWrapper.emitted('submit')).toBeUndefined()
    expect(orderWrapper.text()).toContain(
      'La hora de inicio debe ser anterior a la hora de fin',
    )

    await orderWrapper
      .find('textarea#session-description')
      .setValue('x'.repeat(2001))
    await orderWrapper
      .find('input#session-start-time')
      .setValue('2026-11-15T15:00')
    await orderWrapper
      .find('input#session-end-time')
      .setValue('2026-11-15T16:00')
    await orderWrapper
      .find('form[data-testid="session-form"]')
      .trigger('submit.prevent')
    expect(orderWrapper.emitted('submit')).toBeUndefined()
    expect(orderWrapper.text()).toContain(
      'La descripción no debe superar los 2000 caracteres',
    )

    const source = readFileSync(
      resolve(process.cwd(), 'src/components/sessions/SessionForm.vue'),
      'utf-8',
    )
    expect(source).toContain('toISOString')
    expect(source).not.toContain('v-html')
    expect(source).not.toContain('apiClient')
    expect(source).not.toContain('services/sessions')
  })
})
