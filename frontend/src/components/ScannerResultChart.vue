<template>
  <div
    class="relative w-full overflow-hidden rounded-md border border-border bg-panel"
    :style="containerStyle"
  >
    <div ref="chartEl" class="absolute inset-0"></div>
    <div
      v-if="!hasData"
      class="absolute inset-0 flex items-center justify-center text-xs text-muted"
    >
      Chart unavailable
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { LineStyle, createChart, type IChartApi } from "lightweight-charts";
import type { ScannerChartData } from "@/types/scanner";

const props = defineProps<{ data?: ScannerChartData; height?: number; fill?: boolean }>();

const chartEl = ref<HTMLDivElement | null>(null);
let chart: IChartApi | null = null;
let resizeObserver: ResizeObserver | null = null;

const hasData = computed(() => Boolean(props.data?.candles?.length));
const baseHeight = computed(() => props.height ?? 192);
const containerStyle = computed(() =>
  props.fill ? { height: "100%" } : { height: `${baseHeight.value}px` },
);

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
  if (!chartEl.value || !props.data?.candles?.length) return;

  destroyChart();

  const background = getCssColor("--color-panel", "#1f2937");
  const textColor = getCssColor("--color-muted", "#94a3b8");
  const gridColor = getCssColor("--color-border", "#334155");
  const fontFamily =
    getComputedStyle(document.documentElement)
      .getPropertyValue("--font-mono")
      .trim() || "'IBM Plex Mono', monospace";

  const resolvedHeight = props.fill && chartEl.value?.clientHeight
    ? chartEl.value.clientHeight
    : baseHeight.value;

  chart = createChart(chartEl.value, {
    width: chartEl.value.clientWidth,
    height: resolvedHeight,
    layout: {
      background: { color: background },
      textColor,
      fontFamily,
    },
    grid: {
      vertLines: { color: gridColor },
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

  const candleSeries = chart.addCandlestickSeries({
    upColor: "#22c55e",
    downColor: "#f87171",
    wickUpColor: "#22c55e",
    wickDownColor: "#f87171",
    borderUpColor: "#22c55e",
    borderDownColor: "#f87171",
  });
  candleSeries.setData(props.data.candles);

  const emaColors = ["#38bdf8", "#f59e0b", "#a855f7", "#14b8a6"];
  let emaIndex = 0;
  if (props.data.emas) {
    Object.entries(props.data.emas).forEach(([length, series]) => {
      const emaSeries = chart?.addLineSeries({
        color: emaColors[emaIndex % emaColors.length],
        lineWidth: 2,
        lastValueVisible: false,
        priceLineVisible: false,
      });
      emaSeries?.setData(series);
      emaIndex += 1;
    });
  }

  if (props.data.bollinger) {
    if (props.data.bollinger.upper?.length) {
      const upper = chart.addLineSeries({
        color: "#fb7185",
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
      });
      upper.setData(props.data.bollinger.upper);
    }

    if (props.data.bollinger.middle?.length) {
      const mid = chart.addLineSeries({
        color: "#94a3b8",
        lineWidth: 1,
      });
      mid.setData(props.data.bollinger.middle);
    }

    if (props.data.bollinger.lower?.length) {
      const lower = chart.addLineSeries({
        color: "#4ade80",
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
      });
      lower.setData(props.data.bollinger.lower);
    }
  }

  chart.timeScale().fitContent();

  resizeObserver = new ResizeObserver((entries) => {
    if (!chart || entries.length === 0) return;
    const { width, height } = entries[0].contentRect;
    const nextHeight = height || baseHeight.value;
    chart.applyOptions({ width, height: nextHeight });
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
