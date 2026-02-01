<template>
  <div class="flex min-h-0 flex-1 flex-col gap-4">
    <BaseCard>
      <div class="flex items-start justify-between gap-3">
        <div>
          <div class="text-xs uppercase tracking-wide text-muted">AI Models</div>
          <p class="mt-1 text-xs text-muted">
            Manage provider credentials, defaults, and OpenAI-compatible endpoints.
          </p>
        </div>
        <button
          class="rounded-md border border-border bg-panel px-3 py-2 text-xs text-muted hover:text-text"
          type="button"
          :disabled="isLoading"
          @click="loadProviders(true)"
        >
          {{ isLoading ? "Refreshing..." : "Refresh" }}
        </button>
      </div>

      <div class="mt-4">
        <div
          v-if="showLoading"
          class="grid gap-4 lg:grid-cols-[220px_minmax(0,1fr)] animate-pulse"
        >
          <div class="space-y-2">
            <div class="h-3 w-24 rounded bg-panel/60"></div>
            <div class="space-y-2">
              <div class="h-14 rounded-md bg-panel/50"></div>
              <div class="h-14 rounded-md bg-panel/40"></div>
              <div class="h-14 rounded-md bg-panel/40"></div>
            </div>
          </div>
          <div class="space-y-3">
            <div class="h-3 w-40 rounded bg-panel/60"></div>
            <div class="grid gap-3 sm:grid-cols-2">
              <div class="h-10 rounded-md bg-panel/50"></div>
              <div class="h-10 rounded-md bg-panel/40"></div>
              <div class="h-24 rounded-md bg-panel/40 sm:col-span-2"></div>
              <div class="h-10 rounded-md bg-panel/40 sm:col-span-2"></div>
              <div class="h-10 rounded-md bg-panel/50 sm:col-span-2"></div>
            </div>
            <div class="flex flex-wrap items-center gap-2">
              <div class="h-8 w-20 rounded bg-panel/50"></div>
              <div class="h-8 w-16 rounded bg-panel/40"></div>
              <div class="h-8 w-20 rounded bg-panel/40"></div>
            </div>
          </div>
        </div>

        <div v-else class="grid gap-4 lg:grid-cols-[220px_minmax(0,1fr)]">
          <div class="space-y-2">
            <div class="text-[11px] uppercase tracking-wide text-muted">Providers</div>
            <button
              v-for="provider in providers"
              :key="provider.name"
              class="w-full rounded-md border px-3 py-2 text-left text-xs transition"
              :class="
                provider.name === selectedProvider
                  ? 'border-accent/60 bg-panel text-text'
                  : 'border-border bg-panel/40 text-muted hover:text-text'
              "
              type="button"
              @click="selectedProvider = provider.name"
            >
              <div class="flex items-center justify-between">
                <span class="font-display text-sm text-text">{{ providerLabel(provider) }}</span>
                <span class="h-2 w-2 rounded-full" :class="providerStatusDot(provider)"></span>
              </div>
              <div class="mt-1 text-[11px] text-muted">
                {{ provider.default_model || "No default model" }}
              </div>
            </button>
          </div>

          <div class="space-y-4">
            <div v-if="!activeProvider" class="text-xs text-muted">
              Select a provider to configure.
            </div>

            <div v-else class="space-y-4">
              <div class="grid gap-3 sm:grid-cols-2">
                <label class="text-[11px] text-muted">
                  Provider
                  <input
                    class="mt-2 w-full rounded-md border border-border bg-panel px-3 py-2 text-xs text-text"
                    :value="activeProvider.name"
                    type="text"
                    readonly
                  />
                </label>

                <label class="text-[11px] text-muted">
                  Default Model
                  <select
                    v-model="form.defaultModel"
                    class="mt-2 w-full rounded-md border border-border bg-panel px-3 py-2 text-xs text-text"
                    :disabled="modelList.length === 0"
                  >
                    <option value="">Select model</option>
                    <option v-for="model in modelList" :key="model" :value="model">
                      {{ model }}
                    </option>
                  </select>
                </label>

                <div class="rounded-md border border-border bg-panel/50 p-3 sm:col-span-2">
                  <div class="flex items-center justify-between">
                    <div class="text-[11px] uppercase tracking-wide text-muted">Available Models</div>
                    <span class="text-[11px] text-muted">{{ modelList.length }} total</span>
                  </div>
                  <div class="mt-2 flex flex-wrap items-center gap-2">
                    <input
                      v-model="modelSearch"
                      class="min-w-[160px] flex-1 rounded-md border border-border bg-panel px-3 py-2 text-xs text-text"
                      type="text"
                      placeholder="Search models"
                    />
                    <button
                      v-if="modelSearch"
                      class="rounded-md border border-border bg-panel px-3 py-2 text-xs text-muted hover:text-text"
                      type="button"
                      @click="modelSearch = ''"
                    >
                      Clear
                    </button>
                  </div>
                  <div class="mt-3 max-h-40 overflow-y-auto pr-1 scrollbar-hidden">
                    <div v-if="filteredModels.length === 0" class="text-[11px] text-muted">
                      No models match your search.
                    </div>
                    <div v-else class="flex flex-wrap gap-2">
                      <button
                        v-for="model in filteredModels"
                        :key="model"
                        class="rounded-md border px-2 py-1 text-[11px] transition"
                        :class="
                          model === form.defaultModel
                            ? 'border-accent/60 bg-accent/10 text-text'
                            : 'border-border bg-panel text-muted hover:text-text'
                        "
                        type="button"
                        @click="form.defaultModel = model"
                      >
                        {{ model }}
                      </button>
                    </div>
                  </div>
                </div>

                <label class="text-[11px] text-muted sm:col-span-2">
                  Base URL (OpenAI Protocol)
                  <input
                    v-model="form.baseUrl"
                    class="mt-2 w-full rounded-md border border-border bg-panel px-3 py-2 text-xs text-text"
                    type="text"
                    placeholder="https://api.openai.com/v1"
                  />
                </label>

                <label class="text-[11px] text-muted sm:col-span-2">
                  API Key
                  <div class="mt-2 flex flex-wrap items-center gap-2">
                    <input
                      v-model="form.apiKey"
                      class="min-w-[220px] flex-1 rounded-md border border-border bg-panel px-3 py-2 text-xs text-text"
                      :type="showKey ? 'text' : 'password'"
                      :placeholder="activeProvider.configured ? 'Configured' : 'Enter API key'"
                      autocomplete="off"
                    />
                    <button
                      class="rounded-md border border-border bg-panel px-3 py-2 text-xs text-muted hover:text-text"
                      type="button"
                      @click="showKey = !showKey"
                    >
                      {{ showKey ? "Hide" : "Show" }}
                    </button>
                    <BaseBadge v-if="activeProvider.configured">Configured</BaseBadge>
                  </div>
                  <p class="mt-2 text-[11px] text-muted">
                    Leave blank to keep the existing key.
                  </p>
                </label>

                <label class="flex items-center gap-2 text-xs text-muted sm:col-span-2">
                  <input v-model="form.isEnabled" type="checkbox" />
                  Enabled
                </label>
              </div>

              <div class="flex flex-wrap items-center gap-2">
                <button
                  class="rounded-md border border-border bg-panel px-3 py-2 text-xs text-muted hover:text-text"
                  type="button"
                  :disabled="isValidating"
                  @click="validateProvider"
                >
                  {{ isValidating ? "Validating..." : "Validate" }}
                </button>
                <button
                  class="rounded-md border border-border bg-accent px-3 py-2 text-xs font-medium text-base"
                  type="button"
                  :disabled="isSaving"
                  @click="saveProvider"
                >
                  {{ isSaving ? "Saving..." : "Save" }}
                </button>
                <button
                  class="rounded-md border border-negative/40 bg-negative/10 px-3 py-2 text-xs text-negative"
                  type="button"
                  @click="deleteProvider"
                >
                  Delete/Clear
                </button>
                <span v-if="statusMessage" class="text-xs" :class="statusToneClass">
                  {{ statusMessage }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </BaseCard>

    <BaseCard>
      <div>
        <div class="text-xs uppercase tracking-wide text-muted">Add OpenAI-Compatible Provider</div>
        <p class="mt-1 text-xs text-muted">Register a custom endpoint with OpenAI protocol.</p>
      </div>
      <div class="mt-4 grid gap-3 sm:grid-cols-2">
        <label class="text-[11px] text-muted">
          Provider ID
          <input
            v-model="customProviderId"
            class="mt-2 w-full rounded-md border border-border bg-panel px-3 py-2 text-xs text-text"
            type="text"
            placeholder="mylab"
          />
        </label>
        <label class="text-[11px] text-muted">
          Base URL
          <input
            v-model="customBaseUrl"
            class="mt-2 w-full rounded-md border border-border bg-panel px-3 py-2 text-xs text-text"
            type="text"
            placeholder="https://api.yourhost.com/v1"
          />
        </label>
      </div>
      <div class="mt-3 flex flex-wrap items-center gap-2">
        <button
          class="rounded-md border border-border bg-accent px-3 py-2 text-xs font-medium text-base"
          type="button"
          :disabled="isAddingCustom"
          @click="addCustomProvider"
        >
          {{ isAddingCustom ? "Adding..." : "Add Provider" }}
        </button>
        <span v-if="customStatusMessage" class="text-xs" :class="customStatusToneClass">
          {{ customStatusMessage }}
        </span>
      </div>
      <p class="mt-2 text-[11px] text-muted">
        Custom providers must support the chat/completions and models endpoints.
      </p>
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
import type { ProviderInfo } from "@/services/settingsCache";
import {
  readModelCache,
  readProvidersCache,
  writeModelCache,
  writeProvidersCache,
} from "@/services/settingsCache";

const providers = ref<ProviderInfo[]>([]);
const selectedProvider = ref("");
const providerModels = ref<string[]>([]);
const showKey = ref(false);
const isLoading = ref(false);
const hasLoaded = ref(false);
const isSaving = ref(false);
const isValidating = ref(false);
const statusMessage = ref("");
const statusTone = ref<"info" | "success" | "error">("info");
const error = ref("");
const modelSearch = ref("");

const customProviderId = ref("");
const customBaseUrl = ref("");
const customStatusMessage = ref("");
const customStatusTone = ref<"info" | "success" | "error">("info");
const isAddingCustom = ref(false);

const form = reactive({
  apiKey: "",
  defaultModel: "",
  baseUrl: "",
  isEnabled: true,
});

const activeProvider = computed(
  () => providers.value.find((provider) => provider.name === selectedProvider.value) || null,
);

const showLoading = computed(() => isLoading.value && !hasLoaded.value);

const statusToneClass = computed(() => {
  if (statusTone.value === "success") return "text-positive";
  if (statusTone.value === "error") return "text-negative";
  return "text-muted";
});

const customStatusToneClass = computed(() => {
  if (customStatusTone.value === "success") return "text-positive";
  if (customStatusTone.value === "error") return "text-negative";
  return "text-muted";
});

const modelList = computed(() => {
  const base = [...(activeProvider.value?.models || []), ...providerModels.value];
  const seen = new Set<string>();
  const result: string[] = [];
  base.forEach((model) => {
    if (!model || seen.has(model)) return;
    seen.add(model);
    result.push(model);
  });
  if (form.defaultModel && !seen.has(form.defaultModel)) {
    result.unshift(form.defaultModel);
  }
  return result;
});

const filteredModels = computed(() => {
  const query = modelSearch.value.trim().toLowerCase();
  if (!query) return modelList.value;
  return modelList.value.filter((model) => model.toLowerCase().includes(query));
});

const providerLabel = (provider: ProviderInfo) =>
  provider.settings?.display_name || provider.name;

const providerStatusDot = (provider: ProviderInfo) => {
  if (provider.is_enabled === false) return "bg-muted";
  if (provider.configured) return "bg-accent";
  return "bg-negative";
};

const setStatus = (message: string, tone: "info" | "success" | "error" = "info") => {
  statusMessage.value = message;
  statusTone.value = tone;
  window.setTimeout(() => {
    if (statusMessage.value === message) statusMessage.value = "";
  }, 4000);
};

const setCustomStatus = (message: string, tone: "info" | "success" | "error" = "info") => {
  customStatusMessage.value = message;
  customStatusTone.value = tone;
  window.setTimeout(() => {
    if (customStatusMessage.value === message) customStatusMessage.value = "";
  }, 4000);
};

const syncForm = (provider: ProviderInfo | null) => {
  if (!provider) return;
  form.apiKey = "";
  form.defaultModel = provider.default_model || "";
  form.baseUrl = provider.settings?.base_url || "";
  form.isEnabled = provider.is_enabled !== false;
  showKey.value = false;
  providerModels.value = Array.isArray(provider.models) ? provider.models : [];
  modelSearch.value = "";
};

const loadProviderModels = async (providerName: string, force = false) => {
  if (!providerName) return;
  if (!force) {
    const cached = readModelCache(providerName);
    if (cached) {
      providerModels.value = cached;
      return;
    }
  }
  try {
    const response = await fetch(`/api/v1/ai/providers/${providerName}/models`);
    const data = await response.json();
    if (data?.data?.models && Array.isArray(data.data.models)) {
      providerModels.value = data.data.models;
      writeModelCache(providerName, data.data.models);
    }
  } catch {
    // Ignore model fetch errors
  }
};

const applyProvidersList = async (list: ProviderInfo[]) => {
  providers.value = list;
  const previousSelection = selectedProvider.value;
  let selectionChanged = false;
  if (!selectedProvider.value && list.length > 0) {
    selectedProvider.value = list[0].name;
    selectionChanged = true;
  } else if (
    selectedProvider.value &&
    !list.some((provider) => provider.name === selectedProvider.value)
  ) {
    selectedProvider.value = list[0]?.name || "";
    selectionChanged = true;
  }
  if (!selectionChanged && previousSelection === selectedProvider.value) {
    const active = list.find((provider) => provider.name === selectedProvider.value) || null;
    syncForm(active);
    if (active) {
      await loadProviderModels(active.name);
    }
  }
};

const loadProviders = async (force = false) => {
  isLoading.value = true;
  error.value = "";
  try {
    if (!force) {
      const cached = readProvidersCache();
      if (cached) {
        await applyProvidersList(cached);
        hasLoaded.value = true;
        return;
      }
    }
    const response = await fetch("/api/v1/ai/providers");
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data?.error?.message || "Failed to load providers.");
    }
    const list = data.data || [];
    await applyProvidersList(list);
    writeProvidersCache(list);
    hasLoaded.value = true;
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Failed to load providers.";
  } finally {
    isLoading.value = false;
  }
};

