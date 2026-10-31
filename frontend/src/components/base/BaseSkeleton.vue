<script setup lang="ts">
withDefaults(
  defineProps<{
    lines?: number
  }>(),
  {
    lines: 3,
  },
)
</script>

<template>
  <div
    role="status"
    aria-busy="true"
    aria-label="Cargando contenido"
    class="animate-pulse space-y-2"
  >
    <div
      v-for="idx in lines"
      :key="idx"
      class="h-4 rounded bg-slate-200"
    />
  </div>
</template>
