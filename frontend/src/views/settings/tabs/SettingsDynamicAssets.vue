<template>
  <div class="flex min-h-0 flex-1 flex-col gap-4">
    <BaseCard>
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div class="text-xs uppercase tracking-wide text-muted">Dynamic Assets</div>
          <p class="mt-1 text-xs text-muted">
            Configure multi-source feeds for automated asset lists.
          </p>
        </div>
        <div class="flex items-center gap-2">
          <button
            class="rounded-md border border-border px-3 py-2 text-xs font-medium"
            :class="oiSource === 'nofx' ? 'bg-accent text-base' : 'bg-panel text-muted hover:text-text'"
            type="button"
            @click="oiSource = 'nofx'"
          >
            Nofx
          </button>
          <button
            class="rounded-md border border-border px-3 py-2 text-xs font-medium"
            :class="oiSource === 'custom' ? 'bg-accent text-base' : 'bg-panel text-muted hover:text-text'"
            type="button"
            @click="oiSource = 'custom'"
          >
            Custom OI
          </button>
        </div>
      </div>
    </BaseCard>

    <BaseCard v-if="oiSource === 'nofx'">
      <div class="flex items-center justify-between">
        <div>
          <div class="text-xs uppercase tracking-wide text-muted">API Key</div>
          <p class="mt-1 text-xs text-muted">Required for fetching dynamic assets.</p>
        </div>
        <BaseBadge>{{ hasApiKey ? "Configured" : "Missing" }}</BaseBadge>
      </div>

      <div class="mt-3 flex flex-wrap items-center gap-2">
        <input
          v-model="apiKeyInput"
          class="min-w-[220px] flex-1 rounded-md border border-border bg-panel px-3 py-2 text-xs text-text"
          :type="showKey ? 'text' : 'password'"
          :placeholder="hasApiKey ? 'Configured' : 'Enter API key'"
        />
        <button
          class="rounded-md border border-border bg-panel px-3 py-2 text-xs text-muted hover:text-text"
          type="button"
          @click="showKey = !showKey"
        >
          {{ showKey ? "Hide" : "Show" }}
        </button>
      </div>
      <p class="mt-2 text-[11px] text-muted">
        Leave blank to keep the existing key.
      </p>
    </BaseCard>
    <BaseCard v-else>
      <div class="flex items-center justify-between">
        <div>
          <div class="text-xs uppercase tracking-wide text-muted">OI Source Refresh</div>
          <p class="mt-1 text-xs text-muted">
            Refresh cadence for the custom OI ranking lists.
          </p>
        </div>
        <div class="text-right">
          <BaseBadge>{{ oiRefreshMinutes }} min</BaseBadge>
          <p class="mt-1 text-[11px]" :class="oiStatusToneClass">
            {{ oiStatusLabel }}
          </p>
        </div>
      </div>
      <div class="mt-3 flex items-center gap-2">
        <input
          v-model.number="oiRefreshMinutes"
          class="w-24 rounded-md border border-border bg-panel px-2 py-1 text-xs"
          type="number"
          min="10"
          max="720"
        />
        <span class="text-[11px] text-muted">min (10-720)</span>
      </div>
    </BaseCard>

    <!-- 2-column layout for Refresh Interval and Threshold -->
    <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
      <BaseCard>
        <div class="flex items-center justify-between">
          <div>
            <div class="text-xs uppercase tracking-wide text-muted">Dynamic Assets Refresh</div>
            <p class="mt-1 text-xs text-muted">How often to refresh dynamic assets.</p>
          </div>
          <BaseBadge>{{ refreshIntervalMinutes }} min</BaseBadge>
        </div>
        <div class="mt-3 flex items-center gap-2">
          <input
            v-model.number="refreshIntervalMinutes"
            class="w-24 rounded-md border border-border bg-panel px-2 py-1 text-xs"
            type="number"
            min="1"
            max="60"
          />
          <span class="text-[11px] text-muted">min (1-60)</span>
        </div>
      </BaseCard>

      <BaseCard>
        <div class="flex items-center justify-between">
          <div>
            <div class="text-xs uppercase tracking-wide text-muted">24hr Change Threshold</div>
            <p class="mt-1 text-xs text-muted">Filter out volatile assets.</p>
          </div>
          <BaseBadge>{{ volatilityThresholdPct }}%</BaseBadge>
        </div>
        <div class="mt-3 flex items-center gap-3">
          <input
            v-model.number="volatilityThresholdPct"
            class="flex-1 cursor-pointer"
            type="range"
            min="5"
            max="100"
            step="5"
          />
          <span class="w-12 text-right text-xs text-muted">{{ volatilityThresholdPct }}%</span>
        </div>
      </BaseCard>
    </div>

    <BaseCard>
      <div class="text-xs uppercase tracking-wide text-muted">Sources</div>
      <p class="mt-1 text-xs text-muted">
        Assets from all enabled sources are merged and deduplicated.
      </p>
      <!-- 2-column grid for source cards -->
      <div class="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
        <div v-if="oiSource === 'nofx'" class="rounded-md border border-border bg-panel/50 p-3">
          <div class="flex items-center justify-between gap-3">
            <label class="flex items-center gap-2 text-sm text-text">
              <input v-model="sources.ai500.enabled" type="checkbox" />
              AI500
            </label>
            <span class="text-[11px] text-muted">Momentum / breakout list</span>
          </div>
          <div class="mt-3 flex items-center gap-2">
            <span class="text-[11px] text-muted">Limit</span>
            <input
              v-model.number="sources.ai500.limit"
              class="w-20 rounded-md border border-border bg-panel px-2 py-1 text-xs"
              type="number"
              min="1"
              max="100"
            />
          </div>
        </div>

        <div v-if="oiSource === 'nofx'" class="rounded-md border border-border bg-panel/50 p-3">
          <div class="flex items-center justify-between gap-3">
            <label class="flex items-center gap-2 text-sm text-text">
              <input v-model="sources.ai300.enabled" type="checkbox" />
              AI300
            </label>
            <span class="text-[11px] text-muted">Fund flow ranking</span>
          </div>
          <div class="mt-3 flex flex-wrap items-center gap-3">
            <div class="flex items-center gap-2">
              <span class="text-[11px] text-muted">Limit</span>
              <input
                v-model.number="sources.ai300.limit"
                class="w-20 rounded-md border border-border bg-panel px-2 py-1 text-xs"
                type="number"
                min="1"
                max="100"
              />
            </div>
            <div class="flex items-center gap-2">
              <span class="text-[11px] text-muted">Level</span>
              <select
                v-model="sources.ai300.level"
                class="rounded-md border border-border bg-panel px-2 py-1 text-xs"
              >
                <option value="">All</option>
                <option value="S">S</option>
                <option value="A">A</option>
                <option value="B">B</option>
              </select>
            </div>
          </div>
        </div>

        <div class="rounded-md border border-border bg-panel/50 p-3">
          <div class="flex items-center justify-between gap-3">
            <label class="flex items-center gap-2 text-sm text-text">
              <input v-model="sources.oi_top.enabled" type="checkbox" />
              OI Top
            </label>
            <span class="text-[11px] text-muted">Highest OI growth</span>
          </div>
          <div class="mt-3 flex flex-wrap items-center gap-3">
            <div class="flex items-center gap-2">
              <span class="text-[11px] text-muted">Limit</span>
              <input
                v-model.number="sources.oi_top.limit"
                class="w-20 rounded-md border border-border bg-panel px-2 py-1 text-xs"
                type="number"
                min="1"
                max="100"
              />
            </div>
            <div class="flex items-center gap-2">
              <span class="text-[11px] text-muted">Duration</span>
              <select
                v-model="sources.oi_top.duration"
                class="rounded-md border border-border bg-panel px-2 py-1 text-xs"
              >
                <option
                  v-for="duration in oiDurationOptions"
                  :key="duration"
                  :value="duration"
                >
                  {{ duration }}
                </option>
              </select>
            </div>
          </div>
        </div>

        <div class="rounded-md border border-border bg-panel/50 p-3">
          <div class="flex items-center justify-between gap-3">
            <label class="flex items-center gap-2 text-sm text-text">
              <input v-model="sources.oi_low.enabled" type="checkbox" />
              OI Low
            </label>
            <span class="text-[11px] text-muted">Declining OI</span>
          </div>
          <div class="mt-3 flex flex-wrap items-center gap-3">
            <div class="flex items-center gap-2">
              <span class="text-[11px] text-muted">Limit</span>
              <input
                v-model.number="sources.oi_low.limit"
                class="w-20 rounded-md border border-border bg-panel px-2 py-1 text-xs"
                type="number"
                min="1"
                max="100"
              />
            </div>
            <div class="flex items-center gap-2">
              <span class="text-[11px] text-muted">Duration</span>
              <select
                v-model="sources.oi_low.duration"
                class="rounded-md border border-border bg-panel px-2 py-1 text-xs"
              >
                <option
                  v-for="duration in oiDurationOptions"
                  :key="duration"
                  :value="duration"
                >
                  {{ duration }}
                </option>
              </select>
            </div>
          </div>
        </div>
      </div>

      <div class="mt-4 flex flex-wrap gap-2">
        <button
          class="rounded-md border border-border bg-accent px-3 py-2 text-xs font-medium text-base"
          type="button"
          :disabled="isSaving"
          @click="saveConfig"
        >
          {{ isSaving ? "Saving..." : "Save Configuration" }}
        </button>
        <button
          class="rounded-md border border-border bg-panel px-3 py-2 text-xs text-muted hover:text-text"
          type="button"
          :disabled="isTesting"
          @click="testFetch"
        >
          {{ isTesting ? "Testing..." : "Test Fetch" }}
        </button>
      </div>

      <div v-if="statusMessage" class="mt-2 text-xs" :class="statusToneClass">
        {{ statusMessage }}
      </div>
    </BaseCard>

    <div v-if="error" class="text-xs text-negative">
      {{ error }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import BaseBadge from "@/components/BaseBadge.vue";
import BaseCard from "@/components/BaseCard.vue";
import type { DynamicSources, MarketCacheData } from "@/services/settingsCache";
import { readMarketCache, writeMarketCache } from "@/services/settingsCache";

const nofxDurations = ["5m", "15m", "30m", "1h", "4h", "8h", "12h", "24h"];
const customDurations = ["1h", "4h", "12h"];
const defaultSources: DynamicSources = {
  ai500: { enabled: false, limit: 10 },
  ai300: { enabled: false, limit: 20, level: "" },
  oi_top: { enabled: false, limit: 20, duration: "1h" },
  oi_low: { enabled: false, limit: 20, duration: "1h" },
};

const buildDynamicSources = (value?: Partial<DynamicSources> | null): DynamicSources => ({
  ai500: { ...defaultSources.ai500, ...(value?.ai500 || {}) },
  ai300: { ...defaultSources.ai300, ...(value?.ai300 || {}) },
  oi_top: { ...defaultSources.oi_top, ...(value?.oi_top || {}) },
  oi_low: { ...defaultSources.oi_low, ...(value?.oi_low || {}) },
});

const dynamicEnabled = ref(false);
const hasApiKey = ref(false);
const apiKeyInput = ref("");
const showKey = ref(false);
const isSaving = ref(false);
const isTesting = ref(false);
const statusMessage = ref("");
const statusTone = ref<"info" | "success" | "error">("info");
const error = ref("");
const isBinanceActive = ref(false);
const refreshIntervalMinutes = ref(10);
const volatilityThresholdPct = ref(20);
const oiSource = ref<"nofx" | "custom">("nofx");
const oiRefreshMinutes = ref(30);
const oiStaleMinutes = ref(90);
const oiStatus = ref<"unknown" | "warming" | "ready" | "stale" | "error">("unknown");
const oiStatusLoading = ref(false);

const sources = reactive<DynamicSources>(buildDynamicSources());

const oiDurationOptions = computed(() =>
  oiSource.value === "custom" ? customDurations : nofxDurations,
);

const oiStatusLabel = computed(() => {
  if (oiSource.value !== "custom") return "";
  if (oiStatusLoading.value) return "Checking...";
  if (oiStatus.value === "ready") return "Up to date";
  if (oiStatus.value === "warming") return "Refreshing";
  if (oiStatus.value === "stale") return "Stale";
  if (oiStatus.value === "error") return "Error";
  return "Unknown";
});

const oiStatusToneClass = computed(() => {
  if (oiStatus.value === "ready") return "text-positive";
  if (oiStatus.value === "error" || oiStatus.value === "stale") return "text-negative";
  return "text-muted";
});

const applyDynamicSources = (value?: Partial<DynamicSources> | null) => {
  const normalized = buildDynamicSources(value);
  sources.ai500 = normalized.ai500;
  sources.ai300 = normalized.ai300;
  sources.oi_top = normalized.oi_top;
  sources.oi_low = normalized.oi_low;
  return normalized;
};

const updateMarketCache = (patch: Partial<MarketCacheData>) => {
  const cached = readMarketCache();
  if (!cached) return;
  const next: MarketCacheData = {
    ...cached,
    ...patch,
    dynamicSources: cached.dynamicSources,
    dynamicOiSource: cached.dynamicOiSource || "nofx",
  };
  if (patch.dynamicSources) {
    next.dynamicSources = buildDynamicSources(patch.dynamicSources);
  }
  if (patch.dynamicOiSource) {
    next.dynamicOiSource = patch.dynamicOiSource;
  }
  writeMarketCache(next);
};

const refreshMonitoredAssets = async () => {
  try {
    const response = await fetch("/api/v1/market/monitored-assets?force_refresh=true");
    const data = await response.json();
    if (Array.isArray(data?.data)) {
      updateMarketCache({ assets: data.data });
      return true;
    }
  } catch {
    // Ignore refresh errors.
  }
  return false;
};

const statusToneClass = computed(() => {
  if (statusTone.value === "success") return "text-positive";
  if (statusTone.value === "error") return "text-negative";
  return "text-muted";
});

const setStatus = (message: string, tone: "info" | "success" | "error" = "info") => {
  statusMessage.value = message;
  statusTone.value = tone;
  window.setTimeout(() => {
    if (statusMessage.value === message) statusMessage.value = "";
  }, 4000);
};

const normalizeOiDurations = () => {
  if (oiSource.value !== "custom") return;
  if (!customDurations.includes(sources.oi_top.duration)) {
    sources.oi_top.duration = "1h";
  }
  if (!customDurations.includes(sources.oi_low.duration)) {
    sources.oi_low.duration = "1h";
  }
};

const loadOiConfig = async () => {
  try {
    const response = await fetch("/api/v1/oi-rank/config");
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data?.error?.message || "Failed to load OI config.");
    }
    if (data?.data) {
      oiRefreshMinutes.value = data.data.refresh_interval_minutes ?? oiRefreshMinutes.value;
      oiStaleMinutes.value = data.data.stale_ttl_minutes ?? oiStaleMinutes.value;
    }
  } catch {
    // Ignore OI config errors; we will show status as unknown.
  }
};

