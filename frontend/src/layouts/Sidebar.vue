<template>
  <aside
    class="flex h-screen flex-none flex-col overflow-hidden border-r border-border bg-surface transition-all duration-300"
    :class="collapsed ? 'w-16' : 'w-64'"
  >
    <div
      class="relative flex items-center py-4"
      :class="collapsed ? 'justify-center px-0' : 'justify-end px-3'"
    >
      <div
        class="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 font-display text-xs uppercase tracking-[0.2em] text-muted transition-[opacity,transform] duration-200 ease-out"
        :class="collapsed ? 'opacity-0 -translate-x-2' : 'opacity-100 translate-x-0 delay-300'"
      >
        <span class="block whitespace-nowrap">Trading Desk</span>
      </div>
      <button
        class="rounded-md border border-border bg-panel px-2 py-1 text-xs text-muted hover:text-text"
        type="button"
        @click="$emit('toggle-collapse')"
      >
        {{ collapsed ? ">" : "<" }}
      </button>
    </div>

    <nav class="flex-1 space-y-1 px-2">
      <RouterLink
        v-for="(item, index) in navItems"
        :key="item.to"
        :to="item.to"
        class="relative flex h-9 items-center rounded-md px-3 py-2 text-sm text-muted transition hover:bg-panel hover:text-text"
        active-class="bg-panel text-text"
      >
        <span
          class="absolute top-1/2 flex h-7 w-7 flex-none -translate-y-1/2 items-center justify-center rounded-md border shadow-[inset_0_0_0_1px_rgba(255,255,255,0.04)] transition-[left,transform] duration-200 ease-out"
          :class="[
            item.badgeClass,
            collapsed
              ? 'left-1/2 -translate-x-1/2 delay-200'
              : 'left-3 translate-x-0 delay-0',
          ]"
        >
          <svg
            v-if="item.icon === 'ema'"
            class="h-4 w-4"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
          >
            <path d="M4 15l4-4 4 4 6-6 2 2" />
            <circle cx="18" cy="9" r="2" fill="currentColor" stroke="none" />
          </svg>
          <svg
            v-else-if="item.icon === 'quant'"
            class="h-4 w-4"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.6"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
          >
            <rect x="4" y="4" width="6" height="6" rx="1.4" />
            <rect x="14" y="4" width="6" height="6" rx="1.4" />
            <rect x="4" y="14" width="6" height="6" rx="1.4" />
            <rect x="14" y="14" width="6" height="6" rx="1.4" />
          </svg>
          <svg
            v-else-if="item.icon === 'agent'"
            class="h-4 w-4"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.6"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
          >
            <circle cx="12" cy="8" r="3.2" />
            <path d="M5 19c1.8-3 12.2-3 14 0" />
          </svg>
          <svg
            v-else-if="item.icon === 'automation'"
            class="h-4 w-4"
            viewBox="0 0 24 24"
            fill="currentColor"
            aria-hidden="true"
          >
            <path d="M13 3L5 14h6l-1 7 8-11h-6z" />
          </svg>
          <svg
            v-else-if="item.icon === 'observability'"
            class="h-4 w-4"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.6"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
          >
            <circle cx="12" cy="12" r="8" />
            <circle cx="12" cy="12" r="3" />
            <path d="M12 4v2" />
            <path d="M20 12h-2" />
            <path d="M12 20v-2" />
            <path d="M4 12h2" />
          </svg>
          <svg
            v-else
            class="h-4 w-4"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.6"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
          >
            <path d="M4 7h16" />
            <circle cx="9" cy="7" r="2" fill="currentColor" stroke="none" />
            <path d="M4 17h16" />
            <circle cx="15" cy="17" r="2" fill="currentColor" stroke="none" />
          </svg>
        </span>
        <span
          class="pointer-events-none absolute left-12 top-1/2 -translate-y-1/2 whitespace-nowrap transition-[opacity,transform] duration-160 ease-out"
          :class="collapsed ? 'opacity-0 -translate-x-4' : 'opacity-100 translate-x-0'"
          :style="{
            transitionDelay: collapsed
              ? `${(navItems.length - 1 - index) * 30}ms`
              : `${120 + index * 40}ms`,
          }"
        >
          {{ item.label }}
        </span>
      </RouterLink>
    </nav>

    <div class="flex flex-col gap-2 p-3">
      <button
        class="relative flex h-9 w-full items-center rounded-md border border-transparent bg-transparent px-3 text-[11px] text-muted/70 opacity-80 transition hover:bg-panel/60 hover:text-text hover:opacity-100 disabled:opacity-50"
        type="button"
        :disabled="!fullscreenSupported"
        :title="isFullscreen ? 'Exit fullscreen' : 'Enter fullscreen'"
        @click="toggleFullscreen"
      >
        <span
          class="absolute top-1/2 flex h-7 w-7 flex-none -translate-y-1/2 items-center justify-center rounded-md border bg-panel shadow-[inset_0_0_0_1px_rgba(255,255,255,0.04)] transition-[left,transform] duration-200 ease-out"
          :class="[
            isFullscreen
              ? 'border-accent/40 bg-accent/10 text-accent'
              : 'border-border/60 bg-panel/60 text-muted',
            collapsed
              ? 'left-1/2 -translate-x-1/2 delay-200'
              : 'left-3 translate-x-0 delay-0',
          ]"
        >
          <svg
            v-if="isFullscreen"
            class="h-3 w-3"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
          >
            <path d="M9 3H5v4" />
            <path d="M15 3h4v4" />
            <path d="M9 21H5v-4" />
            <path d="M15 21h4v-4" />
            <path d="M9 9l6 6" />
          </svg>
          <svg
            v-else
            class="h-3 w-3"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
          >
            <path d="M9 3H5v4" />
            <path d="M15 3h4v4" />
            <path d="M9 21H5v-4" />
            <path d="M15 21h4v-4" />
          </svg>
        </span>
        <span
          class="pointer-events-none absolute left-12 top-1/2 -translate-y-1/2 whitespace-nowrap transition-[opacity,transform] duration-160 ease-out"
          :class="collapsed ? 'opacity-0 -translate-x-4' : 'opacity-100 translate-x-0'"
        >
          {{ isFullscreen ? "Exit Fullscreen" : "Fullscreen" }}
        </span>
      </button>
      <button
        class="relative flex h-10 w-full items-center rounded-md border border-border bg-panel px-3 py-2 text-xs text-muted transition hover:text-text"
        type="button"
        @click="$emit('open-exchange')"
      >
        <ExchangeBadge
          :exchange="activeAccount?.exchange"
          size="sm"
          class="absolute top-1/2 h-7 w-7 -translate-y-1/2 transition-[left,transform] duration-200 ease-out"
          :class="
            collapsed
              ? 'left-1/2 -translate-x-1/2 delay-200'
              : 'left-3 translate-x-0 delay-0'
          "
        />
        <span
          class="pointer-events-none absolute left-12 top-1/2 -translate-y-1/2 transition-[opacity,transform] duration-160 ease-out"
          :class="collapsed ? 'opacity-0 -translate-x-4' : 'opacity-100 translate-x-0'"
        >
          <span class="block max-w-[140px] truncate text-[11px] font-semibold text-text">
            {{ activeAccount ? activeAccount.name : "Exchange" }}
          </span>
          <span class="block max-w-[140px] truncate text-[10px] text-muted">
            {{ activeAccount ? exchangeLabel(activeAccount.exchange) : "Connect account" }}
          </span>
        </span>
        <span
          v-if="activeAccount"
          class="absolute right-3 top-1/2 h-2 w-2 -translate-y-1/2 rounded-full bg-positive transition-opacity duration-150"
          :class="collapsed ? 'opacity-0' : 'opacity-100'"
        ></span>
      </button>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { RouterLink } from "vue-router";
