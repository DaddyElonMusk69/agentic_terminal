<template>
  <div class="relative h-full w-full overflow-hidden rounded-md border border-border bg-panel">
    <div ref="chartEl" class="absolute inset-0"></div>
    <div
      v-if="!hasData"
      class="absolute inset-0 flex items-center justify-center text-xs text-muted"
    >
      No equity data
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { createChart, type IChartApi } from "lightweight-charts";

type EquityPoint = { time: string | number; value: number };

const props = defineProps<{ data: EquityPoint[]; height?: number }>();

const chartEl = ref<HTMLDivElement | null>(null);
let chart: IChartApi | null = null;
let resizeObserver: ResizeObserver | null = null;

const hasData = computed(() => props.data.length > 0);

const normalizeRgbParts = (value: string) =>
  value
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .join(", ");

const normalizeCssColor = (value: string) => {
  const trimmed = value.trim();
  if (!trimmed) return "";
  if (trimmed.startsWith("#") || trimmed.startsWith("hsl")) return trimmed;
  if (trimmed.startsWith("rgb(") || trimmed.startsWith("rgba(")) {
    const prefix = trimmed.startsWith("rgba(") ? "rgba" : "rgb";
    const inner = trimmed.slice(trimmed.indexOf("(") + 1, trimmed.lastIndexOf(")"));
    if (inner.includes(",")) return trimmed;
    return `${prefix}(${normalizeRgbParts(inner)})`;
  }
  if (trimmed.includes(",")) return `rgb(${trimmed})`;
  return `rgb(${normalizeRgbParts(trimmed)})`;
};

const getCssColor = (variable: string, fallback: string) => {
  if (typeof window === "undefined") return fallback;
  const value = getComputedStyle(document.documentElement)
    .getPropertyValue(variable)
    .trim();
  if (!value) return fallback;
  const normalized = normalizeCssColor(value);
  return normalized || fallback;
};

const destroyChart = () => {
  if (resizeObserver) {
    resizeObserver.disconnect();
    resizeObserver = null;
  }
  if (chart) {
    chart.remove();
    chart = null;
  }
};

const buildChart = () => {
  if (!chartEl.value || props.data.length === 0) return;

  destroyChart();

  const textColor = getCssColor("--color-muted", "#94a3b8");
  const gridColor = getCssColor("--color-border", "#334155");
  const fontFamily =
    getComputedStyle(document.documentElement)
      .getPropertyValue("--font-mono")
      .trim() || "'IBM Plex Mono', monospace";

  chart = createChart(chartEl.value, {
    width: chartEl.value.clientWidth,
    height: props.height ?? 240,
    layout: {
      background: { color: "transparent" },
      textColor,
      fontFamily,
    },
    grid: {
      vertLines: { visible: false },
      horzLines: { color: gridColor },
    },
    rightPriceScale: {
      borderVisible: false,
    },
    timeScale: {
      timeVisible: true,
      secondsVisible: false,
      borderVisible: false,
    },
    handleScroll: false,
    handleScale: false,
  });

  const areaSeries = chart.addAreaSeries({
    lineColor: "#22c55e",
    topColor: "rgba(34, 197, 94, 0.35)",
    bottomColor: "rgba(34, 197, 94, 0.05)",
    lineWidth: 2,
  });
  areaSeries.setData(props.data);
  chart.timeScale().fitContent();

  resizeObserver = new ResizeObserver((entries) => {
    if (!chart || entries.length === 0) return;
    const { width, height } = entries[0].contentRect;
    chart.applyOptions({ width, height: height || (props.height ?? 240) });
  });
  resizeObserver.observe(chartEl.value);
};

onMounted(() => {
  buildChart();
});

watch(
  () => props.data,
  () => {
    buildChart();
  },
);

onBeforeUnmount(() => {
  destroyChart();
});
</script>
