<template>
  <div class="flex h-full min-h-0 flex-1 flex-col gap-3 overflow-hidden">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <h1 class="font-display text-xl">Agent Context Builder</h1>
      <div class="flex flex-wrap items-center gap-2">
        <BaseBadge v-if="store.activeConfig">Config: {{ store.activeConfig.name }}</BaseBadge>
      </div>
    </div>

    <div
      v-if="store.contextError"
      class="rounded-md border border-negative/40 bg-negative/10 px-3 py-2 text-xs text-negative"
    >
      {{ store.contextError }}
    </div>

    <div
      class="grid min-h-0 flex-1 gap-4 overflow-hidden lg:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]"
    >
      <div
        ref="leftPanelRef"
        class="flex min-h-0 flex-col gap-4 overflow-y-auto pr-1 scrollbar-hidden"
      >
        <BaseCard>
          <div class="flex items-center justify-between gap-3">
            <span class="text-xs uppercase tracking-wide text-muted">Configurations</span>
            <span v-if="store.isLoadingConfigs" class="text-[10px] text-muted">Loading...</span>
          </div>
          <div class="mt-3 flex flex-wrap items-center gap-2">
            <select
              v-model="selectedConfigId"
              class="min-w-[220px] flex-1 rounded-md border border-border bg-panel px-2 py-2 text-xs text-text"
              :disabled="store.isLoadingConfigs || store.contextConfigs.length === 0"
            >
              <option v-if="store.contextConfigs.length === 0" value="">No configs</option>
              <option
                v-for="config in store.contextConfigs"
                :key="config.id"
                :value="String(config.id)"
              >
                {{ config.name }}{{ config.is_default ? " (Default)" : "" }}
              </option>
            </select>
            <button
              class="rounded-md border border-border bg-panel px-3 py-2 text-xs text-muted hover:text-text disabled:opacity-50"
              type="button"
              :disabled="store.isSavingConfig || store.isLoadingConfigs || store.activeConfigId === null"
              @click="handleSave"
            >
              {{ store.isSavingConfig ? "Saving..." : "Save" }}
            </button>
            <button
              class="rounded-md border border-border bg-surface px-3 py-2 text-xs text-muted hover:text-text disabled:opacity-50"
              type="button"
              :disabled="store.isSavingConfig || store.isLoadingConfigs"
              @click="openSaveModal"
            >
              {{ store.isSavingConfig ? "Saving..." : "Save As" }}
            </button>
            <button
              class="rounded-md border border-border bg-panel px-3 py-2 text-xs text-negative hover:text-negative/80 disabled:opacity-50"
              type="button"
              :disabled="
                store.isDeletingConfig ||
                store.isLoadingConfigs ||
                store.activeConfig?.is_default ||
                store.activeConfigId === null
              "
              @click="handleDelete"
            >
              Delete
            </button>
          </div>
        </BaseCard>

        <BaseCard>
          <div class="flex items-center justify-between">
            <span class="text-xs uppercase tracking-wide text-muted">Intro and Role</span>
          </div>
          <textarea
            v-model="store.draft.intro"
            class="mt-3 h-[26rem] w-full rounded-md border border-border bg-panel p-3 font-mono text-xs text-text"
            placeholder="Define the role and context..."
          ></textarea>
        </BaseCard>

        <BaseCard>
          <div class="flex items-center justify-between gap-3">
            <span class="text-xs uppercase tracking-wide text-muted">Context Data</span>
            <label class="flex items-center gap-2 text-[11px] text-muted">
              <input ref="selectAllRef" type="checkbox" :checked="allSelected" @change="toggleAll" />
              All
            </label>
          </div>
          <div class="mt-3 space-y-3">
            <div
              v-for="category in contextCategories"
              :key="category.id"
              class="rounded-md border border-border bg-panel/40 p-3"
            >
              <div class="flex items-start justify-between gap-3">
                <label class="flex flex-1 items-start gap-2 text-xs text-muted">
                  <input v-model="store.draft.data_selections" type="checkbox" :value="category.id" />
                  <span class="min-w-0">
                    <span class="block text-sm text-text">{{ category.label }}</span>
                    <span class="block text-[11px] text-muted">{{ category.description }}</span>
                  </span>
                </label>
                <button
                  v-if="category.fields || category.id === 'chart_snapshots'"
                  class="shrink-0 rounded-md border border-border bg-panel px-2 py-1 text-[10px] uppercase tracking-wide text-muted hover:text-text"
                  type="button"
                  @click="toggleCategory(category.id)"
                >
                  {{ isCategoryExpanded(category.id) ? "Hide" : "Details" }}
                </button>
              </div>

              <div
                v-if="isCategoryExpanded(category.id) && isCategorySelected(category.id)"
                class="mt-3 space-y-3 border-t border-border/60 pt-3"
              >
                <div v-if="category.fields" class="grid gap-2 sm:grid-cols-4">
                  <label
                    v-for="field in category.fields"
                    :key="field.id"
                    class="flex items-center gap-2 text-[11px] text-muted"
                  >
                    <input
                      type="checkbox"
                      :checked="isFieldSelected(category.id, field.id)"
                      :disabled="!isCategorySelected(category.id)"
                      @change="(event) =>
                        updateFieldSelection(
                          category.id,
                          field.id,
                          (event.target as HTMLInputElement).checked,
                        )
                      "
                    />
                    <span>{{ field.label }}</span>
                  </label>
                </div>

                <div v-else-if="category.id === 'chart_snapshots'" class="space-y-3">
                  <div class="rounded-md border border-border bg-panel/60 p-3">
                    <div class="flex items-center justify-between gap-2">
                      <div class="text-[10px] uppercase tracking-wide text-muted">Preview Ticker</div>
                      <span v-if="isLoadingAssets" class="text-[10px] text-muted">Loading...</span>
                    </div>
                    <select
                      v-model="selectedChartTicker"
                      class="mt-2 w-full rounded-md border border-border bg-panel px-2 py-2 text-xs text-text"
                      :disabled="!isCategorySelected(category.id) || chartTickerOptions.length === 0"
                    >
                      <option v-for="ticker in chartTickerOptions" :key="ticker" :value="ticker">
                        {{ ticker }}
                      </option>
                    </select>
                    <p class="mt-2 text-[10px] text-muted">
                      Pulled from Settings → Market → Monitored Assets.
                    </p>
                  </div>

                  <div class="rounded-md border border-border bg-panel/60 p-3">
                    <div class="flex items-center justify-between gap-2">
                      <div class="text-[10px] uppercase tracking-wide text-muted">Candles per Interval</div>
                      <span v-if="isLoadingIntervals" class="text-[10px] text-muted">Loading...</span>
                    </div>
                    <div class="mt-2 grid gap-2 sm:grid-cols-2">
                      <div
                        v-for="interval in vegasIntervals"
                        :key="interval"
                        class="grid grid-cols-[1fr_auto_auto] items-center gap-2 rounded-md border border-border/70 bg-panel/40 px-2 py-1.5"
                      >
                        <span class="font-mono text-[11px] text-text">{{ interval }}</span>
                        <input
                          class="w-20 rounded-md border border-border bg-panel px-2 py-1 text-[11px] text-text"
                          type="number"
                          min="30"
                          max="200"
                          step="10"
                          :disabled="!isCategorySelected(category.id)"
                          :value="vegasIntervalValue(interval)"
                          @input="(event) => updateVegasInterval(interval, event)"
                        />
                        <button
                          class="rounded-md border border-border bg-panel px-2 py-1 text-[10px] uppercase tracking-wide text-muted hover:text-text disabled:opacity-50"
                          type="button"
                          :disabled="!isCategorySelected(category.id) || isPreviewLoading"
                          @click="previewVegasChart(interval)"
                        >
                          Preview
                        </button>
                      </div>
                      <span v-if="vegasIntervals.length === 0" class="text-[11px] text-muted">
                        No intervals configured.
                      </span>
                    </div>
                    <p class="mt-2 text-[10px] text-muted">
                      Manage intervals in Settings -> Market -> Monitored Intervals.
                    </p>
                  </div>

                  <div class="grid gap-3 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
                    <div class="rounded-md border border-border bg-panel/60 p-3">
                      <div class="text-[10px] uppercase tracking-wide text-muted">EMA Tunnels</div>
                      <div class="mt-2 space-y-2">
                        <label class="flex items-center gap-2 text-[11px] text-muted">
                          <input
                            v-model="store.draft.vegas_show_fast_tunnel"
                            type="checkbox"
                            :disabled="!isCategorySelected(category.id)"
                          />
                          <span class="inline-flex items-center gap-2">
                            <span class="h-2 w-2 rounded-full bg-warning"></span>
                            Fast Tunnel (36/44)
                          </span>
                        </label>
                        <label class="flex items-center gap-2 text-[11px] text-muted">
                          <input
                            v-model="store.draft.vegas_show_medium_tunnel"
                            type="checkbox"
                            :disabled="!isCategorySelected(category.id)"
                          />
                          <span class="inline-flex items-center gap-2">
                            <span class="h-2 w-2 rounded-full bg-sky-400"></span>
                            Medium Tunnel (144/169)
                          </span>
                        </label>
                        <label class="flex items-center gap-2 text-[11px] text-muted">
                          <input
                            v-model="store.draft.vegas_show_slow_tunnel"
                            type="checkbox"
                            :disabled="!isCategorySelected(category.id)"
                          />
                          <span class="inline-flex items-center gap-2">
                            <span class="h-2 w-2 rounded-full bg-positive"></span>
                            Slow Tunnel (576/676)
                          </span>
                        </label>
                      </div>
                    </div>

                    <div class="rounded-md border border-border bg-panel/60 p-3">
                      <div class="text-[10px] uppercase tracking-wide text-muted">Other Overlays</div>
                      <label class="mt-2 flex items-center gap-2 text-[11px] text-muted">
                        <input
                          v-model="store.draft.vegas_show_bb"
                          type="checkbox"
                          :disabled="!isCategorySelected(category.id)"
                        />
                        <span class="inline-flex items-center gap-2">
                          <span class="h-2 w-2 rounded-full bg-indigo-400"></span>
                          HTF Bollinger Bands
                        </span>
                      </label>
                      <label class="mt-2 flex items-center gap-2 text-[11px] text-muted">
                        <input
                          v-model="store.draft.vegas_show_atr"
                          type="checkbox"
                          :disabled="!isCategorySelected(category.id)"
                        />
                        <span class="inline-flex items-center gap-2">
                          <span class="h-2 w-2 rounded-full bg-orange-400"></span>
                          ATR (14) Panel
                        </span>
                      </label>
                      <div class="mt-2 grid gap-2 sm:grid-cols-2">
                        <label class="text-[11px] text-muted">
                          Length
                          <input
                            v-model.number="store.draft.vegas_bb_length"
                            class="mt-1 w-full rounded-md border border-border bg-panel px-2 py-1 text-[11px] text-text"
                            type="number"
                            min="10"
                            max="50"
                            step="1"
                            :disabled="!store.draft.vegas_show_bb || !isCategorySelected(category.id)"
                          />
                        </label>
                        <label class="text-[11px] text-muted">
                          Std Dev
                          <input
                            v-model.number="store.draft.vegas_bb_std"
                            class="mt-1 w-full rounded-md border border-border bg-panel px-2 py-1 text-[11px] text-text"
                            type="number"
                            min="1"
                            max="5"
                            step="0.5"
                            :disabled="!store.draft.vegas_show_bb || !isCategorySelected(category.id)"
                          />
                        </label>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </BaseCard>

        <BaseCard>
          <div class="flex items-center justify-between">
            <span class="text-xs uppercase tracking-wide text-muted">Response Requirements</span>
          </div>
          <textarea
            v-model="store.draft.requirements"
            class="mt-3 h-[28rem] w-full rounded-md border border-border bg-panel p-3 font-mono text-xs text-text"
            placeholder="Define structure and output rules..."
          ></textarea>
        </BaseCard>
      </div>

      <div class="flex min-h-0 flex-col gap-4 overflow-hidden">
        <BaseCard>
          <div class="flex items-center justify-between">
            <span class="text-xs uppercase tracking-wide text-muted">Prompt Builder</span>
            <span v-if="previewTime" class="text-[10px] text-muted">Updated {{ previewTime }}</span>
          </div>
          <div class="mt-3 flex flex-wrap items-center gap-2">
            <button
              class="rounded-md border border-border bg-accent px-3 py-2 text-xs font-medium text-base"
              type="button"
              :disabled="store.isBuildingPrompt"
              @click="openPromptPreviewModal"
            >
              {{ store.isBuildingPrompt ? "Building..." : "Generate Prompt" }}
            </button>
            <button
              class="rounded-md border border-border bg-panel px-3 py-2 text-xs text-muted hover:text-text disabled:opacity-50"
              type="button"
              :disabled="!store.preview"
              @click="copyPrompt"
            >
              Copy
            </button>
          </div>
        </BaseCard>

        <BaseCard class="flex min-h-0 flex-1 flex-col">
          <div class="flex items-center justify-between">
            <span class="text-xs uppercase tracking-wide text-muted">Prompt Preview</span>
          </div>
          <div class="mt-3 flex min-h-0 flex-1 flex-col">
            <div
              v-if="!store.preview"
              class="flex flex-1 items-center justify-center rounded-md border border-dashed border-border bg-panel/40 text-xs text-muted"
            >
              Generate a prompt to preview the output.
            </div>
            <pre
              v-else
              class="flex-1 overflow-y-auto whitespace-pre-wrap rounded-md border border-border bg-panel p-3 font-mono text-[11px] leading-relaxed text-text scrollbar-hidden"
            >{{ store.preview }}</pre>
          </div>
        </BaseCard>
      </div>
    </div>

    <TransitionRoot :show="isSaveModalOpen" as="template">
      <Dialog class="relative z-50" @close="closeSaveModal">
        <TransitionChild
          as="template"
          enter="ease-out duration-200"
          enter-from="opacity-0"
          enter-to="opacity-100"
          leave="ease-in duration-150"
          leave-from="opacity-100"
          leave-to="opacity-0"
        >
          <div class="fixed inset-0 bg-black/50" />
        </TransitionChild>

        <div class="fixed inset-0 flex items-center justify-center p-4">
          <TransitionChild
            as="template"
            enter="ease-out duration-200"
            enter-from="opacity-0 translate-y-4"
            enter-to="opacity-100 translate-y-0"
            leave="ease-in duration-150"
            leave-from="opacity-100 translate-y-0"
            leave-to="opacity-0 translate-y-4"
          >
            <DialogPanel class="w-full max-w-md rounded-lg border border-border bg-surface p-5 shadow-panel">
              <div class="flex items-center justify-between">
                <DialogTitle class="font-display text-base">Save Configuration</DialogTitle>
                <button
                  class="rounded-md border border-border bg-panel px-2 py-1 text-xs text-muted hover:text-text"
                  type="button"
                  @click="closeSaveModal"
                >
                  Close
                </button>
              </div>

              <form class="mt-4 space-y-3" @submit.prevent="submitSaveAs">
                <label class="text-xs text-muted">
                  Name
                  <input
                    ref="saveAsInput"
                    v-model="newConfigName"
                    class="mt-2 w-full rounded-md border border-border bg-panel px-3 py-2 text-sm text-text"
                    type="text"
                    placeholder="Configuration name"
                  />
                </label>

                <p v-if="saveModalError" class="text-xs text-negative">{{ saveModalError }}</p>

                <div class="flex items-center justify-end gap-2">
                  <button
                    class="rounded-md border border-border bg-panel px-3 py-2 text-xs text-muted hover:text-text"
                    type="button"
                    @click="closeSaveModal"
                  >
                    Cancel
                  </button>
                  <button
                    class="rounded-md border border-border bg-accent px-3 py-2 text-xs font-medium text-base"
                    type="submit"
                    :disabled="store.isSavingConfig"
                  >
                    {{ store.isSavingConfig ? "Saving..." : "Save" }}
                  </button>
                </div>
              </form>
            </DialogPanel>
          </TransitionChild>
        </div>
      </Dialog>
    </TransitionRoot>

    <TransitionRoot :show="isPromptPreviewOpen" as="template">
      <Dialog class="relative z-50" @close="closePromptPreviewModal">
        <TransitionChild
          as="template"
          enter="ease-out duration-200"
          enter-from="opacity-0"
          enter-to="opacity-100"
          leave="ease-in duration-150"
          leave-from="opacity-100"
          leave-to="opacity-0"
        >
          <div class="fixed inset-0 bg-black/50" />
        </TransitionChild>

        <div class="fixed inset-0 flex items-center justify-center p-4">
          <TransitionChild
            as="template"
            enter="ease-out duration-200"
            enter-from="opacity-0 translate-y-4"
            enter-to="opacity-100 translate-y-0"
            leave="ease-in duration-150"
            leave-from="opacity-100 translate-y-0"
            leave-to="opacity-0 translate-y-4"
          >
            <DialogPanel class="w-full max-w-lg rounded-lg border border-border bg-surface p-5 shadow-panel">
              <div class="flex items-center justify-between">
                <DialogTitle class="font-display text-base">Prompt Preview</DialogTitle>
                <button
                  class="rounded-md border border-border bg-panel px-2 py-1 text-xs text-muted hover:text-text"
                  type="button"
                  @click="closePromptPreviewModal"
                >
                  Close
                </button>
              </div>

              <div class="mt-4 space-y-3 text-xs text-muted">
                <div v-if="isLoadingEmaCache">Loading EMA cache...</div>

                <div v-else-if="emaCacheResults.length === 0" class="space-y-2">
                  <p>No EMA cache available. Run the EMA scanner to preview a prompt.</p>
                  <button
                    class="rounded-md border border-border bg-accent px-3 py-2 text-xs font-medium text-base"
                    type="button"
                    :disabled="isRunningEmaScan"
                    @click="runEmaScanForPreview"
                  >
                    {{ isRunningEmaScan ? "Running EMA Scan..." : "Run EMA Scan" }}
                  </button>
                  <p v-if="emaCacheError" class="text-negative">{{ emaCacheError }}</p>
                </div>

                <div v-else class="space-y-3">
                  <label class="text-[11px] text-muted">
                    EMA Cache Ticker
                    <select
                      v-model="selectedEmaTicker"
                      class="mt-2 w-full rounded-md border border-border bg-panel px-3 py-2 text-xs text-text"
                    >
                      <option v-for="ticker in emaTickerOptions" :key="ticker" :value="ticker">
                        {{ ticker }}
                      </option>
                    </select>
                  </label>

                  <div v-if="selectedEmaIntervals.length > 0" class="text-[11px] text-muted">
                    Intervals: {{ selectedEmaIntervals.join(", ") }}
                  </div>
                  <div v-if="emaCacheDate" class="text-[11px] text-muted">
                    Cache Date: {{ emaCacheDate }}
                  </div>

                  <div class="flex flex-wrap items-center gap-2">
                    <button
                      class="rounded-md border border-border bg-accent px-3 py-2 text-xs font-medium text-base"
                      type="button"
                      :disabled="store.isBuildingPrompt"
                      @click="handleBuildPromptPreview"
                    >
                      {{ store.isBuildingPrompt ? "Building..." : "Build Prompt" }}
                    </button>
                    <button
                      class="rounded-md border border-border bg-panel px-3 py-2 text-xs text-muted hover:text-text"
                      type="button"
                      :disabled="isRunningEmaScan"
                      @click="runEmaScanForPreview"
                    >
                      {{ isRunningEmaScan ? "Refreshing..." : "Refresh EMA Cache" }}
                    </button>
                  </div>

                  <div v-if="promptPreviewError" class="text-negative">{{ promptPreviewError }}</div>

                  <div v-if="quantMissingList.length > 0" class="space-y-2">
                    <div class="text-negative">
                      Quant data missing for: {{ quantMissingList.join(", ") }}
                    </div>
                    <button
                      class="rounded-md border border-border bg-panel px-3 py-2 text-xs text-muted hover:text-text"
                      type="button"
                      :disabled="isRunningQuantScan"
                      @click="runQuantScanForPreview"
                    >
                      {{ isRunningQuantScan ? "Running Quant Scan..." : "Run Quant Scan" }}
                    </button>
                  </div>
                </div>
              </div>
            </DialogPanel>
          </TransitionChild>
        </div>
      </Dialog>
    </TransitionRoot>

    <TransitionRoot :show="isPreviewOpen" as="template">
      <Dialog class="relative z-50" @close="closePreviewModal">
        <TransitionChild
          as="template"
          enter="ease-out duration-200"
          enter-from="opacity-0"
          enter-to="opacity-100"
          leave="ease-in duration-150"
          leave-from="opacity-100"
          leave-to="opacity-0"
        >
          <div class="fixed inset-0 bg-black/60" />
        </TransitionChild>

        <div class="fixed inset-0 flex items-center justify-center p-4">
          <TransitionChild
            as="template"
            enter="ease-out duration-200"
            enter-from="opacity-0 translate-y-4"
            enter-to="opacity-100 translate-y-0"
            leave="ease-in duration-150"
            leave-from="opacity-100 translate-y-0"
            leave-to="opacity-0 translate-y-4"
          >
            <DialogPanel class="w-full max-w-5xl rounded-lg border border-border bg-surface p-5 shadow-panel">
              <div class="flex items-center justify-between gap-2">
                <DialogTitle class="font-display text-base">Chart Preview</DialogTitle>
                <button
                  class="rounded-md border border-border bg-panel px-2 py-1 text-xs text-muted hover:text-text"
                  type="button"
                  @click="closePreviewModal"
                >
                  Close
                </button>
              </div>

              <div class="mt-4 space-y-3">
                <div v-if="previewState === 'loading'" class="rounded-md border border-border bg-panel/50 p-4 text-xs text-muted">
                  Generating chart preview...
                </div>
                <div v-else-if="previewState === 'error'" class="rounded-md border border-negative/40 bg-negative/10 p-4 text-xs text-negative">
                  {{ previewError || "Preview failed." }}
                </div>
                <div v-else-if="previewState === 'success'" class="space-y-3">
                  <div class="text-[11px] text-muted">
                    {{ selectedChartTicker }} @ {{ previewInterval }} | {{ previewCandles }} candles | EMAs:
                    {{ previewEmaList.length ? previewEmaList.join(", ") : "none" }} | ATR:
                    {{ store.draft.vegas_show_atr ? "on" : "off" }}
                  </div>
                  <div class="overflow-auto rounded-md border border-border bg-panel/30 p-2">
                    <img
                      :src="previewImage"
                      alt="Vegas chart preview"
                      class="h-auto w-full rounded-md"
                    />
                  </div>
                </div>
                <div v-else class="text-xs text-muted">
                  Select Preview on an interval to generate a chart.
                </div>
              </div>
            </DialogPanel>
          </TransitionChild>
        </div>
      </Dialog>
    </TransitionRoot>

    <TransitionRoot :show="isToastOpen" as="template">
      <div class="fixed bottom-4 right-4 z-50">
        <TransitionChild
          as="template"
          enter="ease-out duration-200"
          enter-from="opacity-0 translate-y-2"
          enter-to="opacity-100 translate-y-0"
          leave="ease-in duration-150"
          leave-from="opacity-100 translate-y-0"
          leave-to="opacity-0 translate-y-2"
        >
          <div class="rounded-md border border-border bg-surface px-4 py-2 text-xs text-text shadow-panel">
            {{ toastMessage }}
          </div>
        </TransitionChild>
      </div>
    </TransitionRoot>
  </div>
