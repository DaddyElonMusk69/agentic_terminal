<template>
  <div class="flex h-full min-h-0 flex-1 flex-col gap-4 overflow-hidden">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="font-display text-xl">Bus + Queue Monitor</h1>
        <p class="text-xs text-muted">
          Live observability view for message bus flow, queue health, and request traces.
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <select
          v-model="filters.ticker"
          class="rounded-md border border-border bg-panel px-3 py-2 text-xs text-text"
        >
          <option value="all">All tickers</option>
          <option value="BTC">BTC</option>
          <option value="ETH">ETH</option>
          <option value="SOL">SOL</option>
        </select>
        <select
          v-model="filters.interval"
          class="rounded-md border border-border bg-panel px-3 py-2 text-xs text-text"
        >
          <option value="all">All intervals</option>
          <option value="15m">15m</option>
          <option value="1h">1h</option>
          <option value="2h">2h</option>
          <option value="4h">4h</option>
        </select>
        <select
          v-model="filters.topic"
          class="rounded-md border border-border bg-panel px-3 py-2 text-xs text-text"
        >
          <option value="all">All topics</option>
          <option value="scanner">scanner.*</option>
          <option value="chart">chart.*</option>
          <option value="prompt">prompt.*</option>
          <option value="llm">llm.*</option>
        </select>
        <select
          v-model="filters.status"
          class="rounded-md border border-border bg-panel px-3 py-2 text-xs text-text"
        >
          <option value="all">All status</option>
          <option value="ok">OK</option>
          <option value="warn">Warn</option>
          <option value="err">Error</option>
        </select>
        <select
          v-model="filters.range"
          class="rounded-md border border-border bg-panel px-3 py-2 text-xs text-text"
        >
          <option value="15m">Last 15m</option>
          <option value="1h">Last 1h</option>
          <option value="6h">Last 6h</option>
        </select>
        <button
          class="rounded-md border border-border bg-panel px-3 py-2 text-xs text-muted transition hover:text-text"
          type="button"
          @click="store.togglePause()"
        >
          {{ store.isPaused ? "Resume Stream" : "Pause Stream" }}
        </button>
        <button
          class="rounded-md border border-border bg-panel px-3 py-2 text-xs text-muted transition hover:text-text disabled:opacity-60"
          type="button"
          :disabled="isPurgingLlmQueue"
          @click="handleLlmQueuePurge"
        >
          {{ isPurgingLlmQueue ? "Purging..." : "Purge LLM Queue" }}
        </button>
        <button
          class="rounded-md border border-border bg-panel px-3 py-2 text-xs text-muted transition hover:text-text disabled:opacity-60"
          type="button"
          :disabled="isPurgingOutbox"
          @click="handleOutboxPurge"
        >
          {{ isPurgingOutbox ? "Purging..." : "Purge Outbox" }}
        </button>
        <span v-if="llmQueuePurgeMessage" class="text-[11px] text-muted">
          {{ llmQueuePurgeMessage }}
        </span>
        <span v-if="outboxPurgeMessage" class="text-[11px] text-muted">
          {{ outboxPurgeMessage }}
        </span>
      </div>
    </div>

    <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
      <BaseCard
        v-for="stat in kpiCards"
        :key="stat.label"
        class="flex flex-col gap-2"
      >
        <div class="text-[11px] uppercase tracking-wide text-muted">{{ stat.label }}</div>
        <div class="flex items-end justify-between">
          <div class="font-display text-2xl text-text">{{ stat.value }}</div>
          <span class="text-[11px]" :class="stat.deltaClass">{{ stat.delta }}</span>
        </div>
        <div class="text-[11px] text-muted">{{ stat.detail }}</div>
      </BaseCard>
    </div>

    <div
      class="grid min-h-0 flex-1 gap-3 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,1.5fr)_minmax(0,0.9fr)]"
    >
      <BaseCard class="flex min-h-0 flex-col gap-3">
        <div class="flex items-center justify-between">
          <div>
            <div class="text-xs uppercase tracking-wide text-muted">Queue Heatmap</div>
            <div class="text-[11px] text-muted">Depth, age, inflight, DLQ</div>
          </div>
          <BaseBadge>Live</BaseBadge>
        </div>
        <div class="grid grid-cols-[1fr_auto_auto_auto_auto] gap-2 text-[11px] text-muted">
          <span class="uppercase tracking-wide">Queue</span>
          <span class="uppercase tracking-wide">Depth</span>
          <span class="uppercase tracking-wide">Age</span>
          <span class="uppercase tracking-wide">In-flight</span>
          <span class="uppercase tracking-wide">DLQ</span>
        </div>
        <div class="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto pr-1">
          <div
            v-for="queue in queueRows"
            :key="queue.key"
            class="grid grid-cols-[1fr_auto_auto_auto_auto] items-center gap-2 rounded-md border border-border/60 bg-panel/40 px-3 py-2 text-xs"
          >
            <div class="flex items-center gap-3">
              <div class="flex h-6 w-6 items-center justify-center rounded-md border border-border/60 text-[10px]">
                {{ queue.code }}
              </div>
              <div>
                <div class="font-display text-sm text-text">{{ queue.name }}</div>
                <div class="text-[11px] text-muted">{{ queue.throughput }}</div>
              </div>
            </div>
            <div class="flex flex-col items-end gap-1">
              <span class="font-mono text-text">{{ queue.depth }}</span>
              <div class="h-1.5 w-16 overflow-hidden rounded-full bg-panel/70">
                <div
                  class="h-full rounded-full"
                  :class="queue.depthClass"
                  :style="{ width: depthWidth(queue.depth) }"
                ></div>
              </div>
            </div>
            <span class="font-mono text-text">{{ queue.age }}</span>
            <span class="font-mono text-text">{{ queue.inFlight }}</span>
            <span class="font-mono" :class="queue.dlqClass">{{ queue.dlq }}</span>
          </div>
        </div>
      </BaseCard>

      <BaseCard class="flex min-h-0 flex-col gap-3 overflow-hidden">
        <div class="flex items-center justify-between">
          <div>
            <div class="text-xs uppercase tracking-wide text-muted">Pipeline Flow Map</div>
            <div class="text-[11px] text-muted">Stage rates, p95 latency, error ratio</div>
          </div>
          <BaseBadge>Trace-linked</BaseBadge>
        </div>
        <div class="min-h-0 flex-1 overflow-y-auto pr-1">
          <div class="grid gap-3">
            <div
              v-for="node in pipelineNodes"
              :key="node.name"
              class="flex flex-col gap-2 rounded-md border border-border/60 bg-panel/40 px-3 py-2"
            >
              <div class="flex items-center justify-between text-xs">
                <span class="font-display text-sm text-text">{{ node.name }}</span>
                <span class="text-[11px] text-muted">{{ node.rate }}</span>
              </div>
              <div class="grid grid-cols-3 gap-2 text-[11px] text-muted">
                <div class="rounded-md border border-border/50 bg-panel/60 px-2 py-1">
                  <div class="uppercase tracking-wide">p95</div>
                  <div class="font-mono text-text">{{ node.p95 }}</div>
                </div>
                <div class="rounded-md border border-border/50 bg-panel/60 px-2 py-1">
                  <div class="uppercase tracking-wide">Errors</div>
                  <div class="font-mono" :class="node.errorClass">{{ node.errorRate }}</div>
                </div>
                <div class="rounded-md border border-border/50 bg-panel/60 px-2 py-1">
                  <div class="uppercase tracking-wide">Backlog</div>
                  <div class="font-mono text-text">{{ node.backlog }}</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </BaseCard>

      <BaseCard class="flex min-h-0 flex-col gap-3 overflow-hidden">
        <div class="flex items-center justify-between">
          <div>
            <div class="text-xs uppercase tracking-wide text-muted">Inspector</div>
            <div class="text-[11px] text-muted">Selected event or trace context</div>
          </div>
          <BaseBadge>Pinned</BaseBadge>
        </div>
        <div class="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto pr-1 text-xs text-muted">
          <div v-if="activeEvent" class="rounded-md border border-border/60 bg-panel/60 p-3">
            <div class="text-[11px] uppercase tracking-wide text-muted">Trace</div>
            <div class="mt-1 break-all font-mono text-text">
              {{ activeEvent.trace || activeEvent.requestId || "--" }}
            </div>
            <div class="mt-2 text-[11px] text-muted">{{ activeEvent.topic }}</div>
          </div>
          <div v-if="activeEvent" class="rounded-md border border-border/60 bg-panel/60 p-3">
            <div class="text-[11px] uppercase tracking-wide text-muted">Payload meta</div>
            <div class="mt-2 grid gap-2">
              <div class="flex items-center justify-between">
                <span>Ticker</span>
                <span class="font-mono text-text">{{ activeEvent.ticker || "--" }}</span>
              </div>
              <div class="flex items-center justify-between">
                <span>Interval</span>
                <span class="font-mono text-text">{{ activeEvent.intervalLabel || "--" }}</span>
              </div>
              <div class="flex items-center justify-between">
                <span>Size</span>
                <span class="font-mono text-text">{{ activeEventSize }}</span>
              </div>
              <div class="flex items-center justify-between">
                <span>Status</span>
                <span class="font-mono" :class="statusClass(activeEvent.status)">
                  {{ statusLabel(activeEvent.status) }}
                </span>
              </div>
            </div>
          </div>
          <div v-else class="rounded-md border border-border/60 bg-panel/60 p-3 text-center text-xs text-muted">
            No events selected yet.
          </div>
          <button
            class="rounded-md border border-border bg-panel px-3 py-2 text-xs text-muted transition hover:text-text"
            type="button"
          >
            Open full trace
          </button>
        </div>
      </BaseCard>
    </div>

    <div
      class="grid h-[320px] min-h-0 gap-3 overflow-hidden xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]"
    >
      <BaseCard class="flex h-full min-h-0 flex-col gap-3 overflow-hidden">
        <div class="flex items-center justify-between">
          <div>
            <div class="text-xs uppercase tracking-wide text-muted">Event Stream</div>
            <div class="text-[11px] text-muted">Latest bus activity</div>
          </div>
          <BaseBadge>Realtime</BaseBadge>
        </div>
        <div class="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto pr-1">
          <div
            v-for="event in filteredEvents"
            :key="event.id"
            class="flex items-center gap-3 rounded-md border border-border/60 bg-panel/40 px-3 py-2 text-xs"
            @click="selectedEvent = event"
          >
            <span class="h-1.5 w-1.5 rounded-full" :class="statusDotClass(event.status)"></span>
            <span class="font-mono text-text">{{ event.time }}</span>
            <span class="text-text">{{ event.topic }}</span>
            <span class="text-muted">{{ eventMeta(event) }}</span>
            <span class="ml-auto font-mono text-muted">{{ event.trace || event.requestId }}</span>
          </div>
        </div>
      </BaseCard>

      <BaseCard class="flex h-full min-h-0 flex-col gap-3 overflow-hidden">
        <div class="flex items-center justify-between">
          <div>
            <div class="text-xs uppercase tracking-wide text-muted">Trace Waterfall</div>
            <div class="text-[11px] text-muted">Span durations for selected request</div>
          </div>
          <BaseBadge>Request</BaseBadge>
        </div>
        <div class="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto pr-1">
          <div class="rounded-md border border-border/60 bg-panel/60 p-3 text-xs text-muted">
            <div class="text-[11px] uppercase tracking-wide text-muted">Trace ID</div>
            <div class="mt-1 font-mono text-text">{{ activeEvent?.trace || activeEvent?.requestId || "--" }}</div>
          </div>
          <div class="grid gap-2">
            <div
              v-for="span in traceSpans"
              :key="span.name"
              class="flex items-center gap-2 rounded-md border border-border/60 bg-panel/40 px-3 py-2 text-xs"
            >
              <span class="rounded-full px-2 py-0.5 text-[10px]" :class="span.badgeClass">
                {{ span.name }}
              </span>
              <div class="h-2 flex-1 overflow-hidden rounded-full bg-panel/70">
                <div
                  class="h-full rounded-full"
                  :class="span.barClass"
                  :style="{ width: span.width }"
                ></div>
              </div>
              <span class="font-mono text-text">{{ span.duration }}</span>
            </div>
          </div>
        </div>
      </BaseCard>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import BaseBadge from "@/components/BaseBadge.vue";
