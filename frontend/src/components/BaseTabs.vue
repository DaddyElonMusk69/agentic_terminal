<template>
  <div class="flex flex-wrap gap-2">
    <button
      v-for="tab in tabs"
      :key="tab.key"
      class="rounded-full border px-4 py-1 text-xs uppercase tracking-wide"
      :class="
        tab.key === modelValue
          ? 'border-accent bg-panel text-text'
          : 'border-border text-muted hover:text-text'
      "
      type="button"
      @click="$emit('update:modelValue', tab.key)"
    >
      {{ tab.label }}
    </button>
  </div>
</template>

<script setup lang="ts">
type TabItem = { key: string; label: string };

defineProps<{ modelValue: string; tabs: TabItem[] }>();

defineEmits<{
  (event: "update:modelValue", value: string): void;
}>();
</script>
