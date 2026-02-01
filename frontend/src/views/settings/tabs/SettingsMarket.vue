<template>
  <div class="flex min-h-0 flex-1 flex-col gap-4">
    <BaseCard>
      <template v-if="showLoading">
        <div class="animate-pulse space-y-3">
          <div class="flex items-center justify-between">
            <div class="space-y-2">
              <div class="h-3 w-40 rounded bg-panel/60"></div>
              <div class="h-2 w-64 rounded bg-panel/40"></div>
            </div>
            <div class="h-5 w-16 rounded-full bg-panel/50"></div>
          </div>
          <div class="flex flex-wrap gap-2">
            <div class="h-8 w-20 rounded bg-panel/60"></div>
            <div class="h-8 w-16 rounded bg-panel/40"></div>
          </div>
        </div>
      </template>
      <template v-else>
        <div class="flex items-center justify-between">
          <div>
            <div class="text-xs uppercase tracking-wide text-muted">Market Data Source</div>
            <p class="mt-1 text-xs text-muted">
              Spot uses cleaner price action. Futures keeps OI and funding metrics.
            </p>
          </div>
          <BaseBadge>{{ marketSourceLabel }}</BaseBadge>
        </div>
        <div class="mt-3 flex flex-wrap gap-2">
          <button
            class="rounded-md border border-border px-3 py-2 text-xs font-medium"
            :class="
              marketSource === 'futures'
                ? 'bg-accent text-base'
                : 'bg-panel text-muted hover:text-text'
            "
            type="button"
            :disabled="marketSource === 'futures' || isSavingSource"
            @click="updateMarketSource('futures')"
          >
            Futures
          </button>
          <button
            class="rounded-md border border-border px-3 py-2 text-xs font-medium"
            :class="
              marketSource === 'spot'
                ? 'bg-accent text-base'
                : 'bg-panel text-muted hover:text-text'
            "
            type="button"
            :disabled="marketSource === 'spot' || isSavingSource"
            @click="updateMarketSource('spot')"
          >
            Spot
          </button>
        </div>
      </template>
    </BaseCard>

    <BaseCard>
      <template v-if="showLoading">
        <div class="animate-pulse space-y-3">
          <div class="flex items-start justify-between gap-3">
            <div class="space-y-2">
              <div class="h-3 w-32 rounded bg-panel/60"></div>
              <div class="h-2 w-48 rounded bg-panel/40"></div>
            </div>
            <div class="h-5 w-20 rounded-full bg-panel/50"></div>
          </div>
          <div class="h-14 rounded-md border border-border bg-panel/40"></div>
          <div class="flex flex-wrap gap-2">
            <div class="h-6 w-16 rounded-full bg-panel/50"></div>
            <div class="h-6 w-20 rounded-full bg-panel/40"></div>
            <div class="h-6 w-14 rounded-full bg-panel/50"></div>
          </div>
        </div>
      </template>
      <template v-else>
        <div class="flex items-start justify-between gap-3">
          <div>
            <div class="text-xs uppercase tracking-wide text-muted">Monitored Assets</div>
            <p class="mt-1 text-xs text-muted">Assets used in scanners and automation.</p>
          </div>
          <div class="flex items-center gap-2">
            <button
              class="rounded-md border border-border bg-panel px-3 py-1.5 text-[11px] text-muted hover:text-text disabled:opacity-60"
              type="button"
              :disabled="isRefreshingAssets || isUpdatingDynamic"
              @click="handleHardRefresh"
            >
              Hard Refresh
            </button>
            <BaseBadge v-if="dynamicEnabled">Dynamic Mode</BaseBadge>
          </div>
        </div>

        <div class="mt-3 rounded-md border border-border bg-panel/50 p-3">
          <div class="flex items-center justify-between gap-4">
            <div>
              <div class="text-sm font-medium text-text">Dynamic Asset List</div>
              <div class="flex items-center gap-2">
                <span
                  v-if="isUpdatingDynamic || isRefreshingAssets"
                  class="h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent text-muted"
                ></span>
                <p class="text-[11px] text-muted">
                  {{ dynamicStatusLabel }}
                </p>
              </div>
              <p v-if="dynamicEnabled && !isBinanceActive" class="text-[11px] text-warning">
                Dynamic mode requires an active Binance account.
              </p>
              <p v-if="dynamicEnabled && !hasApiKey" class="text-[11px] text-warning">
                API key not configured in Dynamic Assets.
              </p>
            </div>
            <label class="relative inline-flex cursor-pointer items-center">
              <input
                class="peer sr-only"
                type="checkbox"
                :disabled="!isBinanceActive || isUpdatingDynamic"
                :checked="dynamicEnabled"
                @change="handleDynamicToggle"
              />
              <span
                class="h-5 w-10 rounded-full border border-border bg-panel transition peer-checked:bg-accent"
              ></span>
              <span
                class="absolute left-0.5 top-0.5 h-4 w-4 rounded-full bg-text transition peer-checked:translate-x-5"
              ></span>
            </label>
          </div>
        </div>

        <div class="mt-4 space-y-3">
          <div v-if="!dynamicEnabled" class="flex flex-wrap gap-2">
            <input
              v-model="assetInput"
              class="w-40 flex-1 rounded-md border border-border bg-panel px-3 py-2 text-xs"
              type="text"
              placeholder="Add asset (e.g., BTC)"
              maxlength="10"
              @keydown.enter.prevent="addAsset"
            />
            <button
              class="rounded-md border border-border bg-accent px-3 py-2 text-xs font-medium text-base"
              type="button"
              :disabled="isAddingAsset || !assetInput.trim()"
              @click="addAsset"
            >
              Add Asset
            </button>
          </div>

          <div class="flex flex-wrap gap-2">
            <span
              v-for="asset in assets"
              :key="asset"
              class="flex items-center gap-2 rounded-full border border-border bg-panel px-3 py-1 text-xs"
            >
              <span class="font-mono text-text">{{ asset }}</span>
              <button
                v-if="!dynamicEnabled"
                class="text-muted hover:text-negative"
                type="button"
                @click="removeAsset(asset)"
              >
                x
              </button>
              <span v-else class="text-[10px] uppercase text-muted">Auto</span>
            </span>
            <span v-if="assets.length === 0" class="text-xs text-muted">No assets configured.</span>
          </div>
        </div>
      </template>
    </BaseCard>

    <BaseCard>
      <template v-if="showLoading">
        <div class="animate-pulse space-y-3">
          <div class="space-y-2">
            <div class="h-3 w-32 rounded bg-panel/60"></div>
            <div class="h-2 w-48 rounded bg-panel/40"></div>
          </div>
          <div class="flex flex-wrap gap-2">
            <div class="h-8 w-24 rounded bg-panel/50"></div>
            <div class="h-8 w-16 rounded bg-panel/40"></div>
          </div>
          <div class="flex flex-wrap gap-2">
            <div class="h-6 w-12 rounded-full bg-panel/50"></div>
            <div class="h-6 w-16 rounded-full bg-panel/40"></div>
            <div class="h-6 w-20 rounded-full bg-panel/50"></div>
          </div>
        </div>
      </template>
      <template v-else>
        <div class="text-xs uppercase tracking-wide text-muted">Monitored Intervals</div>
        <p class="mt-1 text-xs text-muted">
          Available across charts, scans, and backtesting.
        </p>

        <div class="mt-3 flex flex-wrap gap-2">
          <input
            v-model="intervalInput"
            class="w-40 flex-1 rounded-md border border-border bg-panel px-3 py-2 text-xs"
            type="text"
            placeholder="Add interval (e.g., 15m, 4h)"
            maxlength="10"
            @keydown.enter.prevent="addInterval"
          />
          <button
            class="rounded-md border border-border bg-accent px-3 py-2 text-xs font-medium text-base"
            type="button"
            :disabled="isAddingInterval || !intervalInput.trim()"
            @click="addInterval"
          >
            Add Interval
          </button>
        </div>

        <div class="mt-3 flex flex-wrap gap-2">
          <span
            v-for="interval in intervals"
            :key="interval"
            class="flex items-center gap-2 rounded-full border border-border bg-panel px-3 py-1 text-xs"
          >
            <span class="font-mono text-text">{{ interval }}</span>
            <button
              class="text-muted hover:text-negative"
              type="button"
              @click="removeInterval(interval)"
            >
              x
            </button>
          </span>
          <span v-if="intervals.length === 0" class="text-xs text-muted">
            No intervals configured.
          </span>
        </div>
      </template>
    </BaseCard>

    <div v-if="statusMessage" class="text-xs" :class="statusToneClass">
      {{ statusMessage }}
    </div>

    <div v-if="error" class="text-xs text-negative">
      {{ error }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import BaseBadge from "@/components/BaseBadge.vue";
import BaseCard from "@/components/BaseCard.vue";
import type { DynamicSources, MarketCacheData } from "@/services/settingsCache";
import { readMarketCache, subscribeMarketCache, writeMarketCache } from "@/services/settingsCache";

const defaultDynamicSources: DynamicSources = {
  ai500: { enabled: false, limit: 10 },
  ai300: { enabled: false, limit: 20, level: "" },
  oi_top: { enabled: false, limit: 20, duration: "1h" },
  oi_low: { enabled: false, limit: 20, duration: "1h" },
};

const buildDynamicSources = (value?: Partial<DynamicSources> | null) => ({
  ai500: { ...defaultDynamicSources.ai500, ...(value?.ai500 || {}) },
  ai300: { ...defaultDynamicSources.ai300, ...(value?.ai300 || {}) },
  oi_top: { ...defaultDynamicSources.oi_top, ...(value?.oi_top || {}) },
  oi_low: { ...defaultDynamicSources.oi_low, ...(value?.oi_low || {}) },
});

const assets = ref<string[]>([]);
const intervals = ref<string[]>([]);
const marketSource = ref<"spot" | "futures">("futures");
const assetInput = ref("");
const intervalInput = ref("");
const error = ref("");
const statusMessage = ref("");
const statusTone = ref<"info" | "success" | "error">("info");
const isSavingSource = ref(false);
const isAddingAsset = ref(false);
const isAddingInterval = ref(false);
const isUpdatingDynamic = ref(false);
const isRefreshingAssets = ref(false);
const isLoading = ref(false);
const hasLoaded = ref(false);
const dynamicEnabled = ref(false);
const hasApiKey = ref(false);
const isBinanceActive = ref(false);
const dynamicSources = ref<DynamicSources>(buildDynamicSources());
const dynamicRefreshMinutes = ref(10);
let unsubscribeMarketCache: (() => void) | null = null;

const statusToneClass = computed(() => {
  if (statusTone.value === "success") return "text-positive";
  if (statusTone.value === "error") return "text-negative";
  return "text-muted";
});

const marketSourceLabel = computed(() =>
  marketSource.value === "spot" ? "Spot" : "Futures",
);

const showLoading = computed(() => isLoading.value && !hasLoaded.value);

const dynamicSourcesEnabled = computed(() =>
  Object.values(dynamicSources.value).some((source) => source.enabled),
);

const dynamicActive = computed(
  () =>
    dynamicEnabled.value &&
    isBinanceActive.value &&
    hasApiKey.value &&
    dynamicSourcesEnabled.value,
);

const dynamicStatusLabel = computed(() => {
  if (showLoading.value) return "Loading market settings...";
  if (isUpdatingDynamic.value || isRefreshingAssets.value) return "Refreshing dynamic list...";
  if (dynamicEnabled.value && dynamicActive.value) return "Enabled and active";
  if (dynamicEnabled.value && !dynamicActive.value) return "Enabled but inactive";
  return "Disabled";
});

const setStatus = (message: string, tone: "info" | "success" | "error" = "info") => {
  statusMessage.value = message;
  statusTone.value = tone;
  window.setTimeout(() => {
    if (statusMessage.value === message) statusMessage.value = "";
  }, 4000);
};

const refreshAssets = async (force = false) => {
  try {
    const url = force
      ? "/api/v1/market/monitored-assets?force_refresh=true"
      : "/api/v1/market/monitored-assets";
    const response = await fetch(url);
    const data = await response.json();
    if (Array.isArray(data?.data)) {
      assets.value = data.data;
      persistMarketCache();
      return true;
    }
  } catch {
    // Ignore refresh errors; the UI will retry on next load.
  }
  return false;
};

const applyMarketCache = (data: MarketCacheData) => {
  assets.value = Array.isArray(data.assets) ? [...data.assets] : [];
  intervals.value = Array.isArray(data.intervals) ? [...data.intervals] : [];
  marketSource.value = data.marketSource === "spot" ? "spot" : "futures";
  dynamicEnabled.value = Boolean(data.dynamicEnabled);
  hasApiKey.value = Boolean(data.hasApiKey);
  isBinanceActive.value = Boolean(data.isBinanceActive);
  dynamicSources.value = buildDynamicSources(data.dynamicSources);
  dynamicRefreshMinutes.value = Number.isFinite(data.dynamicRefreshMinutes)
    ? data.dynamicRefreshMinutes
    : 10;
};

const persistMarketCache = () => {
  writeMarketCache({
    assets: [...assets.value],
    intervals: [...intervals.value],
    marketSource: marketSource.value,
    dynamicEnabled: dynamicEnabled.value,
    hasApiKey: hasApiKey.value,
    isBinanceActive: isBinanceActive.value,
    dynamicSources: buildDynamicSources(dynamicSources.value),
    dynamicRefreshMinutes: dynamicRefreshMinutes.value,
  });
};

const loadMarketSettings = async (force = false) => {
  error.value = "";
  const cached = !force ? readMarketCache() : null;
  if (cached) {
    applyMarketCache(cached);
    hasLoaded.value = true;
  }
  const shouldFetchCore = !cached || force;
  if (shouldFetchCore) {
    isLoading.value = true;
  }
  try {
    const assetsUrl = force
      ? "/api/v1/market/monitored-assets?force_refresh=true"
      : "/api/v1/market/monitored-assets";
    const requests: Promise<Response>[] = [
      fetch("/api/v1/market/dynamic-assets"),
      fetch(assetsUrl),
    ];
    if (shouldFetchCore) {
      requests.push(
        fetch("/api/v1/market/monitored-intervals"),
        fetch("/api/config/scanner/market-data-source"),
      );
    }

    const [dynamicRes, assetsRes, intervalsRes, sourceRes] = await Promise.all(requests);
    const dynamicData = await dynamicRes.json();
    const assetsData = await assetsRes.json();

    assets.value = Array.isArray(assetsData?.data) ? assetsData.data : [];

    if (shouldFetchCore && intervalsRes && sourceRes) {
      const intervalsData = await intervalsRes.json();
      const sourceData = await sourceRes.json();

      intervals.value = Array.isArray(intervalsData?.data) ? intervalsData.data : [];

      if (sourceData.success && (sourceData.source === "spot" || sourceData.source === "futures")) {
        marketSource.value = sourceData.source;
      }
    }

    if (dynamicData?.data) {
      const dynamicConfig = dynamicData.data;
      dynamicEnabled.value = Boolean(dynamicConfig.enabled);
      hasApiKey.value = Boolean(dynamicConfig.api_key_present);
      dynamicSources.value = buildDynamicSources(dynamicConfig.sources);
      dynamicRefreshMinutes.value = Math.max(
        1,
        Math.round((dynamicConfig.refresh_interval_seconds || 600) / 60),
      );
      isBinanceActive.value = Boolean(dynamicConfig.is_binance_active);
    }
    persistMarketCache();
    hasLoaded.value = true;
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Failed to load market settings.";
  } finally {
    if (shouldFetchCore) {
      isLoading.value = false;
    }
  }
};

const updateMarketSource = async (source: "spot" | "futures") => {
  if (marketSource.value === source) return;
  isSavingSource.value = true;
  try {
    const response = await fetch("/api/config/scanner/market-data-source", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source }),
    });
    const data = await response.json();
    if (!data.success) {
      throw new Error(data.error || "Failed to update market data source.");
    }
    marketSource.value = source;
    setStatus(`Market data source set to ${source}.`, "success");
    persistMarketCache();
  } catch (err) {
    setStatus(err instanceof Error ? err.message : "Failed to update data source.", "error");
  } finally {
    isSavingSource.value = false;
  }
};