import BaseCard from "@/components/BaseCard.vue";
import { useExchangeStore } from "@/stores/exchangeStore";
import { useObservabilityStore, type ObservabilityEvent } from "@/stores/observabilityStore";

const store = useObservabilityStore();
const exchangeStore = useExchangeStore();

const filters = ref({
  ticker: "all",
  interval: "all",
  topic: "all",
  status: "all",
  range: "15m",
});

const selectedEvent = ref<ObservabilityEvent | null>(null);
const isPurgingOutbox = ref(false);
const outboxPurgeMessage = ref<string | null>(null);
const isPurgingLlmQueue = ref(false);
const llmQueuePurgeMessage = ref<string | null>(null);

const rangeToMs = (range: string) => {
  if (range === "1h") return 60 * 60 * 1000;
  if (range === "6h") return 6 * 60 * 60 * 1000;
  return 15 * 60 * 1000;
};

const formatRate = (count: number, windowMs: number) => {
  if (windowMs <= 0) return "0/s";
  const rate = count / (windowMs / 1000);
  return `${rate.toFixed(1)}/s`;
};

const formatLatency = (ms?: number | null) => {
  if (!ms && ms !== 0) return "--";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
};

const formatAge = (ms?: number | null) => {
  if (!ms && ms !== 0) return "--";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (ms < 60_000) return `${Math.round(ms / 1000)}s`;
  return `${(ms / 60000).toFixed(1)}m`;
};

