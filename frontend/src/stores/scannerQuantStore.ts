import { defineStore } from "pinia";
import type { QuantLog, QuantSignal } from "@/types/quant";
import { createQuantSocket } from "@/services/socketQuant";

type ApiErrorDetail = {
  message?: string;
};

type ApiEnvelope<T> = {
  data?: T;
  error?: ApiErrorDetail;
};

type RealtimeEnvelope<T = unknown> = {
  v?: number;
  type?: string;
  topic?: string;
  payload?: T;
  ts?: string;
  request_id?: string;
  trace_id?: string;
};

const socketClient = createQuantSocket();
let socketExchangeId = "";

const MAX_LOG_ENTRIES = 200;
const QUANT_LOG_TOPIC = "scanner.quant.log";
const QUANT_SIGNAL_TOPIC = "scanner.quant.signal";
const QUANT_COMPLETE_TOPIC = "scanner.quant.completed";
const QUANT_TOPICS = ["scanner.quant.*"];

const parseResponse = async <T>(response: Response): Promise<ApiEnvelope<T>> => {
  try {
    const data = (await response.json()) as ApiEnvelope<T>;
    if (data && typeof data === "object") {
      return data;
    }
  } catch {
    // ignore parse errors
  }
  return {};
};

export const useScannerQuantStore = defineStore("scannerQuant", {
  state: () => ({
    isConnected: false,
    isRunning: false,
    logs: [] as QuantLog[],
    results: [] as QuantSignal[],
    opportunities: {} as Record<string, QuantSignal>,
    assets: [] as string[],
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
        socket.emit("subscribe", { topics: QUANT_TOPICS });
      });

      socket.on("disconnect", () => {
        this.isConnected = false;
        this.isRunning = false;
      });

      socket.on("event", (envelope: RealtimeEnvelope) => {
        if (!envelope || envelope.type !== "event") return;
        if (envelope.topic === QUANT_LOG_TOPIC && envelope.payload) {
          this.appendLog(envelope.payload as QuantLog);
          return;
        }
        if (envelope.topic === QUANT_SIGNAL_TOPIC && envelope.payload) {
          const signal = envelope.payload as QuantSignal;
          this.addResult(signal);
          this.updateOpportunity(signal);
          return;
        }
        if (envelope.topic === QUANT_COMPLETE_TOPIC) {
          this.isRunning = false;
        }
      });
    },
    disconnectSocket() {
      socketClient.disconnect();
      socketExchangeId = "";
      this.isConnected = false;
    },
    appendLog(entry: QuantLog) {
      this.logs.unshift(entry);
      if (this.logs.length > MAX_LOG_ENTRIES) {
        this.logs.pop();
      }
    },
    clearLogs() {
      this.logs = [];
    },
    addResult(result: QuantSignal) {
      this.results.unshift(result);
      if (this.results.length > MAX_LOG_ENTRIES) {
        this.results.pop();
      }
    },
    setResults(results: QuantSignal[]) {
      this.results = [...results];
      this.opportunities = {};
      results.forEach((result) => this.updateOpportunity(result));
    },
    updateOpportunity(signal: QuantSignal) {
      if (!signal || !signal.symbol) return;
      const interval = signal.interval || "15m";
      const key = `${signal.symbol}@${interval}`;
      this.opportunities[key] = signal;
    },
    clearOpportunities() {
      this.opportunities = {};
    },
    async runScan() {
      if (this.isRunning) return;
      this.isRunning = true;
      this.clearLogs();
      this.results = [];
      this.opportunities = {};

      try {
        const res = await fetch("/api/v1/scanner/quant/run", { method: "POST" });
        const data = await parseResponse<{ results: QuantSignal[] }>(res);
        if (!res.ok) {
          const message = data.error?.message || "Quant scan failed.";
          this.appendLog({ message, type: "error" });
          return;
        }
        this.setResults(data.data?.results || []);
      } catch (error) {
        const message = error instanceof Error ? error.message : "Quant scan failed.";
        this.appendLog({ message, type: "error" });
      } finally {
        this.isRunning = false;
      }
    },
    async loadAssets() {
      const res = await fetch("/api/v1/market/monitored-assets");
      if (!res.ok) return;
      const data = await res.json();
      if (Array.isArray(data?.data)) {
        this.assets = data.data;
      }
    },
  },
});