</template>

<script setup lang="ts">
import {
  Dialog,
  DialogPanel,
  DialogTitle,
  TransitionChild,
  TransitionRoot,
} from "@headlessui/vue";
import {
  computed,
  nextTick,
  onActivated,
  onBeforeUnmount,
  onDeactivated,
  onMounted,
  ref,
  watch,
  watchEffect,
} from "vue";
import BaseBadge from "@/components/BaseBadge.vue";
import BaseCard from "@/components/BaseCard.vue";
import { useAgentStore } from "@/stores/agentStore";
import type { ScannerResult } from "@/types/scanner";

defineOptions({ name: "AgentView" });

const store = useAgentStore();
const leftPanelRef = ref<HTMLElement | null>(null);
const leftPanelScrollTop = ref(0);

const contextCategories = [
  {
    id: "portfolio_overview",
    label: "Portfolio Overview",
    description: "Account value, goal progress, days left, daily target",
    fields: [
      { id: "account_value", label: "Account Value" },
      { id: "final_goal", label: "Final Goal" },
      { id: "goal_progress", label: "Goal Progress" },
      { id: "days_left_for_achieving_goal", label: "Days Left" },
      { id: "daily_growth_target", label: "Daily Growth Target %" },
      { id: "daily_growth_target_dollar_value", label: "Daily Target ($)" },
      { id: "status", label: "Status" },
    ],
  },
  {
    id: "trade_mandate",
    label: "Trade Mandate",
    description: "Exposure limits and target profit on max exposure",
    fields: [
      { id: "max_portfolio_exposure", label: "Max Exposure %" },
      { id: "max_available_margin", label: "Max Available Margin" },
      { id: "target_profit_on_max_exposure", label: "Target Profit %" },
      { id: "status", label: "Status" },
    ],
  },
  {
    id: "account_state",
    label: "Account State",
    description: "Today's PnL, margin status, daily goal progress",
    fields: [
      { id: "realized_pnl_today", label: "Realized PnL Today" },
      { id: "trades_today", label: "Trades Today" },
      { id: "available_margin_left", label: "Available Margin Left" },
      { id: "daily_goal_met", label: "Daily Goal Met" },
      { id: "pnl_gap_usd", label: "PnL Gap to Target" },
      { id: "status", label: "Status" },
    ],
  },
  {
    id: "recent_completed_trades",
    label: "Recent Completed Trades",
    description: "Last 10 closed trades with entry/exit, PnL, duration",
    fields: [
      { id: "recent_completed_trades", label: "Trade List" },
      { id: "total_trades_in_period", label: "Total Trades Count" },
    ],
  },
  {
    id: "chart_snapshots",
    label: "Chart Snapshots",
    description: "Multi-timeframe chart snapshots with EMA, BB, and ATR overlays",
  },
  {
    id: "open_positions",
    label: "Open Positions",
    description: "Current active trades with side, size, entry, PnL, duration",
    fields: [
      { id: "side", label: "Side" },
      { id: "margin_used", label: "Margin Used" },
      { id: "entry", label: "Entry Price" },
      { id: "leverage", label: "Leverage" },
      { id: "stop_loss", label: "Stop Loss" },
      { id: "take_profit", label: "Take Profit" },
      { id: "pnl", label: "PnL" },
      { id: "roe", label: "ROE" },
      { id: "liquidation", label: "Liquidation" },
      { id: "held_for", label: "Held For" },
      { id: "opened_at", label: "Opened At" },
      { id: "peak_roe", label: "Peak ROE" },
      { id: "status", label: "Status" },
    ],
  },
  {
    id: "quantitative_signals",
    label: "Quantitative Signals",
    description: "Flattened quant snapshot signals used by prompt builder",
    fields: [
      { id: "ticker", label: "Ticker" },
      { id: "interval", label: "Interval" },
      { id: "timestamp", label: "Timestamp" },
      { id: "price_current", label: "Price Current" },
      { id: "price_slope", label: "Price Slope" },
      { id: "price_slope_z", label: "Price Slope Z" },
      { id: "oi_current", label: "OI Current" },
      { id: "oi_slope", label: "OI Slope" },
      { id: "oi_slope_z", label: "OI Slope Z" },
      { id: "cvd_current", label: "CVD Current" },
      { id: "cvd_slope", label: "CVD Slope" },
      { id: "cvd_slope_z", label: "CVD Slope Z" },
      { id: "cvd_delta", label: "CVD Delta" },
      { id: "net_depth_usd", label: "Net Depth (USD)" },
      { id: "imbalance_pct", label: "Imbalance %" },
      { id: "obi_ratio", label: "OBI Ratio" },
      { id: "vwap", label: "VWAP" },
      { id: "vwap_distance", label: "VWAP Distance" },
      { id: "atr", label: "ATR" },
      { id: "atr_slope_pct", label: "ATR Slope %" },
      { id: "atr_z_score", label: "ATR Z-Score" },
      { id: "funding_rate", label: "Funding Rate" },
      { id: "funding_mark_price", label: "Funding Mark Price" },
      { id: "institution_netflow", label: "Institution Netflow" },
      { id: "retail_netflow", label: "Retail Netflow" },
      { id: "total_netflow", label: "Total Netflow" },
      { id: "flow_regime", label: "Flow Regime" },
      { id: "dominant_flow", label: "Dominant Flow" },
      { id: "anomalies", label: "Anomalies (Significant)" },
    ],
  },
  {
    id: "what_not_to_do_list",
    label: "What Not To Do List",
    description: "Trading rules and restrictions to avoid common mistakes",
  },
  {
    id: "llm_considerations",
    label: "LLM Considerations",
    description: "Context and watchlist items from the previous automation cycle",
  },
];