const statusLabel = (status: ObservabilityEvent["status"]) => {
  if (status === "err") return "Error";
  if (status === "warn") return "Warn";
  return "OK";
};

const statusClass = (status: ObservabilityEvent["status"]) => {
  if (status === "err") return "text-negative";
  if (status === "warn") return "text-warning";
  return "text-positive";
};

const statusDotClass = (status: ObservabilityEvent["status"]) => {
  if (status === "err") return "bg-negative";
  if (status === "warn") return "bg-warning";
  return "bg-positive";
};

const matchesTopicFilter = (topic: string, filterValue: string) => {
  if (filterValue === "all") return true;
  if (filterValue === "scanner") return topic.startsWith("scanner.");
  if (filterValue === "prompt") return topic.startsWith("automation.prompt");
  if (filterValue === "llm") return topic.startsWith("automation.llm");
  if (filterValue === "chart") return topic.startsWith("chart.");
  return topic.includes(filterValue);
};

const filteredEvents = computed(() => {
  const now = Date.now();
  const rangeMs = rangeToMs(filters.value.range);
  return store.events.filter((event) => {
    if (rangeMs && now - event.timestamp > rangeMs) return false;
    if (filters.value.status !== "all" && event.status !== filters.value.status) return false;
    if (filters.value.ticker !== "all" && event.ticker !== filters.value.ticker) return false;
    if (filters.value.interval !== "all" && !event.intervals.includes(filters.value.interval)) {
      return false;
    }
    if (!matchesTopicFilter(event.topic, filters.value.topic)) return false;
    return true;
  });
});

