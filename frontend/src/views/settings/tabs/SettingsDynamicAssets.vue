<template>
  <div class="flex min-h-0 flex-1 flex-col gap-4">
    <BaseCard>
      <div class="flex items-center justify-between">
        <div>
          <div class="text-xs uppercase tracking-wide text-muted">Dynamic Assets</div>
          <p class="mt-1 text-xs text-muted">
            Configure multi-source feeds for automated asset lists.
          </p>
        </div>
      </div>
    </BaseCard>

    <BaseCard>
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

    <!-- 2-column layout for Refresh Interval and Threshold -->
    <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
      <BaseCard>
        <div class="flex items-center justify-between">
          <div>
            <div class="text-xs uppercase tracking-wide text-muted">Refresh Interval</div>
            <p class="mt-1 text-xs text-muted">How often to refresh.</p>
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
        <div class="rounded-md border border-border bg-panel/50 p-3">
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

        <div class="rounded-md border border-border bg-panel/50 p-3">
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
                <option v-for="duration in durations" :key="duration" :value="duration">
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
                <option v-for="duration in durations" :key="duration" :value="duration">
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
import { computed, onMounted, reactive, ref } from "vue";
import BaseBadge from "@/components/BaseBadge.vue";
import BaseCard from "@/components/BaseCard.vue";
import type { DynamicSources, MarketCacheData } from "@/services/settingsCache";
import { readMarketCache, writeMarketCache } from "@/services/settingsCache";

const durations = ["5m", "15m", "30m", "1h", "4h", "8h", "12h", "24h"];
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

const sources = reactive<DynamicSources>(buildDynamicSources());

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
  };
  if (patch.dynamicSources) {
    next.dynamicSources = buildDynamicSources(patch.dynamicSources);
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
      });
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Failed to load dynamic assets config.";
  }
};

const saveConfig = async () => {
  isSaving.value = true;
  try {
    const payload: Record<string, unknown> = {
      enabled: dynamicEnabled.value,
      refresh_interval_seconds: Math.round(
        Math.min(60, Math.max(1, refreshIntervalMinutes.value || 10)) * 60,
      ),
      volatility_threshold_pct: Math.min(100, Math.max(5, volatilityThresholdPct.value || 20)),
      sources: buildDynamicSources(sources),
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
    });
    const refreshed = await refreshMonitoredAssets();
    setStatus(
      refreshed ? "Configuration saved. Asset list refreshed." : "Configuration saved.",
      "success",
    );
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

onMounted(() => {
  loadConfig();
});
</script>