const DEFAULT_VEGAS_INTERVALS: string[] = ["30m", "1h", "2h", "4h", "8h", "12h"];

const monitoredIntervals = ref<string[]>([]);
const isLoadingIntervals = ref(false);
const monitoredAssets = ref<string[]>([]);
const isLoadingAssets = ref(false);
const selectedChartTicker = ref("BTC");

const expandedCategories = ref<Record<string, boolean>>({});
const selectAllRef = ref<HTMLInputElement | null>(null);
const isSaveModalOpen = ref(false);
const newConfigName = ref("");
const saveModalError = ref("");
const saveAsInput = ref<HTMLInputElement | null>(null);
type PreviewState = "idle" | "loading" | "success" | "error";

const isPreviewOpen = ref(false);
const previewState = ref<PreviewState>("idle");
const previewImage = ref("");
const previewError = ref("");
const previewInterval = ref("");
const previewCandles = ref(0);
const previewEmaList = ref<number[]>([]);

const isPromptPreviewOpen = ref(false);
const isLoadingEmaCache = ref(false);
const isRunningEmaScan = ref(false);
const isRunningQuantScan = ref(false);
const emaCacheResults = ref<ScannerResult[]>([]);
const emaCacheDate = ref("");
const emaCacheError = ref("");
const selectedEmaTicker = ref("");
const promptPreviewError = ref("");
const quantMissingList = ref<string[]>([]);