const activeEvent = computed(() => selectedEvent.value ?? filteredEvents.value[0] ?? null);

const activeEventSize = computed(() => {
  const payload = activeEvent.value?.payload;
  if (!payload) return "--";
  try {
    return `${JSON.stringify(payload).length} bytes`;
  } catch {
    return "--";
  }
});

const queueRows = computed(() =>
  store.queueMetrics.map((metric) => {
    const depthClass = metric.depth > 40 ? "bg-negative" : metric.depth > 15 ? "bg-warning" : "bg-positive";
    const dlqClass = metric.dlq > 0 ? "text-negative" : "text-muted";
    return {
      key: metric.key,
      name: metric.name,
      code: metric.key.slice(0, 2).toUpperCase(),
      depth: metric.depth,
      age: formatAge(metric.age_oldest_ms),
      inFlight: metric.in_flight,
      dlq: metric.dlq,
      throughput: `${metric.throughput_per_min}/min`,
      depthClass,
      dlqClass,
    };
  }),
);

const stageDefinitions = [
  { key: "scanner", label: "Scanner", matches: (topic: string) => topic.startsWith("scanner.") },
  { key: "prompt", label: "Prompt", matches: (topic: string) => topic.startsWith("automation.prompt") },
  { key: "llm", label: "LLM", matches: (topic: string) => topic.startsWith("automation.llm") },
  { key: "guard", label: "Guard", matches: (topic: string) => topic.startsWith("automation.guard") },
  { key: "order", label: "Order", matches: (topic: string) => topic.startsWith("automation.order") || topic.startsWith("trade.") },
];