import { useExchangeStore } from "@/stores/exchangeStore";
import ExchangeBadge from "@/components/ExchangeBadge.vue";

defineProps<{ collapsed: boolean }>();

defineEmits<{
  (event: "toggle-collapse"): void;
  (event: "open-exchange"): void;
}>();

const isFullscreen = ref(false);
const fullscreenSupported = ref(false);
const exchangeStore = useExchangeStore();
const activeAccount = computed(() => exchangeStore.activeAccount);

const syncFullscreenState = () => {
  if (typeof document === "undefined") return;
  const doc = document as Document & {
    webkitFullscreenElement?: Element | null;
    mozFullScreenElement?: Element | null;
    msFullscreenElement?: Element | null;
  };
  isFullscreen.value = Boolean(
    doc.fullscreenElement ||
      doc.webkitFullscreenElement ||
      doc.mozFullScreenElement ||
      doc.msFullscreenElement,
  );
};

const resolveFullscreenSupport = () => {
  if (typeof document === "undefined") return false;
  const element = document.documentElement as HTMLElement & {
    webkitRequestFullscreen?: () => Promise<void> | void;
    mozRequestFullScreen?: () => Promise<void> | void;
    msRequestFullscreen?: () => Promise<void> | void;
  };
  return Boolean(
    element.requestFullscreen ||
      element.webkitRequestFullscreen ||
      element.mozRequestFullScreen ||
      element.msRequestFullscreen,
  );
};