const isPreviewLoading = computed(() => previewState.value === "loading");
const isToastOpen = ref(false);
const toastMessage = ref("");
let toastTimer: number | undefined;

const emaTickerOptions = computed(() => emaCacheResults.value.map((item) => item.ticker));

const selectedEmaResult = computed(() =>
  emaCacheResults.value.find((item) => item.ticker === selectedEmaTicker.value),
);

const selectedEmaIntervals = computed(() => {
  const result = selectedEmaResult.value;
  if (!result) return [];
  if (result.chart_data && typeof result.chart_data === "object") {
    return Object.keys(result.chart_data);
  }
  return Array.isArray(result.intervals) ? result.intervals : [];
});

const parseIntervalMinutes = (value: string) => {
  const trimmed = value.trim().toLowerCase();
  if (!trimmed) return Number.POSITIVE_INFINITY;
  const match = trimmed.match(/^(\d+)([mhdw])$/);
  if (!match) return Number.POSITIVE_INFINITY;
  const amount = Number(match[1]);
  if (!Number.isFinite(amount) || amount <= 0) return Number.POSITIVE_INFINITY;
  const unit = match[2];
  const multipliers: Record<string, number> = { m: 1, h: 60, d: 1440, w: 10080 };
  return amount * (multipliers[unit] ?? 1);
};

