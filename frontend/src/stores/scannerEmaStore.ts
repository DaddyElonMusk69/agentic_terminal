import { defineStore } from "pinia";
import type {
  EmaScannerConfig,
  EmaScannerLine,
  EmaScannerRunPayload,
  ScannerLog,
  ScannerResult,
} from "@/types/scanner";
import type { VegasStateUpdate, VegasTickerState } from "@/types/vegas";
import { createEmaSocket } from "@/services/socketEma";

type ApiErrorDetail = {
  message?: string;
  code?: string;
  details?: Record<string, unknown>;
};

type ApiEnvelope<T> = {
  data?: T;
  error?: ApiErrorDetail;
  meta?: { request_id?: string };
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

const socketClient = createEmaSocket();
let socketExchangeId = "";
let activeScanAbortController: AbortController | null = null;

const MAX_LOG_ENTRIES = 200;
const EMA_LOG_TOPIC = "scanner.ema.log";
const EMA_STATE_TOPIC = "scanner.ema.state";
const EMA_RESULTS_TOPIC = "scanner.ema.results";
const EMA_LOG_TOPICS = ["scanner.ema.*"];

const parseResponse = async <T>(response: Response): Promise<ApiEnvelope<T>> => {
  try {
    const data = (await response.json()) as ApiEnvelope<T>;
    if (data && typeof data === "object") {
      return data;
    }
  } catch {
    // Ignore parsing errors.
  }
  return {};
};

const resolveError = (data: ApiEnvelope<unknown>, fallback: string) => {
  if (data.error?.message) return data.error.message;
  return fallback;
};

export const useScannerEmaStore = defineStore("scannerEma", {
  state: () => ({
    isConnected: false,
    isScanning: false,
    showLogOverlay: false,
    isLoadingHistory: false,
    isImporting: false,
    lastUpdated: null as string | null,
    selectedDate: null as string | null,
    logs: [] as ScannerLog[],
    results: [] as ScannerResult[],
    calendarData: {} as Record<string, number>,
    emaLines: [] as EmaScannerLine[],
    tolerancePct: 0.2,
    availableIntervals: [] as string[],
    scanIntervals: [] as string[],
    vegasStates: [] as VegasTickerState[],
    vegasSummary: {
      tickers: 0,
      totalResonance: 0,
    },
    vegasLastUpdated: null as string | null,
    cycleNumber: 0,
    activeCycleNumber: null as number | null,
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
        socket.emit("subscribe", { topics: EMA_LOG_TOPICS });
      });

      socket.on("disconnect", () => {
        this.isConnected = false;
        this.isScanning = false;
      });

      socket.on("event", (envelope: RealtimeEnvelope) => {
        if (!envelope || envelope.type !== "event") return;
        if (envelope.topic === EMA_LOG_TOPIC && envelope.payload) {
          this.appendLog(envelope.payload as ScannerLog);
        }
        if (envelope.topic === EMA_STATE_TOPIC && envelope.payload) {
          this.applyVegasState(envelope.payload as VegasStateUpdate);
        }
        if (envelope.topic === EMA_RESULTS_TOPIC && envelope.payload) {
          const payload = envelope.payload as Record<string, unknown>;
          const results = Array.isArray(payload.results)
            ? (payload.results as ScannerResult[])
            : null;
          if (results) {
            this.setResults(results);
          }
        }
      });
    },
    disconnectSocket() {
      socketClient.disconnect();
      socketExchangeId = "";
      this.isConnected = false;
      this.vegasStates = [];
      this.vegasSummary = { tickers: 0, totalResonance: 0 };
      this.vegasLastUpdated = null;
    },
    async runScan(): Promise<void> {
      if (this.isScanning) return;
      this.isScanning = true;
      this.showLogOverlay = true;
      this.logs = [];
      this.results = [];
      this.lastUpdated = null;
      this.selectedDate = null;

      const controller = new AbortController();
      activeScanAbortController = controller;

      try {
        const response = await fetch("/api/v1/scanner/ema/run", {
          method: "POST",
          signal: controller.signal,
        });
        const data = await parseResponse<EmaScannerRunPayload>(response);
        if (!response.ok) {
          const message = resolveError(data, "EMA scan failed.");
          this.appendLog({ event: "scan_error", data: { error: message } });
          return;
        }
        this.setResults(data.data?.results || []);
        await this.loadCalendar();
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          this.appendLog({ event: "scan_cancelled", data: { reason: "client_abort" } });
          return;
        }
        const message = error instanceof Error ? error.message : "EMA scan failed.";
        this.appendLog({ event: "scan_error", data: { error: message } });
      } finally {
        if (activeScanAbortController === controller) {
          activeScanAbortController = null;
        }
        this.isScanning = false;
      }
    },
    async stopScan(): Promise<boolean> {
      if (activeScanAbortController) {
        activeScanAbortController.abort();
        activeScanAbortController = null;
      }

      try {
        const response = await fetch("/api/v1/scanner/ema/stop", { method: "POST" });
        const data = await parseResponse<{ running: boolean; stop_requested: boolean }>(response);
        if (!response.ok) {
          const message = resolveError(data, "Failed to stop EMA scan.");
          this.appendLog({ event: "scan_error", data: { error: message } });
          return false;
        }
        if (data.data?.stop_requested) {
          this.appendLog({ event: "scan_cancel_requested", data: { running: data.data.running } });
        }
        return Boolean(data.data?.stop_requested);
      } catch (error) {
        const message = error instanceof Error ? error.message : "Failed to stop EMA scan.";
        this.appendLog({ event: "scan_error", data: { error: message } });
        return false;
      } finally {
        this.isScanning = false;
      }
    },
    async loadCalendar() {
      const res = await fetch("/api/v1/scanner/ema/calendar");
      if (!res.ok) return;
      const data = await parseResponse<Record<string, number>>(res);
      if (!data.data) return;
      this.calendarData = data.data;
    },
    async loadHistory(date: string) {
      if (!date) return;
      this.isLoadingHistory = true;
      try {
        const res = await fetch(`/api/v1/scanner/ema/history?date=${encodeURIComponent(date)}`);
        const data = await parseResponse<EmaScannerRunPayload>(res);
        if (!res.ok) return;
        this.results = data.data?.results || [];
        this.selectedDate = date;
        this.lastUpdated = new Date().toISOString();
      } finally {
        this.isLoadingHistory = false;
      }
    },
    async deleteResult(resultId: number | string) {
      const idValue = typeof resultId === "number" ? resultId : Number(resultId);
      if (!Number.isFinite(idValue)) return false;
      const res = await fetch(`/api/v1/scanner/ema/result/${idValue}`, { method: "DELETE" });
      const data = await parseResponse<{ success: boolean }>(res);
      if (!res.ok || !data.data?.success) return false;
      const idKey = String(idValue);
      this.results = this.results.filter((item) => String(item.id ?? "") !== idKey);
      await this.loadCalendar();
      return true;
    },
    async importScanResults(file: File) {
      if (!file) return 0;
      this.isImporting = true;
      try {
        const formData = new FormData();
        formData.append("file", file);
        const res = await fetch("/api/v1/scanner/ema/import", {
          method: "POST",
          body: formData,
        });
        const data = await parseResponse<{ count: number }>(res);
        if (!res.ok) return 0;
        await this.loadCalendar();
        return data.data?.count ?? 0;
      } finally {
        this.isImporting = false;
      }
    },
    async exportScanResults() {
      const res = await fetch("/api/v1/scanner/ema/export");
      if (!res.ok) return;
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      const dateStamp = new Date().toISOString().split("T")[0];
      link.download = `scan_results_${dateStamp}.csv`;
      link.click();
      window.URL.revokeObjectURL(url);
    },
    appendLog(entry: ScannerLog) {
      const payload: ScannerLog = {
        ...entry,
        data: { ...(entry.data || {}) },
      };
      const data = payload.data as Record<string, unknown>;
      const entryRecord = entry as Record<string, unknown>;
      const toNumber = (value: unknown) => {
        if (typeof value === "number") return value;
        const parsed = Number(value);
        return Number.isNaN(parsed) ? null : parsed;
      };
      const incomingCycle =
        toNumber(
          data.cycle ??
            data.cycle_number ??
            data.cycleNumber ??
            data.cycleIndex ??
            entryRecord.cycle_number,
        );

      const isScanStart = payload.event === "scan_init" || payload.event === "cycle_start";
      const isScanEnd =
        payload.event === "scan_finished" ||
        payload.event === "scan_empty_config" ||
        payload.event === "scan_cancelled";
      const hasSymbol = typeof data.symbol === "string" && data.symbol.trim().length > 0;
      const isTerminalError = payload.event === "scan_error" && !hasSymbol;

      if (typeof incomingCycle === "number") {
        this.cycleNumber = incomingCycle;
        if (data.cycle === undefined && data.cycle_number === undefined) {
          data.cycle_number = incomingCycle;
        }
      } else if (isScanStart) {
        this.cycleNumber = Math.max(0, this.cycleNumber) + 1;
      }

      if (this.cycleNumber > 0 && data.cycle === undefined && data.cycle_number === undefined) {
        data.cycle = this.cycleNumber;
      }

      if (isScanStart) {
        this.activeCycleNumber =
          typeof incomingCycle === "number" ? incomingCycle : this.cycleNumber;
      }
      if (isScanEnd || isTerminalError) {
        if (this.activeCycleNumber === null) {
          this.activeCycleNumber = null;
        } else if (typeof incomingCycle !== "number" || incomingCycle === this.activeCycleNumber) {
          this.activeCycleNumber = null;
        }
      }

      this.logs.unshift(payload);
      if (this.logs.length > MAX_LOG_ENTRIES) {
        this.logs.pop();
      }
    },
    setCycleNumber(value: number) {
      if (!Number.isFinite(value)) return;
      this.cycleNumber = Math.max(0, Math.floor(value));
    },
    clearLogs() {
      this.logs = [];
    },
    setResults(results: ScannerResult[]) {
      this.results = results;
      this.lastUpdated = new Date().toISOString();
    },
    toggleLogOverlay() {
      this.showLogOverlay = !this.showLogOverlay;
    },
    async loadConfig() {
      const res = await fetch("/api/v1/scanner/ema/config");
      if (!res.ok) return;
      const data = await parseResponse<EmaScannerConfig>(res);
      if (!data.data) return;
      this.emaLines = data.data.ema_lines || [];
      this.tolerancePct = Number(data.data.tolerance_pct ?? this.tolerancePct);
      this.availableIntervals = Array.isArray(data.data.available_intervals)
        ? data.data.available_intervals.filter((item) => typeof item === "string")
        : [];
      this.scanIntervals = Array.isArray(data.data.scan_intervals)
        ? data.data.scan_intervals.filter((item) => typeof item === "string")
        : [];
    },
    async loadVegasState() {
      const res = await fetch("/api/v1/scanner/ema/state");
      if (!res.ok) return;
      const data = await parseResponse<VegasStateUpdate>(res);
      if (!data.data) return;
      this.applyVegasState(data.data);
    },
    async clearVegasState() {
      const res = await fetch("/api/v1/scanner/ema/state/clear", { method: "POST" });
      const data = await parseResponse<VegasStateUpdate>(res);
      if (!res.ok) {
        throw new Error(resolveError(data, `Failed to clear managed states (${res.status}).`));
      }
      this.applyVegasState(data.data || { states: [] });
    },
    async updateTolerance(value: number) {
      this.tolerancePct = value;
      await fetch("/api/v1/scanner/ema/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tolerance_pct: value }),
      });
    },
    async updateScanIntervals(intervals: string[]) {
      const normalized = Array.from(
        new Set(intervals.filter((item): item is string => typeof item === "string" && item.trim())),
      );
      const response = await fetch("/api/v1/scanner/ema/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scan_intervals: normalized }),
      });
      const data = await parseResponse<EmaScannerConfig>(response);
      if (!response.ok) {
        throw new Error(resolveError(data, "Failed to update scanned intervals."));
      }
      if (data.data) {
        this.emaLines = data.data.ema_lines || this.emaLines;
        this.tolerancePct = Number(data.data.tolerance_pct ?? this.tolerancePct);
        this.availableIntervals = Array.isArray(data.data.available_intervals)
          ? data.data.available_intervals.filter((item) => typeof item === "string")
          : this.availableIntervals;
        this.scanIntervals = Array.isArray(data.data.scan_intervals)
          ? data.data.scan_intervals.filter((item) => typeof item === "string")
          : this.scanIntervals;
        return;
      }
      await this.loadConfig();
    },
    async addEmaLine(length: number) {
      if (!length) return;
      const response = await fetch("/api/v1/scanner/ema/lines", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ length }),
      });
      const data = await parseResponse<EmaScannerConfig>(response);
      if (data.data?.ema_lines) {
        this.emaLines = data.data.ema_lines;
        this.tolerancePct = Number(data.data.tolerance_pct ?? this.tolerancePct);
        this.availableIntervals = Array.isArray(data.data.available_intervals)
          ? data.data.available_intervals.filter((item) => typeof item === "string")
          : this.availableIntervals;
        this.scanIntervals = Array.isArray(data.data.scan_intervals)
          ? data.data.scan_intervals.filter((item) => typeof item === "string")
          : this.scanIntervals;
        return;
      }
      await this.loadConfig();
    },
    async removeEmaLine(lineId: number) {
      const response = await fetch(`/api/v1/scanner/ema/lines/${lineId}`, {
        method: "DELETE",
      });
      const data = await parseResponse<EmaScannerConfig>(response);
      if (data.data?.ema_lines) {
        this.emaLines = data.data.ema_lines;
        this.tolerancePct = Number(data.data.tolerance_pct ?? this.tolerancePct);
        this.availableIntervals = Array.isArray(data.data.available_intervals)
          ? data.data.available_intervals.filter((item) => typeof item === "string")
          : this.availableIntervals;
        this.scanIntervals = Array.isArray(data.data.scan_intervals)
          ? data.data.scan_intervals.filter((item) => typeof item === "string")
          : this.scanIntervals;
        return;
      }
      await this.loadConfig();
    },
    applyVegasState(payload: VegasStateUpdate) {
      const states = Array.isArray(payload?.states) ? payload.states : [];
      this.vegasStates = states;
      this.vegasSummary = {
        tickers: states.length,
        totalResonance: states.reduce(
          (total, state) => total + (state.resonance_count || 0),
          0,
        ),
      };
      this.vegasLastUpdated = new Date().toISOString();
    },
    updateVegasTicker(state: VegasTickerState) {
      const next = [...this.vegasStates];
      const index = next.findIndex((item) => item.ticker === state.ticker);
      if (index >= 0) {
        next[index] = state;
      } else {
        next.push(state);
      }
      this.applyVegasState({ states: next });
    },
  },
});
