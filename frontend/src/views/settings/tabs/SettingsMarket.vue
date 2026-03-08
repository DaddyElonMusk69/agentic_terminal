<template>
  <div class="flex min-h-0 flex-1 flex-col gap-4">
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
            <p class="mt-1 text-[11px] text-muted">
              Final global list = Base List (manual or dynamic) + Open Positions − High Volatility removals.
            </p>
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

        <div class="mt-3 rounded-md border border-border bg-panel/40 p-3 text-[11px] text-muted">
          <div class="text-[10px] uppercase tracking-wide text-muted">Global List Breakdown</div>
          <div class="mt-2 space-y-2">
            <div>
              <div class="text-[10px] uppercase tracking-wide text-muted">Base List</div>
              <div class="mt-1 flex flex-wrap gap-1">
                <span
                  v-for="asset in baseAssets"
                  :key="`base-${asset}`"
                  class="rounded-full border border-border bg-panel px-2 py-0.5 text-[10px] text-text"
                >
                  {{ asset }}
                </span>
                <span v-if="baseAssets.length === 0" class="text-[10px] text-muted">None</span>
              </div>
            </div>
            <div>
              <div class="text-[10px] uppercase tracking-wide text-muted">Open Positions</div>
              <div class="mt-1 flex flex-wrap gap-1">
                <span
                  v-for="asset in openPositions"
                  :key="`open-${asset}`"
                  class="rounded-full border border-border bg-panel px-2 py-0.5 text-[10px] text-text"
                >
                  {{ asset }}
                </span>
                <span v-if="openPositions.length === 0" class="text-[10px] text-muted">None</span>
              </div>
            </div>
            <div>
              <div class="text-[10px] uppercase tracking-wide text-muted">
                Removed High Volatility
              </div>
              <div class="mt-1 flex flex-wrap gap-1">
                <span
                  v-for="asset in removedHighVolAssets"
                  :key="`vol-${asset}`"
                  class="rounded-full border border-border bg-panel px-2 py-0.5 text-[10px] text-text"
                >
                  {{ asset }}
                </span>
                <span v-if="removedHighVolAssets.length === 0" class="text-[10px] text-muted"
                  >None</span
                >
              </div>
            </div>
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
              <p
                v-if="dynamicEnabled && apiKeyRequired && !hasApiKey"
                class="text-[11px] text-warning"
              >
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
  netflow_top: { enabled: false, limit: 20, duration: "1h" },
  netflow_low: { enabled: false, limit: 20, duration: "1h" },
  futures_depth: { enabled: false, limit: 60 },
  excluded_assets: { enabled: false, symbols: "" },
};

const buildDynamicSources = (value?: Partial<DynamicSources> | null) => ({
  ai500: { ...defaultDynamicSources.ai500, ...(value?.ai500 || {}) },
  ai300: { ...defaultDynamicSources.ai300, ...(value?.ai300 || {}) },
  oi_top: { ...defaultDynamicSources.oi_top, ...(value?.oi_top || {}) },
  oi_low: { ...defaultDynamicSources.oi_low, ...(value?.oi_low || {}) },
  netflow_top: { ...defaultDynamicSources.netflow_top, ...(value?.netflow_top || {}) },
  netflow_low: { ...defaultDynamicSources.netflow_low, ...(value?.netflow_low || {}) },
  futures_depth: { ...defaultDynamicSources.futures_depth, ...(value?.futures_depth || {}) },
  excluded_assets: { ...defaultDynamicSources.excluded_assets, ...(value?.excluded_assets || {}) },
});

const assets = ref<string[]>([]);
const baseAssets = ref<string[]>([]);
const openPositions = ref<string[]>([]);
const removedHighVolAssets = ref<string[]>([]);
const intervals = ref<string[]>([]);
const assetInput = ref("");
const intervalInput = ref("");
const error = ref("");
const statusMessage = ref("");
const statusTone = ref<"info" | "success" | "error">("info");
const isAddingAsset = ref(false);
const isAddingInterval = ref(false);
const isUpdatingDynamic = ref(false);
const isRefreshingAssets = ref(false);
const isLoading = ref(false);
const hasLoaded = ref(false);
const dynamicEnabled = ref(false);
const hasApiKey = ref(false);
const isBinanceActive = ref(false);
const dynamicOiSource = ref("nofx");
const dynamicSources = ref<DynamicSources>(buildDynamicSources());
const dynamicRefreshMinutes = ref(10);
let unsubscribeMarketCache: (() => void) | null = null;

