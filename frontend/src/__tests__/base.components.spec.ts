import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import BaseInput from '@/components/base/BaseInput.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseSpinner from '@/components/base/BaseSpinner.vue'
import BaseSkeleton from '@/components/base/BaseSkeleton.vue'
import BaseAlert from '@/components/base/BaseAlert.vue'

describe('Reusable base UI components', () => {
  it('PLAT-AC-17 renders BaseInput, BaseButton, BaseSpinner, BaseSkeleton and BaseAlert in Spanish without v-html', async () => {
    const inputWrapper = mount(BaseInput, {
      props: {
        id: 'email-field',
        label: 'Correo electrónico',
        modelValue: 'usuario@ejemplo.com',
        error: 'El correo electrónico no es válido',
        required: true,
      },
    })
    expect(inputWrapper.text()).toContain('Correo electrónico')
    expect(inputWrapper.text()).toContain('El correo electrónico no es válido')
    const inputEl = inputWrapper.find('input')
    expect(inputEl.attributes('aria-invalid')).toBe('true')
    await inputEl.setValue('nuevo@ejemplo.com')
    expect(inputWrapper.emitted('update:modelValue')?.[0]).toEqual([
      'nuevo@ejemplo.com',
    ])

    const buttonWrapper = mount(BaseButton, {
      props: {
        isLoading: true,
      },
      slots: {
        default: 'Guardar evento',
      },
    })
    expect(buttonWrapper.find('button').attributes('disabled')).toBeDefined()
    expect(buttonWrapper.findComponent(BaseSpinner).exists()).toBe(true)

    const spinnerWrapper = mount(BaseSpinner)
    expect(spinnerWrapper.text()).toContain('Cargando...')

    const skeletonWrapper = mount(BaseSkeleton, {
      props: { lines: 3 },
    })
    expect(skeletonWrapper.attributes('aria-busy')).toBe('true')

    const xssPayload = '<img src=x onerror=alert(1)>'
    const alertWrapper = mount(BaseAlert, {
      props: {
        type: 'error',
        message: `Error: ${xssPayload}`,
        dismissible: true,
      },
    })
    expect(alertWrapper.text()).toContain(xssPayload)
    expect(alertWrapper.find('img').exists()).toBe(false)

    const baseDir = resolve(process.cwd(), 'src/components/base')
    for (const fileName of [
      'BaseInput.vue',
      'BaseButton.vue',
      'BaseSpinner.vue',
      'BaseSkeleton.vue',
      'BaseAlert.vue',
    ]) {
      const source = readFileSync(resolve(baseDir, fileName), 'utf-8')
      expect(source).not.toContain('v-html')
    }
  })
})