const vegasIntervals = computed(() => {
  const configIntervals = Object.keys(store.draft.vegas_interval_configs || {});
  const merged = [...monitoredIntervals.value, ...configIntervals];
  const deduped = Array.from(new Set(merged.filter((item) => item && item.trim())));
  if (!deduped.length) return DEFAULT_VEGAS_INTERVALS;
  return [...deduped].sort((a, b) => {
    const diff = parseIntervalMinutes(a) - parseIntervalMinutes(b);
    if (Number.isFinite(diff) && diff !== 0) return diff;
    return a.localeCompare(b);
  });
});

const chartTickerOptions = computed(() => {
  const assets = monitoredAssets.value.filter((item) => item && item.trim());
  return assets.length ? assets : ["BTC"];
});

const vegasIntervalValue = (interval: string) => {
  const value = store.draft.vegas_interval_configs[interval];
  return typeof value === "number" && Number.isFinite(value) ? value : 50;
};

const updateVegasInterval = (interval: string, event: Event) => {
  const rawValue = Number((event.target as HTMLInputElement).value);
  const numeric = Number.isFinite(rawValue) ? rawValue : 50;
  const clamped = Math.min(Math.max(numeric, 30), 200);
  store.draft.vegas_interval_configs = {
    ...store.draft.vegas_interval_configs,
    [interval]: clamped,
  };
};