const stageStyles: Record<string, { badge: string; bar: string }> = {
  scanner: { badge: "bg-accent/20 text-accent", bar: "bg-accent" },
  prompt: { badge: "bg-warning/20 text-warning", bar: "bg-warning" },
  llm: { badge: "bg-negative/20 text-negative", bar: "bg-negative" },
  guard: { badge: "bg-text/10 text-text", bar: "bg-text/60" },
  order: { badge: "bg-positive/20 text-positive", bar: "bg-positive" },
};

const pipelineNodes = computed(() => {
  const now = Date.now();
  const windowMs = 60 * 1000;
  const windowEvents = filteredEvents.value.filter((event) => now - event.timestamp <= windowMs);
  const queueByKey = new Map(store.queueMetrics.map((metric) => [metric.key, metric]));

  return stageDefinitions.map((stage) => {
    const stageEvents = windowEvents.filter((event) => stage.matches(event.topic));
    const errorEvents = stageEvents.filter((event) => event.status === "err");
    const errorRate = stageEvents.length > 0 ? (errorEvents.length / stageEvents.length) * 100 : 0;
    const queueMetric = queueByKey.get(stage.key);
    const p95Ms = queueMetric?.p95_latency_ms ?? null;
    const backlog = queueMetric ? `${queueMetric.depth}` : "--";
    const errorClass = errorRate > 2 ? "text-negative" : errorRate > 0 ? "text-warning" : "text-positive";

    return {
      key: stage.key,
      name: stage.label,
      rate: formatRate(stageEvents.length, windowMs),
      p95: formatLatency(p95Ms),
      p95Ms,
      errorRate: `${errorRate.toFixed(1)}%`,
      backlog,
      errorClass,
    };
  });
});

const traceSpans = computed(() => {
  const latencies = pipelineNodes.value.map((node) => node.p95Ms || 0);
  const maxLatency = Math.max(1, ...latencies);

  return pipelineNodes.value.map((node) => {
    const width = node.p95Ms ? `${Math.max(8, (node.p95Ms / maxLatency) * 100)}%` : "8%";
    const style = stageStyles[node.key] || stageStyles.guard;
    return {
      name: node.key,
      duration: node.p95,
      width,
      badgeClass: style.badge,
      barClass: style.bar,
    };
  });
});

