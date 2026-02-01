<template>
  <div class="flex min-h-0 flex-1 flex-col gap-4">
    <BaseCard>
      <div class="flex items-center gap-2">
        <button
          class="rounded-md border border-border px-3 py-2 text-xs font-medium"
          :class="activeTab === 'depth' ? 'bg-accent text-base' : 'bg-panel text-muted hover:text-text'"
          type="button"
          @click="activeTab = 'depth'"
        >
          Depth Cache
        </button>
        <button
          class="rounded-md border border-border px-3 py-2 text-xs font-medium"
          :class="activeTab === 'market' ? 'bg-accent text-base' : 'bg-panel text-muted hover:text-text'"
          type="button"
          @click="activeTab = 'market'"
        >
          Market Data Cache
        </button>
      </div>
    </BaseCard>

    <div v-if="activeTab === 'depth'" class="space-y-4">
      <BaseCard>
        <div class="flex items-center justify-between">
          <div>
            <div class="text-xs uppercase tracking-wide text-muted">Depth Recording</div>
            <p class="mt-1 text-xs text-muted">Capture order book snapshots for backtesting.</p>
          </div>
          <label class="relative inline-flex cursor-pointer items-center">
            <input
              class="peer sr-only"
              type="checkbox"
              :checked="depthStatus.recording"
              :disabled="isDepthUpdating"
              @change="toggleDepthRecording"
            />
            <span
              class="h-5 w-10 rounded-full border border-border bg-panel transition peer-checked:bg-accent"
            ></span>
            <span
              class="absolute left-0.5 top-0.5 h-4 w-4 rounded-full bg-text transition peer-checked:translate-x-5"
            ></span>
          </label>
        </div>
        <p class="mt-2 text-[11px]" :class="depthStatus.recording ? 'text-positive' : 'text-muted'">
          {{ depthStatus.recording ? "Recording active" : "Recording inactive" }}
        </p>
      </BaseCard>

      <BaseCard>
        <div class="text-xs uppercase tracking-wide text-muted">Retention</div>
        <div class="mt-3 flex flex-wrap items-center gap-3">
          <label class="flex items-center gap-2 text-xs text-muted">
            <input v-model="depthSettings.autoCleanup" type="checkbox" />
            Auto-cleanup
          </label>
          <div class="flex items-center gap-2 text-xs text-muted">
            <span>Keep</span>
            <input
              v-model.number="depthSettings.retentionDays"
              class="w-20 rounded-md border border-border bg-panel px-2 py-1 text-xs text-text"
              type="number"
              min="1"
              max="365"
            />
            <span>days</span>
          </div>
          <button
            class="rounded-md border border-border bg-accent px-3 py-2 text-xs font-medium text-base"
            type="button"
            :disabled="isDepthUpdating"
            @click="saveDepthSettings"
          >
            {{ isDepthUpdating ? "Saving..." : "Save" }}
          </button>
        </div>
      </BaseCard>

      <BaseCard>
        <div class="text-xs uppercase tracking-wide text-muted">Storage</div>
        <div class="mt-3 grid gap-3 sm:grid-cols-2">
          <div class="rounded-md border border-border bg-panel/50 p-3">
            <div class="text-lg font-semibold text-text">{{ depthStatus.totalRecords }}</div>
            <div class="text-[11px] text-muted">Total records</div>
          </div>
          <div class="rounded-md border border-border bg-panel/50 p-3">
            <div class="text-lg font-semibold text-text">{{ formatBytes(depthStatus.storageBytes) }}</div>
            <div class="text-[11px] text-muted">Storage used</div>
          </div>
        </div>
      </BaseCard>

      <BaseCard>
        <div class="text-xs uppercase tracking-wide text-muted">Coverage (Last 30 Days)</div>
        <div class="mt-3 grid grid-cols-10 gap-1">
          <div
            v-for="day in depthCoverage"
            :key="day.date"
            class="h-6 rounded"
            :style="{ backgroundColor: day.color }"
            :title="`${day.date}: ${day.count} records`"
          ></div>
        </div>
      </BaseCard>

      <BaseCard>
        <div class="flex flex-wrap items-center gap-2">
          <button
            class="rounded-md border border-border bg-panel px-3 py-2 text-xs text-muted hover:text-text"
            type="button"
            :disabled="isDepthUpdating"
            @click="runDepthCleanup"
          >
            Run Cleanup
          </button>
          <button
            class="rounded-md border border-border bg-negative/20 px-3 py-2 text-xs text-negative"
            type="button"
            :disabled="isDepthUpdating"
            @click="clearDepthCache"
          >
            Clear All
          </button>
        </div>
      </BaseCard>
    </div>

    <div v-else class="space-y-4">
      <BaseCard>
        <div class="text-xs uppercase tracking-wide text-muted">Market Data Cache</div>
        <p class="mt-1 text-xs text-muted">
          Historical candles cached for backtesting and analytics.
        </p>
      </BaseCard>

      <BaseCard>
        <div class="text-xs uppercase tracking-wide text-muted">Retention</div>
        <div class="mt-3 flex flex-wrap items-center gap-3">
          <label class="flex items-center gap-2 text-xs text-muted">
            <input v-model="marketSettings.autoCleanup" type="checkbox" />
            Auto-cleanup
          </label>
          <div class="flex items-center gap-2 text-xs text-muted">
            <span>Keep</span>
            <input
              v-model.number="marketSettings.retentionDays"
              class="w-20 rounded-md border border-border bg-panel px-2 py-1 text-xs text-text"
              type="number"
              min="7"
              max="365"
            />
            <span>days</span>
          </div>
          <button
            class="rounded-md border border-border bg-accent px-3 py-2 text-xs font-medium text-base"
            type="button"
            :disabled="isMarketUpdating"
            @click="saveMarketSettings"
          >
            {{ isMarketUpdating ? "Saving..." : "Save" }}
          </button>
        </div>
      </BaseCard>

      <BaseCard>
        <div class="text-xs uppercase tracking-wide text-muted">Storage</div>
        <div class="mt-3 grid gap-3 sm:grid-cols-2">
          <div class="rounded-md border border-border bg-panel/50 p-3">
            <div class="text-lg font-semibold text-text">{{ marketStatus.totalRecords }}</div>
            <div class="text-[11px] text-muted">Total records</div>
          </div>
          <div class="rounded-md border border-border bg-panel/50 p-3">
            <div class="text-lg font-semibold text-text">{{ formatBytes(marketStatus.storageBytes) }}</div>
            <div class="text-[11px] text-muted">Storage used</div>
          </div>
          <div class="rounded-md border border-border bg-panel/50 p-3">
            <div class="text-lg font-semibold text-text">{{ marketStatus.symbolCount }}</div>
            <div class="text-[11px] text-muted">Symbols cached</div>
          </div>
          <div class="rounded-md border border-border bg-panel/50 p-3">
            <div class="text-lg font-semibold text-text">{{ marketStatus.takerCoverage }}%</div>
            <div class="text-[11px] text-muted">Taker volume coverage</div>
          </div>
        </div>
      </BaseCard>

      <BaseCard>
        <div class="text-xs uppercase tracking-wide text-muted">Cache Actions</div>
        <div class="mt-3 flex flex-wrap items-center gap-2">
          <button
            class="rounded-md border border-border bg-panel px-3 py-2 text-xs text-muted hover:text-text"
            type="button"
            :disabled="isMarketUpdating"
            @click="runMarketCleanup"
          >
            Run Cleanup
          </button>
          <button
            class="rounded-md border border-border bg-negative/20 px-3 py-2 text-xs text-negative"
            type="button"
            :disabled="isMarketUpdating"
            @click="clearMarketCache"
          >
            Clear All
          </button>
        </div>

        <div class="mt-4 flex flex-wrap items-center gap-2">
          <input
            v-model="marketSymbol"
            class="w-40 rounded-md border border-border bg-panel px-3 py-2 text-xs"
            type="text"
            placeholder="Symbol to clear"
            maxlength="12"
          />
          <button
            class="rounded-md border border-border bg-panel px-3 py-2 text-xs text-muted hover:text-text"
            type="button"
            :disabled="isMarketUpdating || !marketSymbol.trim()"
            @click="clearMarketSymbol"
          >
            Clear Symbol
          </button>
        </div>
      </BaseCard>
    </div>

    <div v-if="statusMessage" class="text-xs" :class="statusToneClass">
      {{ statusMessage }}
    </div>

    <div v-if="error" class="text-xs text-negative">
      {{ error }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import BaseCard from "@/components/BaseCard.vue";

type DepthStatus = {
  recording: boolean;
  autoCleanup: boolean;
  retentionDays: number;
  totalRecords: number;
  storageBytes: number;
  coverage: Record<string, number>;
};

type MarketStatus = {
  totalRecords: number;
  storageBytes: number;
  symbolCount: number;
  takerCoverage: number;
  autoCleanup: boolean;
  retentionDays: number;
};

const activeTab = ref<"depth" | "market">("depth");
const error = ref("");
const statusMessage = ref("");
const statusTone = ref<"info" | "success" | "error">("info");
const isDepthUpdating = ref(false);
const isMarketUpdating = ref(false);
const marketSymbol = ref("");

const depthStatus = reactive<DepthStatus>({
  recording: false,
  autoCleanup: true,
  retentionDays: 90,
  totalRecords: 0,
  storageBytes: 0,
  coverage: {},
});

const depthSettings = reactive({
  autoCleanup: true,
  retentionDays: 90,
});

const marketStatus = reactive<MarketStatus>({
  totalRecords: 0,
  storageBytes: 0,
  symbolCount: 0,
  takerCoverage: 0,
  autoCleanup: true,
  retentionDays: 30,
});

const marketSettings = reactive({
  autoCleanup: true,
  retentionDays: 30,
});

const statusToneClass = computed(() => {
  if (statusTone.value === "success") return "text-positive";
  if (statusTone.value === "error") return "text-negative";
  return "text-muted";
});

const depthCoverage = computed(() => {
  const coverage = depthStatus.coverage || {};
  const days: { date: string; count: number; color: string }[] = [];
  const today = new Date();
  const values = Object.values(coverage);
  const maxValue = values.length ? Math.max(...values) : 0;
  for (let i = 29; i >= 0; i -= 1) {
    const date = new Date(today);
    date.setDate(today.getDate() - i);
    const key = date.toISOString().slice(0, 10);
    const count = coverage[key] || 0;
    const ratio = maxValue ? count / maxValue : 0;
    const opacity = ratio > 0 ? 0.2 + ratio * 0.6 : 0.15;
    const color = ratio > 0 ? `rgba(var(--color-accent) / ${opacity})` : `rgba(var(--color-border) / 0.3)`;
    days.push({ date: key, count, color });
  }
  return days;
});

const setStatus = (message: string, tone: "info" | "success" | "error" = "info") => {
  statusMessage.value = message;
  statusTone.value = tone;
  window.setTimeout(() => {
    if (statusMessage.value === message) statusMessage.value = "";
  }, 4000);
};

const formatBytes = (bytes: number) => {
  if (!Number.isFinite(bytes)) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value.toFixed(1)} ${units[index]}`;
};

const loadDepthStatus = async () => {
  try {
    const response = await fetch("/api/depth-cache/status");
    const data = await response.json();
    if (!data.success) throw new Error(data.error || "Failed to load depth cache.");
    depthStatus.recording = Boolean(data.recording);
    depthStatus.autoCleanup = data.auto_cleanup_enabled !== false;
    depthStatus.retentionDays = data.retention_days || 90;
    depthStatus.totalRecords = data.total_records || 0;
    depthStatus.storageBytes = data.storage_bytes || 0;
    depthStatus.coverage = data.coverage_by_date || {};
    depthSettings.autoCleanup = depthStatus.autoCleanup;
    depthSettings.retentionDays = depthStatus.retentionDays;
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Failed to load depth cache.";
  }
};

const loadMarketStatus = async () => {
  try {
    const response = await fetch("/api/market-data-cache/status");
    const data = await response.json();
    if (!data.success) throw new Error(data.error || "Failed to load market cache.");
    marketStatus.totalRecords = data.total_records || 0;
    marketStatus.storageBytes = data.storage_bytes || 0;
    marketStatus.symbolCount = Array.isArray(data.symbols_cached) ? data.symbols_cached.length : 0;
    marketStatus.takerCoverage = data.has_taker_volume?.percentage || 0;
    marketStatus.autoCleanup = data.auto_cleanup_enabled !== false;
    marketStatus.retentionDays = data.retention_days || 30;
    marketSettings.autoCleanup = marketStatus.autoCleanup;
    marketSettings.retentionDays = marketStatus.retentionDays;
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Failed to load market cache.";
  }
};

const toggleDepthRecording = async (event: Event) => {
  const target = event.target as HTMLInputElement;
  const next = target.checked;
  isDepthUpdating.value = true;
  try {
    const response = await fetch("/api/depth-cache/recording", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: next }),
    });
    const data = await response.json();
    if (!data.success) throw new Error(data.error || "Failed to toggle recording.");
    depthStatus.recording = next;
    setStatus(next ? "Recording enabled." : "Recording disabled.", "success");
  } catch (err) {
    target.checked = depthStatus.recording;
    setStatus(err instanceof Error ? err.message : "Failed to toggle recording.", "error");
  } finally {
    isDepthUpdating.value = false;
  }
};

const saveDepthSettings = async () => {
  isDepthUpdating.value = true;
  try {
    const response = await fetch("/api/depth-cache/cleanup-settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        enabled: depthSettings.autoCleanup,
        retention_days: depthSettings.retentionDays,
      }),
    });
    const data = await response.json();
    if (!data.success) throw new Error(data.error || "Failed to update settings.");
    depthStatus.autoCleanup = depthSettings.autoCleanup;
    depthStatus.retentionDays = depthSettings.retentionDays;
    setStatus("Retention settings updated.", "success");
  } catch (err) {
    setStatus(err instanceof Error ? err.message : "Failed to update settings.", "error");
  } finally {
    isDepthUpdating.value = false;
  }
};

const runDepthCleanup = async () => {
  isDepthUpdating.value = true;
  try {
    const response = await fetch("/api/depth-cache/run-cleanup", { method: "POST" });
    const data = await response.json();
    if (!data.success) throw new Error(data.error || "Cleanup failed.");
    setStatus(`Cleanup removed ${data.records_deleted || 0} records.`, "success");
    await loadDepthStatus();
  } catch (err) {
    setStatus(err instanceof Error ? err.message : "Cleanup failed.", "error");
  } finally {
    isDepthUpdating.value = false;
  }
};

const clearDepthCache = async () => {
  const confirmed = window.confirm("Clear all depth cache data?");
  if (!confirmed) return;
  isDepthUpdating.value = true;
  try {
    const response = await fetch("/api/depth-cache/clear", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirm: true }),
    });
    const data = await response.json();
    if (!data.success) throw new Error(data.error || "Failed to clear cache.");
    setStatus("Depth cache cleared.", "success");
    await loadDepthStatus();
  } catch (err) {
    setStatus(err instanceof Error ? err.message : "Failed to clear cache.", "error");
  } finally {
    isDepthUpdating.value = false;
  }
};

const saveMarketSettings = async () => {
  isMarketUpdating.value = true;
  try {
    const response = await fetch("/api/market-data-cache/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        auto_cleanup_enabled: marketSettings.autoCleanup,
        retention_days: marketSettings.retentionDays,
      }),
    });
    const data = await response.json();
    if (!data.success) throw new Error(data.error || "Failed to update settings.");
    marketStatus.autoCleanup = marketSettings.autoCleanup;
    marketStatus.retentionDays = marketSettings.retentionDays;
    setStatus("Retention settings updated.", "success");
  } catch (err) {
    setStatus(err instanceof Error ? err.message : "Failed to update settings.", "error");
  } finally {
    isMarketUpdating.value = false;
  }
};

const runMarketCleanup = async () => {
  isMarketUpdating.value = true;
  try {
    const response = await fetch("/api/market-data-cache/run-cleanup", { method: "POST" });
    const data = await response.json();
    if (!data.success) throw new Error(data.error || "Cleanup failed.");
    setStatus(`Cleanup removed ${data.records_deleted || 0} records.`, "success");
    await loadMarketStatus();
  } catch (err) {
    setStatus(err instanceof Error ? err.message : "Cleanup failed.", "error");
  } finally {
    isMarketUpdating.value = false;
  }
};

const clearMarketCache = async () => {
  const confirmed = window.confirm("Clear all market data cache?");
  if (!confirmed) return;
  isMarketUpdating.value = true;
  try {
    const response = await fetch("/api/market-data-cache/clear", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirm: true }),
    });
    const data = await response.json();
    if (!data.success) throw new Error(data.error || "Failed to clear cache.");
    setStatus("Market cache cleared.", "success");
    await loadMarketStatus();
  } catch (err) {
    setStatus(err instanceof Error ? err.message : "Failed to clear cache.", "error");
  } finally {
    isMarketUpdating.value = false;
  }
};

const clearMarketSymbol = async () => {
  const symbol = marketSymbol.value.trim().toUpperCase();
  if (!symbol) return;
  isMarketUpdating.value = true;
  try {
    const response = await fetch("/api/market-data-cache/clear", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirm: true, symbol }),
    });
    const data = await response.json();
    if (!data.success) throw new Error(data.error || "Failed to clear symbol.");
    setStatus(`${symbol} cache cleared.`, "success");
    marketSymbol.value = "";
    await loadMarketStatus();
  } catch (err) {
    setStatus(err instanceof Error ? err.message : "Failed to clear symbol.", "error");
  } finally {
    isMarketUpdating.value = false;
  }
};

watch(activeTab, (value) => {
  if (value === "depth") {
    loadDepthStatus();
  } else {
    loadMarketStatus();
  }
});

onMounted(() => {
  loadDepthStatus();
});
</script>