const updateOiConfig = async () => {
  if (oiSource.value !== "custom") return true;
  const refreshMinutes = Math.max(10, Math.min(720, Math.round(oiRefreshMinutes.value || 30)));
  const staleMinutes = Math.max(refreshMinutes, Math.round(oiStaleMinutes.value || 90));
  try {
    const response = await fetch("/api/v1/oi-rank/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        refresh_interval_minutes: refreshMinutes,
        stale_ttl_minutes: staleMinutes,
      }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data?.error?.message || "Failed to update OI refresh interval.");
    }
    if (data?.data) {
      oiRefreshMinutes.value = data.data.refresh_interval_minutes ?? refreshMinutes;
      oiStaleMinutes.value = data.data.stale_ttl_minutes ?? staleMinutes;
    } else {
      oiRefreshMinutes.value = refreshMinutes;
      oiStaleMinutes.value = staleMinutes;
    }
    return true;
  } catch (err) {
    setStatus(err instanceof Error ? err.message : "Failed to update OI refresh interval.", "error");
    return false;
  }
};

const resolveOiStatus = async () => {
  if (oiSource.value !== "custom") {
    oiStatus.value = "unknown";
    return;
  }
  const intervals = new Set<string>();
  if (sources.oi_top.enabled) intervals.add(sources.oi_top.duration);
  if (sources.oi_low.enabled) intervals.add(sources.oi_low.duration);
  if (intervals.size === 0) intervals.add("1h");
  oiStatusLoading.value = true;
  try {
    const statuses = await Promise.all(
      Array.from(intervals).map(async (interval) => {
        const response = await fetch(
          `/api/v1/oi-rank/top?interval=${encodeURIComponent(interval)}&limit=1`,
        );
        const data = await response.json();
        if (!response.ok) {
          return "error";
        }
        return data?.data?.status || "unknown";
      }),
    );
    if (statuses.includes("error")) {
      oiStatus.value = "error";
    } else if (statuses.includes("stale")) {
      oiStatus.value = "stale";
    } else if (statuses.includes("warming")) {
      oiStatus.value = "warming";
    } else if (statuses.includes("ready")) {
      oiStatus.value = "ready";
    } else {
      oiStatus.value = "unknown";
    }
  } catch {
    oiStatus.value = "error";
  } finally {
    oiStatusLoading.value = false;
  }
};