const syncVegasIntervalConfigs = (intervals: string[]) => {
  if (intervals.length === 0) return;
  const current = store.draft.vegas_interval_configs;
  const next = { ...current };
  let changed = false;
  intervals.forEach((interval) => {
    const value = next[interval];
    const isValid = typeof value === "number" && Number.isFinite(value) && value > 0;
    if (!isValid) {
      next[interval] = 50;
      changed = true;
    }
  });
  if (changed) {
    store.draft.vegas_interval_configs = next;
  }
};

const loadIntervals = async () => {
  if (isLoadingIntervals.value) return;
  isLoadingIntervals.value = true;
  try {
    const response = await fetch("/api/v1/market/monitored-intervals");
    const data = await response.json();
    if (Array.isArray(data?.data)) {
      monitoredIntervals.value = data.data;
    }
  } catch {
    // Ignore interval load failures
  } finally {
    isLoadingIntervals.value = false;
  }
};

const loadAssets = async () => {
  if (isLoadingAssets.value) return;
  isLoadingAssets.value = true;
  try {
    const response = await fetch("/api/v1/market/monitored-assets");
    const data = await response.json();
    if (Array.isArray(data?.data)) {
      monitoredAssets.value = data.data;
      if (!data.data.includes(selectedChartTicker.value) && data.data.length > 0) {
        selectedChartTicker.value = data.data[0];
      }
    }
  } catch {
    // Ignore asset load failures
  } finally {
    isLoadingAssets.value = false;
  }
};

