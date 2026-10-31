<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    modelValue?: string | number
    label?: string
    type?: string
    placeholder?: string
    error?: string
    id?: string
    required?: boolean
    disabled?: boolean
  }>(),
  {
    modelValue: '',
    label: '',
    type: 'text',
    placeholder: '',
    error: '',
    id: 'base-input',
    required: false,
    disabled: false,
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const errorId = computed(() => `${props.id}-error`)

function onInput(event: Event): void {
  const target = event.target as HTMLInputElement
  emit('update:modelValue', target.value)
}
</script>

<template>
  <div class="flex flex-col gap-1">
    <label
      v-if="label"
      :for="id"
      class="text-sm font-medium text-slate-700"
    >
      {{ label }}
      <span v-if="required" class="text-red-600">*</span>
    </label>
    <input
      :id="id"
      :type="type"
      :value="modelValue"
      :placeholder="placeholder"
      :required="required"
      :disabled="disabled"
      :aria-invalid="error ? 'true' : 'false'"
      :aria-describedby="error ? errorId : undefined"
      class="rounded-md border px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2"
      :class="
        error
          ? 'border-red-500 focus:ring-red-500'
          : 'border-slate-300 focus:ring-indigo-500'
      "
      @input="onInput"
    />
    <p
      v-if="error"
      :id="errorId"
      role="alert"
      class="text-xs text-red-600"
    >
      {{ error }}
    </p>
  </div>
</template>