const loadConfig = async () => {
  error.value = "";
  try {
    const configRes = await fetch("/api/v1/market/dynamic-assets");
    const configData = await configRes.json();

    if (configData?.data) {
      const dynamicConfig = configData.data;
      dynamicEnabled.value = Boolean(dynamicConfig.enabled);
      hasApiKey.value = Boolean(dynamicConfig.api_key_present);
      const normalizedSources = applyDynamicSources(dynamicConfig.sources);
      oiSource.value = dynamicConfig.oi_source === "custom" ? "custom" : "nofx";
      refreshIntervalMinutes.value = Math.max(
        1,
        Math.round((dynamicConfig.refresh_interval_seconds || 600) / 60),
      );
      volatilityThresholdPct.value = dynamicConfig.volatility_threshold_pct ?? 20;
      isBinanceActive.value = Boolean(dynamicConfig.is_binance_active);
      updateMarketCache({
        dynamicEnabled: dynamicEnabled.value,
        hasApiKey: hasApiKey.value,
        isBinanceActive: isBinanceActive.value,
        dynamicSources: normalizedSources,
        dynamicRefreshMinutes: refreshIntervalMinutes.value,
        dynamicOiSource: oiSource.value,
      });
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Failed to load dynamic assets config.";
  }
};

const saveConfig = async () => {
  isSaving.value = true;
  try {
    if (oiSource.value === "custom") {
      sources.ai500.enabled = false;
      sources.ai300.enabled = false;
      normalizeOiDurations();
    }
    const payload: Record<string, unknown> = {
      enabled: dynamicEnabled.value,
      refresh_interval_seconds: Math.round(
        Math.min(60, Math.max(1, refreshIntervalMinutes.value || 10)) * 60,
      ),
      volatility_threshold_pct: Math.min(100, Math.max(5, volatilityThresholdPct.value || 20)),
      sources: buildDynamicSources(sources),
      oi_source: oiSource.value,
    };
    const apiKey = apiKeyInput.value.trim();
    if (apiKey) {
      payload.api_key = apiKey;
    }

    const response = await fetch("/api/v1/market/dynamic-assets", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data?.error?.message || "Failed to save configuration.");
    }
    let normalizedSources = buildDynamicSources(sources);
    if (data?.data) {
      dynamicEnabled.value = Boolean(data.data.enabled);
      hasApiKey.value = Boolean(data.data.api_key_present);
      oiSource.value = data.data.oi_source === "custom" ? "custom" : "nofx";
      refreshIntervalMinutes.value = Math.max(
        1,
        Math.round((data.data.refresh_interval_seconds || 600) / 60),
      );
      volatilityThresholdPct.value = data.data.volatility_threshold_pct ?? 20;
      isBinanceActive.value = Boolean(data.data.is_binance_active);
      normalizedSources = applyDynamicSources(data.data.sources);
    }
    if (apiKey) {
      apiKeyInput.value = "";
      hasApiKey.value = true;
    }
    updateMarketCache({
      dynamicEnabled: dynamicEnabled.value,
      hasApiKey: hasApiKey.value,
      isBinanceActive: isBinanceActive.value,
      dynamicSources: normalizedSources,
      dynamicRefreshMinutes: refreshIntervalMinutes.value,
      dynamicOiSource: oiSource.value,
    });
    const oiOk = await updateOiConfig();
    const refreshed = await refreshMonitoredAssets();
    if (oiOk) {
      setStatus(
        refreshed ? "Configuration saved. Asset list refreshed." : "Configuration saved.",
        "success",
      );
    } else {
      setStatus("Dynamic assets saved, but OI refresh interval update failed.", "error");
    }
    return true;
  } catch (err) {
    setStatus(err instanceof Error ? err.message : "Failed to save configuration.", "error");
    return false;
  } finally {
    isSaving.value = false;
  }
};

