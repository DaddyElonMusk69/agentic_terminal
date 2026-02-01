<template>
  <div class="flex h-screen overflow-hidden bg-base text-text">
    <Sidebar
      :collapsed="isCollapsed"
      @toggle-collapse="isCollapsed = !isCollapsed"
      @open-exchange="showExchangeModal = true"
    />

    <div class="flex min-h-0 min-w-0 flex-1 flex-col">
      <TopBanner :price-tape="priceTape" :news-tape="newsTape" />
      <main class="flex min-h-0 flex-1 overflow-hidden">
        <div class="flex min-h-0 flex-1 flex-col p-4 md:p-6">
          <slot />
        </div>
      </main>
    </div>

    <ExchangeModal
      :open="showExchangeModal"
      @close="showExchangeModal = false"
    />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import Sidebar from "@/layouts/Sidebar.vue";
import TopBanner from "@/layouts/TopBanner.vue";
import ExchangeModal from "@/components/ExchangeModal.vue";
import { useExchangeStore } from "@/stores/exchangeStore";
import { useAutomationStore } from "@/stores/automationStore";
import { useScannerEmaStore } from "@/stores/scannerEmaStore";
import { useScannerQuantStore } from "@/stores/scannerQuantStore";
import type { NewsItem, PriceItem } from "@/types/banner";

const sidebarStorageKey = "td_sidebar_collapsed";
const readSidebarStorage = () => {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(sidebarStorageKey);
    if (raw === null) return null;
    return raw === "true";
  } catch {
    return null;
  }
};
const writeSidebarStorage = (value: boolean) => {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(sidebarStorageKey, value ? "true" : "false");
  } catch {
    // Ignore storage errors.
  }
};

const isCollapsed = ref(readSidebarStorage() ?? false);
const showExchangeModal = ref(false);
const exchangeStore = useExchangeStore();
const emaStore = useScannerEmaStore();
const quantStore = useScannerQuantStore();
const automationStore = useAutomationStore();

const priceTape: PriceItem[] = [
  { label: "BTC", value: "0.00", change: "0.00%" },
  { label: "ETH", value: "0.00", change: "0.00%" },
  { label: "SOL", value: "0.00", change: "0.00%" },
];

const newsTape: NewsItem[] = [
  { text: "News feed ready" },
  { text: "Exchange switching syncs data across views" },
];

const connectSockets = (exchangeId?: string | null) => {
  const resolvedId = exchangeId || undefined;
  emaStore.connectSocket(resolvedId);
  quantStore.connectSocket(resolvedId);
  if (automationStore.status.isRunning) {
    automationStore.connectSocket(resolvedId);
  } else {
    automationStore.deferDisconnect("stopped");
  }
};

onMounted(() => {
  connectSockets(exchangeStore.activeExchangeId);
  void exchangeStore.loadExchanges();
});

watch(
  () => exchangeStore.activeExchangeId,
  (exchangeId) => {
    connectSockets(exchangeId);
  },
);

watch(
  () => automationStore.status.isRunning,
  (isRunning) => {
    const exchangeId = exchangeStore.activeExchangeId || undefined;
    if (isRunning) {
      automationStore.pendingDisconnect = null;
      automationStore.connectSocket(exchangeId);
    } else {
      automationStore.deferDisconnect("stopped");
    }
  },
);

watch(
  () => isCollapsed.value,
  (value) => {
    writeSidebarStorage(value);
  },
  { immediate: true },
);
</script>
