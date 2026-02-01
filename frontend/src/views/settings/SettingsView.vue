<template>
  <div class="flex h-full min-h-0 flex-1 flex-col gap-3 overflow-hidden">
    <div class="flex items-center justify-between">
      <h1 class="font-display text-xl">Settings</h1>
    </div>

    <div class="flex min-h-0 flex-1 gap-4 overflow-hidden">
      <aside class="w-60 shrink-0 rounded-lg border border-border bg-surface p-3">
        <div class="space-y-1">
          <button
            v-for="section in sections"
            :key="section.key"
            class="flex w-full flex-col gap-1 rounded-md border border-transparent px-3 py-2 text-left transition"
            :class="
              section.key === activeSectionKey
                ? 'border-accent/50 bg-panel text-text'
                : 'text-muted hover:border-border hover:bg-panel/40'
            "
            type="button"
            @click="activeSectionKey = section.key"
          >
            <span class="text-sm font-medium text-text">{{ section.label }}</span>
            <span class="text-[11px] text-muted">{{ section.description }}</span>
          </button>
        </div>
      </aside>

      <section class="flex min-h-0 flex-1 flex-col overflow-hidden">
        <div class="flex min-h-0 flex-1 flex-col overflow-y-auto pr-1 scrollbar-hidden">
          <KeepAlive>
            <component :is="activeSection.component" />
          </KeepAlive>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import SettingsMarket from "@/views/settings/tabs/SettingsMarket.vue";
import SettingsDynamicAssets from "@/views/settings/tabs/SettingsDynamicAssets.vue";
import SettingsIntegration from "@/views/settings/tabs/SettingsIntegration.vue";
import SettingsCache from "@/views/settings/tabs/SettingsCache.vue";
import SettingsAiModels from "@/views/settings/tabs/SettingsAiModels.vue";
import SettingsTheme from "@/views/settings/tabs/SettingsTheme.vue";
import SettingsRiskManagement from "@/views/settings/tabs/SettingsRiskManagement.vue";
import { useExchangeStore } from "@/stores/exchangeStore";

defineOptions({ name: "SettingsView" });

const exchangeStore = useExchangeStore();

const baseSections = [
  {
    key: "market",
    label: "Market",
    description: "Assets, intervals, and scanner data source.",
    component: SettingsMarket,
  },
  {
    key: "dynamic-assets",
    label: "Dynamic Assets",
    description: "Configure multi-source asset feeds.",
    component: SettingsDynamicAssets,
  },
  {
    key: "integration",
    label: "Integration",
    description: "Telegram notifications and channels.",
    component: SettingsIntegration,
  },
  {
    key: "ai-models",
    label: "AI Models",
    description: "Provider credentials and default models.",
    component: SettingsAiModels,
  },
  {
    key: "cache",
    label: "Cache",
    description: "Retention, cleanup, and storage metrics.",
    component: SettingsCache,
  },
  {
    key: "theme",
    label: "Theme",
    description: "Visual profile and density styling.",
    component: SettingsTheme,
  },
];

const riskSection = {
  key: "risk-management",
  label: "Risk Management",
  description: "Goal tracking, exposure, and daily targets.",
  component: SettingsRiskManagement,
};

const storageKey = "settings.activeSection";
const activeSectionKey = ref(baseSections[0]?.key ?? "market");

const sections = computed(() => {
  const items = [...baseSections];
  if (exchangeStore.activeAccount) {
    items.splice(1, 0, riskSection);
  }
  return items;
});

const activeSection = computed(() => {
  const available = sections.value;
  return available.find((section) => section.key === activeSectionKey.value) || available[0];
});

const loadStoredSection = () => {
  if (typeof localStorage === "undefined") return;
  const stored = localStorage.getItem(storageKey);
  if (!stored) return;
  if (sections.value.some((section) => section.key === stored)) {
    activeSectionKey.value = stored;
  }
};

watch(activeSectionKey, (value) => {
  if (typeof localStorage === "undefined") return;
  localStorage.setItem(storageKey, value);
});

watch(
  sections,
  (available) => {
    if (!available.some((section) => section.key === activeSectionKey.value)) {
      activeSectionKey.value = available[0]?.key ?? "market";
    }
  },
  { immediate: true },
);

onMounted(() => {
  void exchangeStore.loadExchanges();
  loadStoredSection();
});
</script>
