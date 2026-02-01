<template>
  <div class="flex min-h-0 flex-1 flex-col gap-4">
    <BaseCard>
      <div class="flex items-start justify-between gap-3">
        <div>
          <div class="text-xs uppercase tracking-wide text-muted">Theme</div>
          <p class="mt-1 text-xs text-muted">
            Choose the visual profile for dense, real-time workflows.
          </p>
        </div>
        <BaseBadge>Active: {{ activeThemeLabel }}</BaseBadge>
      </div>

      <div class="mt-4 grid gap-3 sm:grid-cols-2">
        <button
          v-for="theme in themes"
          :key="theme.key"
          class="group rounded-md border border-border p-3 text-left transition"
          :class="
            theme.key === activeTheme
              ? 'border-accent/60 bg-panel text-text'
              : 'bg-panel/40 text-muted hover:border-border hover:bg-panel/60 hover:text-text'
          "
          type="button"
          :aria-pressed="theme.key === activeTheme"
          @click="applyTheme(theme.key)"
        >
          <div class="flex items-center justify-between">
            <div class="text-sm font-medium text-text">{{ theme.label }}</div>
            <span class="text-[10px] uppercase tracking-wide text-muted">{{ theme.tag }}</span>
          </div>
          <p class="mt-1 text-[11px] text-muted">{{ theme.description }}</p>
          <div class="mt-3 flex items-center gap-2">
            <span
              v-for="swatch in theme.swatches"
              :key="swatch"
              class="h-3 w-6 rounded-sm border border-border"
              :style="{ backgroundColor: swatch }"
            ></span>
          </div>
        </button>
      </div>

      <p class="mt-3 text-[11px] text-muted">
        Theme preference is saved locally and applied instantly.
      </p>
    </BaseCard>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import BaseBadge from "@/components/BaseBadge.vue";
import BaseCard from "@/components/BaseCard.vue";
import { useSettingsStore } from "@/stores/settingsStore";
import type { ThemeKey } from "@/types/settings";

type ThemeOption = {
  key: ThemeKey;
  label: string;
  description: string;
  tag: string;
  swatches: string[];
};

const themes: ThemeOption[] = [
  {
    key: "terminal",
    label: "Terminal",
    description: "High-density, precision-forward palette with institutional contrast.",
    tag: "Default",
    swatches: ["#0E1217", "#121820", "#1E2A38", "#007AFF", "#23C277", "#E45858"],
  },
  {
    key: "vanilla",
    label: "Vanilla",
    description: "Legacy theme with softer surfaces and rounded accents.",
    tag: "Legacy",
    swatches: ["#0B0F14", "#11161D", "#181E27", "#22C55E", "#F87171", "#FB923C"],
  },
];

const settingsStore = useSettingsStore();
const activeTheme = computed(() => settingsStore.theme);

const activeThemeLabel = computed(
  () => themes.find((theme) => theme.key === activeTheme.value)?.label ?? "Theme",
);

const applyTheme = (theme: ThemeKey) => {
  settingsStore.setTheme(theme);
};
</script>