const handleDynamicToggle = async (event: Event) => {
  const target = event.target as HTMLInputElement;
  const nextEnabled = target.checked;
  if (!isBinanceActive.value) return;
  isUpdatingDynamic.value = true;
  try {
    const response = await fetch("/api/v1/market/dynamic-assets", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        enabled: nextEnabled,
        refresh_interval_seconds: Math.round(dynamicRefreshMinutes.value * 60),
      }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data?.error?.message || "Failed to update dynamic assets.");
    }
    const config = data?.data;
    if (config) {
      dynamicEnabled.value = Boolean(config.enabled);
      hasApiKey.value = Boolean(config.api_key_present);
      dynamicSources.value = buildDynamicSources(config.sources);
      dynamicRefreshMinutes.value = Math.max(
        1,
        Math.round((config.refresh_interval_seconds || 600) / 60),
      );
      isBinanceActive.value = Boolean(config.is_binance_active);
      persistMarketCache();
    }
    await refreshAssets();
    setStatus(
      dynamicEnabled.value ? "Dynamic mode enabled." : "Dynamic mode disabled.",
      "success",
    );
  } catch (err) {
    target.checked = dynamicEnabled.value;
    setStatus(err instanceof Error ? err.message : "Failed to update dynamic mode.", "error");
  } finally {
    isUpdatingDynamic.value = false;
  }
};