const statusToneClass = computed(() => {
  if (statusTone.value === "success") return "text-positive";
  if (statusTone.value === "error") return "text-negative";
  return "text-muted";
});

const showLoading = computed(() => isLoading.value && !hasLoaded.value);

const dynamicSourcesEnabled = computed(() =>
  Object.values(dynamicSources.value).some((source) => source.enabled),
);

const apiKeyRequired = computed(() => {
  if (dynamicOiSource.value === "custom") {
    return dynamicSources.value.ai500.enabled || dynamicSources.value.ai300.enabled;
  }
  return true;
});

const dynamicActive = computed(
  () =>
    dynamicEnabled.value &&
    isBinanceActive.value &&
    dynamicSourcesEnabled.value &&
    (!apiKeyRequired.value || hasApiKey.value),
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
      await loadAssetsBreakdown(force);
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
  dynamicEnabled.value = Boolean(data.dynamicEnabled);
  hasApiKey.value = Boolean(data.hasApiKey);
  isBinanceActive.value = Boolean(data.isBinanceActive);
  dynamicSources.value = buildDynamicSources(data.dynamicSources);
  dynamicOiSource.value = data.dynamicOiSource || "nofx";
  dynamicRefreshMinutes.value = Number.isFinite(data.dynamicRefreshMinutes)
    ? data.dynamicRefreshMinutes
    : 10;
};

const persistMarketCache = () => {
  writeMarketCache({
    assets: [...assets.value],
    intervals: [...intervals.value],
    dynamicEnabled: dynamicEnabled.value,
    hasApiKey: hasApiKey.value,
    isBinanceActive: isBinanceActive.value,
    dynamicSources: buildDynamicSources(dynamicSources.value),
    dynamicRefreshMinutes: dynamicRefreshMinutes.value,
    dynamicOiSource: dynamicOiSource.value,
  });
};

const normalizeAssetList = (list: string[]) =>
  Array.from(
    new Set(
      list
        .map((item) => item?.toString().trim().toUpperCase())
        .filter((item) => item),
    ),
  );

const loadAssetsBreakdown = async (force = false) => {
  const baseUrl = force
    ? "/api/v1/market/monitored-assets?include_positions=false&force_refresh=true"
    : "/api/v1/market/monitored-assets?include_positions=false";

  try {
    const response = await fetch(baseUrl);
    const data = await response.json();
    baseAssets.value = Array.isArray(data?.data) ? normalizeAssetList(data.data) : [];
  } catch {
    baseAssets.value = [];
  }

  try {
    const response = await fetch("/api/v1/portfolio/snapshot");
    const data = await response.json();
    const positions = Array.isArray(data?.data?.positions) ? data.data.positions : [];
    openPositions.value = normalizeAssetList(positions.map((pos: { symbol?: string }) => pos.symbol || ""));
  } catch {
    openPositions.value = [];
  }

  try {
    const response = await fetch("/api/v1/market/dynamic-assets/volatility");
    const data = await response.json();
    removedHighVolAssets.value = Array.isArray(data?.data?.removed_assets)
      ? normalizeAssetList(data.data.removed_assets)
      : [];
  } catch {
    removedHighVolAssets.value = [];
  }
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
      requests.push(fetch("/api/v1/market/monitored-intervals"));
    }

    const [dynamicRes, assetsRes, intervalsRes] = await Promise.all(requests);
    const dynamicData = await dynamicRes.json();
    const assetsData = await assetsRes.json();

    assets.value = Array.isArray(assetsData?.data) ? assetsData.data : [];

    if (shouldFetchCore && intervalsRes) {
      const intervalsData = await intervalsRes.json();
      intervals.value = Array.isArray(intervalsData?.data) ? intervalsData.data : [];
    }

    if (dynamicData?.data) {
      const dynamicConfig = dynamicData.data;
      dynamicEnabled.value = Boolean(dynamicConfig.enabled);
      hasApiKey.value = Boolean(dynamicConfig.api_key_present);
      dynamicOiSource.value = dynamicConfig.oi_source === "custom" ? "custom" : "nofx";
      dynamicSources.value = buildDynamicSources(dynamicConfig.sources);
      dynamicRefreshMinutes.value = Math.max(
        1,
        Math.round((dynamicConfig.refresh_interval_seconds || 600) / 60),
      );
      isBinanceActive.value = Boolean(dynamicConfig.is_binance_active);
    }
    await loadAssetsBreakdown(force);
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
      dynamicOiSource.value = config.oi_source === "custom" ? "custom" : "nofx";
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