const enterFullscreen = async () => {
  const element = document.documentElement as HTMLElement & {
    webkitRequestFullscreen?: () => Promise<void> | void;
    mozRequestFullScreen?: () => Promise<void> | void;
    msRequestFullscreen?: () => Promise<void> | void;
  };
  if (element.requestFullscreen) {
    await element.requestFullscreen();
  } else if (element.webkitRequestFullscreen) {
    element.webkitRequestFullscreen();
  } else if (element.mozRequestFullScreen) {
    element.mozRequestFullScreen();
  } else if (element.msRequestFullscreen) {
    element.msRequestFullscreen();
  }
};

const exitFullscreen = async () => {
  const doc = document as Document & {
    webkitExitFullscreen?: () => Promise<void> | void;
    mozCancelFullScreen?: () => Promise<void> | void;
    msExitFullscreen?: () => Promise<void> | void;
  };
  if (doc.exitFullscreen) {
    await doc.exitFullscreen();
  } else if (doc.webkitExitFullscreen) {
    doc.webkitExitFullscreen();
  } else if (doc.mozCancelFullScreen) {
    doc.mozCancelFullScreen();
  } else if (doc.msExitFullscreen) {
    doc.msExitFullscreen();
  }
};

const toggleFullscreen = async () => {
  if (!fullscreenSupported.value) return;
  if (isFullscreen.value) {
    await exitFullscreen();
  } else {
    await enterFullscreen();
  }
};

const unifiedBadgeClass = "border-text/40 bg-text/10 text-text";

const navItems = [
  {
    label: "EMA Scanner",
    to: "/scanner/ema",
    icon: "ema",
    badgeClass: unifiedBadgeClass,
  },
  {
    label: "Quant Scanner",
    to: "/scanner/quant",
    icon: "quant",
    badgeClass: unifiedBadgeClass,
  },
  {
    label: "Agent",
    to: "/agent",
    icon: "agent",
    badgeClass: unifiedBadgeClass,
  },
  {
    label: "Automation",
    to: "/automation",
    icon: "automation",
    badgeClass: unifiedBadgeClass,
  },
  {
    label: "Observability",
    to: "/observability",
    icon: "observability",
    badgeClass: unifiedBadgeClass,
  },
  {
    label: "Settings",
    to: "/settings",
    icon: "settings",
    badgeClass: unifiedBadgeClass,
  },
];

onMounted(() => {
  fullscreenSupported.value = resolveFullscreenSupport();
  syncFullscreenState();
  document.addEventListener("fullscreenchange", syncFullscreenState);
  document.addEventListener("webkitfullscreenchange", syncFullscreenState);
  document.addEventListener("mozfullscreenchange", syncFullscreenState);
  document.addEventListener("MSFullscreenChange", syncFullscreenState);
});

onBeforeUnmount(() => {
  document.removeEventListener("fullscreenchange", syncFullscreenState);
  document.removeEventListener("webkitfullscreenchange", syncFullscreenState);
  document.removeEventListener("mozfullscreenchange", syncFullscreenState);
  document.removeEventListener("MSFullscreenChange", syncFullscreenState);
});

const exchangeLabel = (name?: string | null) => {
  if (name === "hyperliquid") return "Hyperliquid";
  if (name === "binance") return "Binance";
  if (name === "okx") return "OKX";
  return name || "Exchange";
};

</script>
