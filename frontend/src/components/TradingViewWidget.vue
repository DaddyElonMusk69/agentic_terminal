<template>
  <div class="relative h-full w-full overflow-hidden rounded-md border border-border bg-panel">
    <div :id="containerId" ref="containerRef" class="absolute inset-0"></div>
    <div
      v-if="state === 'loading'"
      class="absolute inset-0 flex items-center justify-center text-xs text-muted"
    >
      Loading chart...
    </div>
    <div
      v-else-if="state === 'error'"
      class="absolute inset-0 flex items-center justify-center text-xs text-negative"
    >
      {{ errorMessage || "Chart unavailable" }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";

type WidgetState = "idle" | "loading" | "ready" | "error";

const props = defineProps<{
  symbol?: string | null;
  interval?: string;
  theme?: "light" | "dark";
}>();

const containerRef = ref<HTMLDivElement | null>(null);
const containerId = `tradingview-${Math.random().toString(36).slice(2)}`;
const state = ref<WidgetState>("idle");
const errorMessage = ref("");

declare global {
  interface Window {
    TradingView?: {
      widget: new (options: Record<string, unknown>) => unknown;
    };
  }
}

let tradingViewScriptPromise: Promise<void> | null = null;

const loadTradingViewScript = () => {
  if (typeof window === "undefined") return Promise.resolve();
  if (window.TradingView?.widget) return Promise.resolve();
  if (tradingViewScriptPromise) return tradingViewScriptPromise;

  tradingViewScriptPromise = new Promise((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>(
      'script[src="https://s3.tradingview.com/tv.js"]',
    );
    if (existing) {
      existing.addEventListener("load", () => resolve());
      existing.addEventListener("error", () => reject(new Error("TradingView failed to load")));
      return;
    }

    const script = document.createElement("script");
    script.src = "https://s3.tradingview.com/tv.js";
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("TradingView failed to load"));
    document.head.appendChild(script);
  });

  return tradingViewScriptPromise;
};

const renderWidget = async () => {
  const symbol = (props.symbol || "").trim();
  if (!containerRef.value) return;
  if (!symbol) {
    state.value = "idle";
    errorMessage.value = "";
    containerRef.value.innerHTML = "";
    return;
  }

  state.value = "loading";
  errorMessage.value = "";

  try {
    await loadTradingViewScript();
  } catch (error) {
    state.value = "error";
    errorMessage.value = error instanceof Error ? error.message : "TradingView unavailable";
    return;
  }

  if (!window.TradingView?.widget) {
    state.value = "error";
    errorMessage.value = "TradingView unavailable";
    return;
  }

  containerRef.value.innerHTML = "";

  const theme = props.theme || "dark";
  const interval = props.interval || "15";

  new window.TradingView.widget({
    container_id: containerId,
    symbol,
    interval,
    timezone: "Etc/UTC",
    theme,
    style: "1",
    locale: "en",
    allow_symbol_change: false,
    save_image: false,
    hide_top_toolbar: true,
    hide_legend: true,
    hide_side_toolbar: true,
    withdateranges: false,
    details: false,
    calendar: false,
    studies: [],
    autosize: true,
    support_host: "https://www.tradingview.com",
  });

  state.value = "ready";
};

onMounted(() => {
  void renderWidget();
});

watch(
  () => [props.symbol, props.interval, props.theme],
  () => {
    void renderWidget();
  },
);

onBeforeUnmount(() => {
  if (containerRef.value) {
    containerRef.value.innerHTML = "";
  }
});
</script>