const buildVegasEmaList = () => {
  const emaList: number[] = [];
  if (store.draft.vegas_show_fast_tunnel) {
    emaList.push(36, 44);
  }
  if (store.draft.vegas_show_medium_tunnel) {
    emaList.push(144, 169);
  }
  if (store.draft.vegas_show_slow_tunnel) {
    emaList.push(576, 676);
  }
  return emaList;
};

const closePreviewModal = () => {
  isPreviewOpen.value = false;
  previewState.value = "idle";
  previewImage.value = "";
  previewError.value = "";
};

const showToast = (message: string) => {
  toastMessage.value = message;
  isToastOpen.value = true;
  if (toastTimer) {
    window.clearTimeout(toastTimer);
  }
  toastTimer = window.setTimeout(() => {
    isToastOpen.value = false;
  }, 2200);
};

const closePromptPreviewModal = () => {
  isPromptPreviewOpen.value = false;
  promptPreviewError.value = "";
  quantMissingList.value = [];
};

const loadEmaCache = async () => {
  if (isLoadingEmaCache.value) return;
  isLoadingEmaCache.value = true;
  emaCacheError.value = "";
  try {
    const response = await fetch("/api/v1/scanner/ema/latest");
    const data = await response.json();
    const payload = data?.data;
    if (!response.ok || !payload) {
      throw new Error(data?.error?.message || "Failed to load EMA cache.");
    }
    const results = Array.isArray(payload.results) ? payload.results : [];
    emaCacheResults.value = results;
    emaCacheDate.value = payload.date || "";
    if (!selectedEmaTicker.value && results.length > 0) {
      selectedEmaTicker.value = results[0].ticker;
    }
  } catch (error) {
    emaCacheResults.value = [];
    emaCacheDate.value = "";
    emaCacheError.value = error instanceof Error ? error.message : "Failed to load EMA cache.";
  } finally {
    isLoadingEmaCache.value = false;
  }
};

const openPromptPreviewModal = async () => {
  isPromptPreviewOpen.value = true;
  promptPreviewError.value = "";
  quantMissingList.value = [];
  await loadEmaCache();
};

const runEmaScanForPreview = async () => {
  if (isRunningEmaScan.value) return;
  isRunningEmaScan.value = true;
  emaCacheError.value = "";
  try {
    const response = await fetch("/api/v1/scanner/ema/run", { method: "POST" });
    if (!response.ok) {
      const data = await response.json();
      throw new Error(data?.error?.message || "EMA scan failed.");
    }
    await loadEmaCache();
  } catch (error) {
    emaCacheError.value = error instanceof Error ? error.message : "EMA scan failed.";
  } finally {
    isRunningEmaScan.value = false;
  }
};

const runQuantScanForPreview = async () => {
  if (isRunningQuantScan.value) return;
  isRunningQuantScan.value = true;
  promptPreviewError.value = "";
  try {
    const response = await fetch("/api/v1/scanner/quant/run", { method: "POST" });
    if (!response.ok) {
      const data = await response.json();
      throw new Error(data?.error?.message || "Quant scan failed.");
    }
    if (selectedEmaTicker.value) {
      await handleBuildPromptPreview();
    }
  } catch (error) {
    promptPreviewError.value = error instanceof Error ? error.message : "Quant scan failed.";
  } finally {
    isRunningQuantScan.value = false;
  }
};

const handleBuildPromptPreview = async () => {
  if (!selectedEmaTicker.value) {
    promptPreviewError.value = "Select a ticker to preview.";
    return;
  }
  promptPreviewError.value = "";
  quantMissingList.value = [];
  const result = await store.buildContextPrompt(selectedEmaTicker.value);
  if (result?.ok) {
    closePromptPreviewModal();
    return;
  }
  if (result?.errorCode === "quant_snapshot_missing") {
    const missing = result.errorDetails?.missing;
    quantMissingList.value = Array.isArray(missing) ? missing : [];
    return;
  }
  promptPreviewError.value = store.contextError || "Prompt preview failed.";
};