const handleHardRefresh = async () => {
  if (isRefreshingAssets.value) return;
  isRefreshingAssets.value = true;
  const ok = await refreshAssets(true);
  if (ok) {
    setStatus("Monitored assets refreshed.", "success");
  } else {
    setStatus("Failed to refresh monitored assets.", "error");
  }
  isRefreshingAssets.value = false;
};

const addAsset = async () => {
  const ticker = assetInput.value.trim().toUpperCase();
  if (!ticker) return;
  isAddingAsset.value = true;
  try {
    const response = await fetch("/api/v1/market/monitored-assets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol: ticker }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data?.error?.message || "Failed to add asset.");
    }
    assets.value = Array.isArray(data?.data)
      ? data.data
      : [ticker, ...assets.value.filter((item) => item !== ticker)];
    assetInput.value = "";
    setStatus(`${ticker} added.`, "success");
    persistMarketCache();
  } catch (err) {
    setStatus(err instanceof Error ? err.message : "Failed to add asset.", "error");
  } finally {
    isAddingAsset.value = false;
  }
};

const removeAsset = async (ticker: string) => {
  if (!ticker) return;
  try {
    const response = await fetch(
      `/api/v1/market/monitored-assets/${encodeURIComponent(ticker)}`,
      {
        method: "DELETE",
      },
    );
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data?.error?.message || "Failed to remove asset.");
    }
    assets.value = Array.isArray(data?.data)
      ? data.data
      : assets.value.filter((item) => item !== ticker);
    setStatus(`${ticker} removed.`, "success");
    persistMarketCache();
  } catch (err) {
    setStatus(err instanceof Error ? err.message : "Failed to remove asset.", "error");
  }
};