const kpiCards = computed(() => {
  const now = Date.now();
  const windowMs = 60 * 1000;
  const windowEvents = filteredEvents.value.filter((event) => now - event.timestamp <= windowMs);
  const errorEvents = windowEvents.filter((event) => event.status === "err");
  const completionEvents = windowEvents.filter((event) =>
    event.topic.includes("completed") ||
    event.topic.includes("executed") ||
    event.topic.includes("passed"),
  );
  const backlog = store.queueMetrics.reduce((total, metric) => total + metric.depth, 0);
  const maxLatency = Math.max(
    0,
    ...store.queueMetrics.map((metric) => metric.p95_latency_ms || 0),
  );

  const errorRate = windowEvents.length > 0 ? (errorEvents.length / windowEvents.length) * 100 : 0;

  return [
    {
      label: "Publish/s",
      value: formatRate(windowEvents.length, windowMs),
      delta: "last 60s",
      deltaClass: "text-muted",
      detail: `${windowEvents.length} events`,
    },
    {
      label: "Consume/s",
      value: formatRate(completionEvents.length, windowMs),
      delta: "last 60s",
      deltaClass: "text-muted",
      detail: `${completionEvents.length} completions`,
    },
    {
      label: "Backlog",
      value: `${backlog}`,
      delta: "live",
      deltaClass: "text-muted",
      detail: "queued items",
    },
    {
      label: "P95 Latency",
      value: formatLatency(maxLatency),
      delta: "queue p95",
      deltaClass: "text-muted",
      detail: "last 60m",
    },
    {
      label: "Error Rate",
      value: `${errorRate.toFixed(2)}%`,
      delta: "last 60s",
      deltaClass: "text-muted",
      detail: `${errorEvents.length} errors`,
    },
  ];
});

const eventMeta = (event: ObservabilityEvent) => {
  const parts = [
    event.ticker ? `ticker=${event.ticker}` : null,
    event.intervalLabel ? `intervals=${event.intervalLabel}` : null,
  ].filter(Boolean);
  return parts.length > 0 ? parts.join(" · ") : "--";
};

const depthWidth = (depth: number) => `${Math.min(100, 10 + depth * 1.6)}%`;

const handleLlmQueuePurge = async () => {
  if (isPurgingLlmQueue.value) return;
  isPurgingLlmQueue.value = true;
  llmQueuePurgeMessage.value = null;
  try {
    const response = await fetch("/api/v1/automation/llm-queue/purge", { method: "POST" });
    if (!response.ok) {
      throw new Error("Purge failed");
    }
    const payload = await response.json();
    const result = payload?.data;
    if (result) {
      llmQueuePurgeMessage.value = `Purged ${result.purged} queued LLM prompts`;
    } else {
      llmQueuePurgeMessage.value = "LLM queue purge completed";
    }
  } catch (error) {
    llmQueuePurgeMessage.value = "LLM queue purge failed";
  } finally {
    isPurgingLlmQueue.value = false;
  }
};

const handleOutboxPurge = async () => {
  if (isPurgingOutbox.value) return;
  isPurgingOutbox.value = true;
  outboxPurgeMessage.value = null;
  try {
    const response = await fetch("/api/v1/automation/outbox/purge", { method: "POST" });
    if (!response.ok) {
      throw new Error("Purge failed");
    }
    const payload = await response.json();
    const result = payload?.data;
    if (result) {
      outboxPurgeMessage.value = `Purged ${result.purged} rows (older than ${result.hours}h)`;
    } else {
      outboxPurgeMessage.value = "Outbox purge completed";
    }
  } catch (error) {
    outboxPurgeMessage.value = "Outbox purge failed";
  } finally {
    isPurgingOutbox.value = false;
  }
};

onMounted(() => {
  store.connectSocket(exchangeStore.activeExchangeId || undefined);
  store.startPolling();
});

watch(
  () => exchangeStore.activeExchangeId,
  (exchangeId) => {
    store.connectSocket(exchangeId || undefined);
  },
);

onBeforeUnmount(() => {
  store.stopPolling();
  store.disconnectSocket();
});
</script>