const previewVegasChart = async (interval: string) => {
  if (!isCategorySelected("chart_snapshots")) return;
  previewInterval.value = interval;
  previewCandles.value = vegasIntervalValue(interval);
  previewEmaList.value = buildVegasEmaList();
  previewError.value = "";
  previewImage.value = "";
  previewState.value = "loading";
  isPreviewOpen.value = true;

  try {
    const response = await fetch("/api/v1/agent/preview-chart", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ticker: selectedChartTicker.value || "BTC",
        interval,
        candles: previewCandles.value,
        emas: previewEmaList.value,
        show_bb: store.draft.vegas_show_bb,
        show_atr: store.draft.vegas_show_atr,
        bb_length: store.draft.vegas_bb_length,
        bb_std: store.draft.vegas_bb_std,
      }),
    });
    const data = await response.json();
    const chartBase64 = data?.data?.chart_base64;
    if (!response.ok || !chartBase64) {
      throw new Error(data?.error?.message || "Preview failed.");
    }
    previewImage.value = `data:image/png;base64,${chartBase64}`;
    previewState.value = "success";
  } catch (error) {
    previewError.value = error instanceof Error ? error.message : "Preview failed.";
    previewState.value = "error";
  }
};

const selectedConfigId = computed({
  get: () => (store.activeConfigId !== null ? String(store.activeConfigId) : ""),
  set: (value) => {
    const id = value ? Number(value) : null;
    store.setActiveConfig(Number.isFinite(id as number) ? (id as number) : null);
  },
});

const allSelected = computed(() =>
  contextCategories.every((category) => store.draft.data_selections.includes(category.id)),
);
const someSelected = computed(() =>
  contextCategories.some((category) => store.draft.data_selections.includes(category.id)),
);

const toggleAll = () => {
  store.draft.data_selections = allSelected.value
    ? []
    : contextCategories.map((option) => option.id);
};

const isCategoryExpanded = (id: string) => Boolean(expandedCategories.value[id]);

const toggleCategory = (id: string) => {
  expandedCategories.value = {
    ...expandedCategories.value,
    [id]: !expandedCategories.value[id],
  };
};

const isCategorySelected = (id: string) => store.draft.data_selections.includes(id);

const isFieldSelected = (categoryId: string, fieldId: string) => {
  const selections = store.draft.field_selections[categoryId];
  if (!selections || selections.length === 0) return true;
  return selections.includes(fieldId);
};

const updateFieldSelection = (categoryId: string, fieldId: string, checked: boolean) => {
  const category = contextCategories.find((item) => item.id === categoryId);
  if (!category || !category.fields) return;
  const allFields = category.fields.map((field) => field.id);
  const current = store.draft.field_selections[categoryId];
  const next = current && current.length > 0 ? [...current] : [...allFields];
  if (checked) {
    if (!next.includes(fieldId)) next.push(fieldId);
  } else {
    const index = next.indexOf(fieldId);
    if (index >= 0) next.splice(index, 1);
  }
  store.draft.field_selections = { ...store.draft.field_selections, [categoryId]: next };
};

const previewTime = computed(() => {
  if (!store.previewTimestamp) return "";
  const parsed = new Date(store.previewTimestamp);
  if (Number.isNaN(parsed.getTime())) return "";
  return parsed.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
});

const openSaveModal = async () => {
  saveModalError.value = "";
  newConfigName.value = "";
  isSaveModalOpen.value = true;
  await nextTick();
  saveAsInput.value?.focus();
};

const closeSaveModal = () => {
  isSaveModalOpen.value = false;
  saveModalError.value = "";
  newConfigName.value = "";
};

const handleSave = async () => {
  await store.saveActiveConfig();
  if (!store.contextError) {
    showToast("Configuration saved.");
  }
};

const submitSaveAs = async () => {
  const name = newConfigName.value.trim();
  if (!name) {
    saveModalError.value = "Name is required.";
    return;
  }
  await store.createConfig(name);
  if (store.contextError) {
    saveModalError.value = store.contextError;
    return;
  }
  closeSaveModal();
  showToast(`Saved as ${name}.`);
};

const handleDelete = async () => {
  if (!store.activeConfig || store.activeConfig.is_default) return;
  const confirmed = window.confirm(`Delete configuration "${store.activeConfig.name}"?`);
  if (!confirmed) return;
  await store.deleteActiveConfig();
};

const copyPrompt = async () => {
  if (!store.preview) return;
  try {
    await navigator.clipboard.writeText(store.preview);
  } catch {
    // Ignore copy failures for now
  }
};

watchEffect(() => {
  if (!selectAllRef.value) return;
  selectAllRef.value.indeterminate = someSelected.value && !allSelected.value;
});

watch(
  [vegasIntervals, () => store.activeConfigId],
  ([intervals]) => {
    syncVegasIntervalConfigs(intervals);
  },
  { immediate: true },
);

onMounted(() => {
  if (!store.contextConfigs.length) {
    store.loadContextConfigs();
  }
  loadIntervals();
  loadAssets();
});

onActivated(() => {
  void nextTick(() => {
    if (leftPanelRef.value) {
      leftPanelRef.value.scrollTop = leftPanelScrollTop.value;
    }
  });
});

onDeactivated(() => {
  if (leftPanelRef.value) {
    leftPanelScrollTop.value = leftPanelRef.value.scrollTop;
  }
});

onBeforeUnmount(() => {
  if (toastTimer) {
    window.clearTimeout(toastTimer);
  }
});
</script>