const addInterval = async () => {
  const interval = intervalInput.value.trim().toLowerCase();
  if (!interval) return;
  isAddingInterval.value = true;
  try {
    const response = await fetch("/api/v1/market/monitored-intervals", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ interval }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data?.error?.message || "Failed to add interval.");
    }
    intervals.value = Array.isArray(data?.data) ? data.data : [...intervals.value, interval];
    intervalInput.value = "";
    setStatus(`${interval} added.`, "success");
    persistMarketCache();
  } catch (err) {
    setStatus(err instanceof Error ? err.message : "Failed to add interval.", "error");
  } finally {
    isAddingInterval.value = false;
  }
};

const removeInterval = async (interval: string) => {
  try {
    const response = await fetch(
      `/api/v1/market/monitored-intervals/${encodeURIComponent(interval)}`,
      {
        method: "DELETE",
      },
    );
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data?.error?.message || "Failed to remove interval.");
    }
    intervals.value = Array.isArray(data?.data)
      ? data.data
      : intervals.value.filter((item) => item !== interval);
    setStatus(`${interval} removed.`, "success");
    persistMarketCache();
  } catch (err) {
    setStatus(err instanceof Error ? err.message : "Failed to remove interval.", "error");
  }
};

const initialCache = readMarketCache();
if (initialCache) {
  applyMarketCache(initialCache);
}

onMounted(() => {
  unsubscribeMarketCache = subscribeMarketCache((data) => {
    applyMarketCache(data);
  });
  loadMarketSettings();
});

onUnmounted(() => {
  if (unsubscribeMarketCache) {
    unsubscribeMarketCache();
    unsubscribeMarketCache = null;
  }
});
</script>
