<template>
  <div class="rounded-lg border border-dashed border-border bg-surface p-6 text-center">
    <div class="font-display text-sm text-text">{{ title }}</div>
    <div v-if="subtitle" class="mt-1 text-xs text-muted">{{ subtitle }}</div>
    <div class="mt-4">
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ title: string; subtitle?: string }>();
</script>