const testFetch = async () => {
  const apiKey = apiKeyInput.value.trim();
  const anyEnabled = Object.values(sources).some((source) => source.enabled);
  if (!anyEnabled) {
    setStatus("Enable at least one source to test.", "error");
    return;
  }
  isTesting.value = true;
  try {
    const payload: Record<string, unknown> = { sources: buildDynamicSources(sources) };
    if (apiKey) {
      payload.api_key = apiKey;
    }
    const response = await fetch("/api/v1/market/dynamic-assets/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data?.error?.message || "Test failed.");
    }
    setStatus(`Fetched ${data.data?.count ?? 0} assets.`, "success");
  } catch (err) {
    setStatus(err instanceof Error ? err.message : "Test failed.", "error");
  } finally {
    isTesting.value = false;
  }
};

watch(
  () => oiSource.value,
  (next) => {
    if (next === "custom") {
      sources.ai500.enabled = false;
      sources.ai300.enabled = false;
      normalizeOiDurations();
      loadOiConfig();
      apiKeyInput.value = "";
      showKey.value = false;
    }
    updateMarketCache({ dynamicOiSource: next });
    resolveOiStatus();
  },
);

watch(
  () => [sources.oi_top.duration, sources.oi_low.duration, sources.oi_top.enabled, sources.oi_low.enabled],
  () => {
    resolveOiStatus();
  },
);

onMounted(() => {
  loadConfig();
  loadOiConfig();
  resolveOiStatus();
});
</script>
