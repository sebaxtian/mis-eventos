<script setup lang="ts">
withDefaults(
  defineProps<{
    type?: 'success' | 'error' | 'warning' | 'info'
    message: string
    dismissible?: boolean
  }>(),
  {
    type: 'info',
    dismissible: false,
  },
)

const emit = defineEmits<{
  dismiss: []
}>()
</script>

<template>
  <div
    role="alert"
    class="flex items-center justify-between rounded-md border px-4 py-3 text-sm"
    :class="{
      'border-emerald-300 bg-emerald-50 text-emerald-900': type === 'success',
      'border-red-300 bg-red-50 text-red-900': type === 'error',
      'border-amber-300 bg-amber-50 text-amber-900': type === 'warning',
      'border-sky-300 bg-sky-50 text-sky-900': type === 'info',
    }"
  >
    <span>{{ message }}</span>
    <button
      v-if="dismissible"
      type="button"
      aria-label="Cerrar aviso"
      class="ml-3 text-xs font-semibold underline"
      @click="emit('dismiss')"
    >
      Cerrar
    </button>
  </div>
</template>