const saveProvider = async () => {
  if (!activeProvider.value) return;
  isSaving.value = true;
  try {
    const payload: Record<string, unknown> = {
      provider: activeProvider.value.name,
      default_model: form.defaultModel || null,
      is_enabled: form.isEnabled,
    };
    if (form.apiKey.trim()) {
      payload.api_key = form.apiKey.trim();
    }
    if (form.baseUrl.trim()) {
      payload.base_url = form.baseUrl.trim();
    }
    const response = await fetch("/api/v1/ai/providers", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data?.error?.message || "Failed to save provider.");
    form.apiKey = "";
    setStatus("Provider configuration saved.", "success");
    await loadProviders(true);
    if (activeProvider.value) {
      await loadProviderModels(activeProvider.value.name, true);
    }
  } catch (err) {
    setStatus(err instanceof Error ? err.message : "Failed to save provider.", "error");
  } finally {
    isSaving.value = false;
  }
};

const validateProvider = async () => {
  if (!activeProvider.value) return;
  isValidating.value = true;
  try {
    const payload: Record<string, unknown> = {
      provider: activeProvider.value.name,
      model: form.defaultModel || undefined,
    };
    if (form.apiKey.trim()) {
      payload.api_key = form.apiKey.trim();
    }
    const response = await fetch(`/api/v1/ai/providers/${activeProvider.value.name}/validate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data?.error?.message || "Validation failed.");
    }
    const latency = data?.data?.latency_ms ? `${data.data.latency_ms}ms` : "ok";
    setStatus(`Validated (${latency}).`, "success");
  } catch (err) {
    setStatus(err instanceof Error ? err.message : "Validation failed.", "error");
  } finally {
    isValidating.value = false;
  }
};

const deleteProvider = async () => {
  if (!activeProvider.value) return;
  const confirmed = window.confirm(
    `Delete configuration for ${activeProvider.value.name}? This clears stored keys.`,
  );
  if (!confirmed) return;
  try {
    const response = await fetch(`/api/v1/ai/providers/${activeProvider.value.name}`, {
      method: "DELETE",
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data?.error?.message || "Failed to delete provider.");
    setStatus("Provider cleared.", "success");
    await loadProviders(true);
  } catch (err) {
    setStatus(err instanceof Error ? err.message : "Failed to delete provider.", "error");
  }
};

const addCustomProvider = async () => {
  const name = customProviderId.value.trim();
  const baseUrl = customBaseUrl.value.trim();
  if (!name || !baseUrl) {
    setCustomStatus("Provider ID and base URL are required.", "error");
    return;
  }
  isAddingCustom.value = true;
  try {
    const response = await fetch("/api/v1/ai/providers", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        provider: name.toLowerCase(),
        base_url: baseUrl,
        is_enabled: true,
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data?.error?.message || "Failed to add provider.");
    setCustomStatus("Provider added.", "success");
    customProviderId.value = "";
    customBaseUrl.value = "";
    await loadProviders(true);
  } catch (err) {
    setCustomStatus(err instanceof Error ? err.message : "Failed to add provider.", "error");
  } finally {
    isAddingCustom.value = false;
  }
};

watch(
  selectedProvider,
  (value) => {
    const provider = providers.value.find((item) => item.name === value) || null;
    syncForm(provider);
    if (provider) {
      loadProviderModels(provider.name);
    }
  },
  { immediate: true },
);

onMounted(() => {
  loadProviders();
});
</script>
