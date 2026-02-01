import { defineStore } from "pinia";
import { createObservabilitySocket } from "@/services/socketObservability";

const socketClient = createObservabilitySocket();
let socketExchangeId = "";

const MAX_EVENTS = 400;
const OBSERVABILITY_TOPICS = ["automation.*", "scanner.*", "trade.*", "portfolio.*"];

type RealtimeEnvelope<T = unknown> = {
  v?: number;
  type?: string;
  topic?: string;
  payload?: T;
  ts?: string;
  request_id?: string;
  trace_id?: string;
};

type ObservabilityEvent = {
  id: string;
  timestamp: number;
  time: string;
  topic: string;
  status: "ok" | "warn" | "err";
  ticker?: string | null;
  intervals: string[];
  intervalLabel: string;
  trace?: string | null;
  requestId?: string | null;
  payload?: Record<string, unknown> | null;
};

type QueueMetric = {
  key: string;
  name: string;
  depth: number;
  in_flight: number;
  dlq: number;
  age_oldest_ms: number | null;
  throughput_per_min: number;
  p95_latency_ms: number | null;
};

type QueueMetricsEnvelope = {
  data?: {
    queues?: QueueMetric[];
  };
  error?: { message?: string };
};

let queuePollTimer: number | null = null;

const resolveStatus = (topic: string, payload: Record<string, unknown>) => {
  const lowered = topic.toLowerCase();
  if (lowered.includes("failed") || lowered.includes("error") || lowered.includes("blocked")) {
    return "err" as const;
  }
  if (lowered.includes("rejected") || lowered.includes("waiting") || lowered.includes("dropped")) {
    return "warn" as const;
  }
  if (payload.type === "error" || payload.error) {
    return "err" as const;
  }
  return "ok" as const;
};

const extractTicker = (payload: Record<string, unknown>) => {
  if (typeof payload.ticker === "string") return payload.ticker;
  if (typeof payload.symbol === "string") return payload.symbol;
  if (Array.isArray(payload.tickers) && typeof payload.tickers[0] === "string") return payload.tickers[0];
  const idea = payload.execution_idea as Record<string, unknown> | undefined;
  if (idea && typeof idea.symbol === "string") return idea.symbol;
  return null;
};

const extractIntervals = (payload: Record<string, unknown>): string[] => {
  if (typeof payload.interval === "string") return [payload.interval];
  if (Array.isArray(payload.intervals)) {
    return payload.intervals.filter((item): item is string => typeof item === "string");
  }
  if (Array.isArray(payload.active_intervals)) {
    return payload.active_intervals.filter((item): item is string => typeof item === "string");
  }
  return [];
};

const formatTime = (timestamp: number) => {
  const date = new Date(timestamp);
  return date.toLocaleTimeString(undefined, { hour12: false });
};

export const useObservabilityStore = defineStore("observability", {
  state: () => ({
    isConnected: false,
    isPaused: false,
    events: [] as ObservabilityEvent[],
    queueMetrics: [] as QueueMetric[],
    lastQueueFetch: null as string | null,
  }),
  actions: {
    connectSocket(exchangeId?: string) {
      if (socketExchangeId !== (exchangeId || "")) {
        this.disconnectSocket();
      }

      const socket = socketClient.connect(exchangeId);
      socketExchangeId = exchangeId || "";

      socket.off("connect");
      socket.off("disconnect");
      socket.off("event");

      socket.on("connect", () => {
        this.isConnected = true;
        socket.emit("subscribe", { topics: OBSERVABILITY_TOPICS });
      });

      socket.on("disconnect", () => {
        this.isConnected = false;
      });

      socket.on("event", (envelope: RealtimeEnvelope) => {
        if (!envelope || envelope.type !== "event" || !envelope.topic) return;
        if (this.isPaused) return;
        const payload =
          envelope.payload && typeof envelope.payload === "object"
            ? (envelope.payload as Record<string, unknown>)
            : {};
        const ticker = extractTicker(payload);
        const intervals = extractIntervals(payload);
        const intervalLabel = intervals.length > 0 ? intervals.join(", ") : "";
        const ts = envelope.ts ? Date.parse(envelope.ts) : Date.now();
        const event: ObservabilityEvent = {
          id: `${ts}-${Math.random().toString(36).slice(2, 8)}`,
          timestamp: Number.isNaN(ts) ? Date.now() : ts,
          time: formatTime(Number.isNaN(ts) ? Date.now() : ts),
          topic: envelope.topic,
          status: resolveStatus(envelope.topic, payload),
          ticker,
          intervals,
          intervalLabel,
          trace: envelope.trace_id || null,
          requestId: envelope.request_id || null,
          payload,
        };
        this.events.unshift(event);
        if (this.events.length > MAX_EVENTS) {
          this.events = this.events.slice(0, MAX_EVENTS);
        }
      });
    },
    disconnectSocket() {
      socketClient.disconnect();
      socketExchangeId = "";
      this.isConnected = false;
    },
    togglePause() {
      this.isPaused = !this.isPaused;
    },
    async fetchQueueMetrics() {
      try {
        const response = await fetch("/api/v1/observability/queues");
        const data = (await response.json()) as QueueMetricsEnvelope;
        if (data.data?.queues) {
          this.queueMetrics = data.data.queues;
          this.lastQueueFetch = new Date().toISOString();
        }
      } catch {
        // ignore
      }
    },
    startPolling(intervalMs = 5000) {
      if (queuePollTimer) return;
      this.fetchQueueMetrics();
      queuePollTimer = window.setInterval(() => {
        this.fetchQueueMetrics();
      }, intervalMs);
    },
    stopPolling() {
      if (queuePollTimer) {
        clearInterval(queuePollTimer);
        queuePollTimer = null;
      }
    },
    clearEvents() {
      this.events = [];
    },
  },
});

export type { ObservabilityEvent, QueueMetric };
