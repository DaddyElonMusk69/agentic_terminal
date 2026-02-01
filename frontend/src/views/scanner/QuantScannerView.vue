<template>
  <div class="flex h-full min-h-0 flex-1 flex-col gap-3 overflow-hidden">
    <div
      class="grid min-h-0 flex-1 gap-4 overflow-hidden xl:grid-cols-[280px_minmax(0,0.6fr)_minmax(0,1.7fr)] xl:grid-rows-[auto_minmax(0,1fr)]"
    >
      <div class="col-span-full flex flex-wrap items-center justify-between gap-2 xl:col-span-2">
        <h1 class="font-display text-xl">Quant Scanner</h1>
        <BaseBadge>
          {{ store.isConnected ? "Socket: Live" : "Socket: Idle" }}
        </BaseBadge>
      </div>

      <aside class="flex h-full min-h-0 flex-col gap-3 overflow-hidden xl:row-start-2">
        <div class="flex flex-col gap-3">
          <BaseCard>
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <span
                  class="h-2 w-2 rounded-full"
                  :class="store.isRunning ? 'bg-warning' : store.isConnected ? 'bg-accent' : 'bg-muted'"
                ></span>
                <span class="font-display text-sm">Market Scanner</span>
              </div>
              <span
                class="text-[10px] uppercase tracking-wide"
                :class="store.isRunning ? 'text-warning' : 'text-muted'"
              >
                {{ store.isRunning ? "Running" : "Idle" }}
              </span>
            </div>
            <p class="mt-2 text-xs text-muted">
              OI/CVD quant scan across all intervals.
            </p>
          </BaseCard>

          <button
            class="w-full rounded-md border border-border px-3 py-2 text-sm font-medium transition-colors duration-200 disabled:cursor-not-allowed disabled:opacity-70"
            :class="automationIsRunning || !automationStateReady ? 'bg-panel text-muted' : 'bg-accent text-base'"
            type="button"
            :disabled="isScanDisabled"
            @click="handleRun"
          >
            <Transition name="fade" mode="out-in">
              <span :key="scanButtonLabel">{{ scanButtonLabel }}</span>
            </Transition>
          </button>
        </div>

        <div
          ref="leftPanelRef"
          class="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto pr-1 scrollbar-hidden"
        >
          <BaseCard>
            <div class="text-xs uppercase tracking-wide text-muted">Monitored Assets</div>
            <div class="mt-3 flex flex-wrap gap-2">
            <span
              v-for="asset in monitoredAssets"
              :key="asset"
              class="rounded-full border border-border px-2 py-1 text-[11px] text-muted"
            >
              {{ asset }}
            </span>
            <span v-if="monitoredAssets.length === 0" class="text-[11px] text-muted">
              No assets configured.
            </span>
          </div>
          <p class="mt-2 text-[11px] text-muted">
            Manage assets in Settings > Dynamic Assets.
          </p>
        </BaseCard>

        <Disclosure v-for="section in configSections" :key="section.key" v-slot="{ open }">
          <div class="rounded-lg border border-border bg-surface">
            <DisclosureButton class="flex w-full items-center justify-between px-4 py-3">
              <span class="font-display text-sm text-text">{{ section.label }}</span>
              <span class="text-xs text-muted">{{ open ? "Hide" : "Show" }}</span>
            </DisclosureButton>
            <DisclosurePanel class="border-t border-border px-4 py-4">
              <div class="space-y-4">
                <div
                  v-for="item in section.items"
                  :key="item.key"
                  class="space-y-2"
                >
                  <div class="flex items-center justify-between">
                    <span class="text-xs text-muted">{{ item.label }}</span>
                    <span class="text-xs text-accent">
                      {{ item.display(item.value) }}
                    </span>
                  </div>
                  <input
                    v-if="item.type === 'range'"
                    v-model.number="item.value"
                    class="w-full"
                    type="range"
                    :min="item.min"
                    :max="item.max"
                    :step="item.step"
                  />
                  <label v-else class="flex items-center justify-between text-xs text-muted">
                    <span>{{ item.label }}</span>
                    <input v-model="item.value" type="checkbox" />
                  </label>
                  <p class="text-[11px] text-muted">{{ item.hint }}</p>
                </div>
              </div>
            </DisclosurePanel>
          </div>
        </Disclosure>
        </div>
      </aside>

      <section class="flex h-full min-h-0 flex-col overflow-hidden xl:row-start-2">
        <BaseCard class="flex min-h-0 flex-1 flex-col">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div class="flex flex-wrap items-center gap-2">
              <span class="font-display text-sm">Scanner Log</span>
            </div>
            <div class="flex items-center gap-2 text-[11px] text-muted">
              <select
                v-model="logFilter"
                class="rounded-md border border-border bg-panel px-2 py-1 text-[11px] text-muted"
              >
                <option value="all">All</option>
                <option value="signal">Signal</option>
                <option value="info">Info</option>
                <option value="warning">Warning</option>
                <option value="error">Error</option>
                <option value="success">Success</option>
              </select>
              <button
                class="rounded-md border border-border bg-panel px-2 py-1 text-[11px] text-muted"
                type="button"
                @click="store.clearLogs"
              >
                Clear
              </button>
            </div>
          </div>
          <div
            ref="logListRef"
            class="mt-3 min-h-0 flex-1 space-y-1 overflow-y-auto pr-1 text-xs scrollbar-hidden"
            @scroll="handleLogScroll"
          >
            <div v-for="(log, idx) in filteredLogs" :key="idx" :class="logEntryClass(log)">
              {{ log.message }}
            </div>
            <p v-if="filteredLogs.length === 0" class="text-muted">No logs yet.</p>
          </div>
        </BaseCard>
      </section>

      <aside class="flex h-full min-h-0 flex-col gap-3 overflow-hidden xl:row-span-2 xl:row-start-1">
        <div class="space-y-2">
          <div class="flex items-center justify-between gap-3">
            <div>
              <h2 class="font-display text-sm uppercase tracking-wide text-muted">
                Active Opportunities
              </h2>
            </div>
            <button
              class="rounded-md border border-border bg-panel px-2 py-1 text-[11px] text-muted"
              type="button"
              :disabled="activeSignals.length === 0"
              @click="openHistoryModal"
            >
              Signal History
            </button>
          </div>

          <div class="flex flex-wrap items-center justify-between gap-2 text-[10px] uppercase tracking-wide">
            <span class="text-muted">{{ sentiment.label }}</span>
            <div class="flex items-center gap-2">
              <span class="text-positive">Bull {{ sentiment.bullCount }}</span>
              <span class="text-negative">Bear {{ sentiment.bearCount }}</span>
            </div>
          </div>
          <div class="h-2 w-full overflow-hidden rounded-full bg-border/60">
            <div class="flex h-full w-full">
              <div class="h-full bg-positive" :style="{ width: `${sentiment.bullPercent}%` }"></div>
              <div class="h-full bg-negative" :style="{ width: `${sentiment.bearPercent}%` }"></div>
            </div>
          </div>
        </div>

        <div class="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto pr-1 scrollbar-hidden">
          <div
            v-for="group in groupedOpportunities"
            :key="group.symbol"
            class="rounded-lg border border-border bg-surface shadow-panel"
            :class="groupBorderClass(group.status)"
          >
            <div
              class="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3"
              :class="groupHeaderClass(group.status)"
            >
              <div class="flex flex-wrap items-center gap-3">
                <span class="font-display text-base text-text">{{ group.symbol }}</span>
                <span class="h-2 w-2 rounded-full" :class="groupStatusDotClass(group.status)"></span>
                <span
                  class="rounded-md border border-border px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted"
                >
                  {{ group.activeCount }} Active
                </span>
                <span
                  class="rounded-md border border-border px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted"
                >
                  {{ group.signals.length }} TF
                </span>
              </div>
              <div class="flex items-center gap-2 text-[11px] uppercase tracking-wide">
                <span class="rounded-md border px-2 py-0.5" :class="groupStatusBadgeClass(group.status)">
                  {{ groupStatusLabel(group.status) }}
                </span>
              </div>
            </div>

            <div class="p-4" :class="signalGridClass(group.signals.length)">
              <div
                v-for="signal in group.signals"
                :key="`${group.symbol}-${signal.interval || '15m'}`"
                class="rounded-md border border-border/70 bg-panel/60 p-4"
                :class="signalPanelClass(signal)"
              >
                <div class="flex flex-wrap items-start justify-between gap-3">
                  <div class="space-y-1">
                    <div class="flex flex-wrap items-center gap-2">
                      <span
                        class="rounded-md border px-2 py-0.5 text-[10px] uppercase tracking-wide"
                        :class="signalTonePillClass(signal)"
                      >
                        {{ signal.interval || "15m" }}
                      </span>
                      <span
                        class="rounded-md border px-2 py-0.5 text-[10px] uppercase tracking-wide"
                        :class="signalDirectionBadgeClass(signal)"
                      >
                        {{ signalDirectionLabel(signal) }}
                      </span>
                      <span class="text-xs font-display" :class="signalToneTextClass(signal)">
                        {{ formatSignalName(signal) }}
                      </span>
                    </div>
                    <div class="flex flex-wrap items-center gap-2 text-[10px] uppercase tracking-wide text-muted">
                      <span
                        v-if="signal.signal_metadata?.category"
                        class="rounded-md border border-border px-2 py-0.5"
                      >
                        {{ signal.signal_metadata.category }}
                      </span>
                      <span
                        v-if="signal.signal_metadata?.verdict"
                        class="rounded-md border border-border px-2 py-0.5"
                      >
                        {{ signal.signal_metadata.verdict }}
                      </span>
                    </div>
                  </div>
                  <div class="text-right text-[11px] text-muted">
                    <div class="text-[10px] uppercase tracking-wide">Snapshot</div>
                    <div class="font-mono text-sm" :class="signalToneTextClass(signal)">
                      {{ formatUsd(signal.current_price ?? signal.entry_price) }}
                    </div>
                    <div class="text-[10px] text-muted">
                      OI {{ formatUsdCompact(signal.current_oi, 0) }} | CVD
                      {{ formatCompact(signal.cvd_current, 0) }}
                    </div>
                  </div>
                </div>

                <div class="mt-3 space-y-3">
                  <div
                    v-if="contextChips(signal).length > 0"
                    class="rounded-md border border-border bg-surface/70"
                  >
                    <div class="px-3 py-2 text-[10px] uppercase tracking-wide text-muted">Highlights</div>
                    <div class="flex flex-wrap gap-2 px-3 pb-2">
                      <div
                        v-for="chip in contextChips(signal)"
                        :key="chip.label"
                        class="rounded-full border border-border/60 px-2 py-1 text-[10px] uppercase tracking-wide"
                        :class="chipToneClass(chip.tone)"
                      >
                        <span class="text-muted">{{ chip.label }}</span>
                        <span class="ml-1 text-xs">{{ chip.value }}</span>
                      </div>
                    </div>
                  </div>

                  <div class="rounded-md border border-border bg-surface/70">
                    <div class="flex items-center justify-between border-b border-border/60 px-3 py-2">
                      <div class="text-[10px] uppercase tracking-wide text-muted">Snapshot Overview</div>
                      <div class="text-[10px] text-muted">Updated {{ formatDateTime(signal.last_updated) }}</div>
                    </div>
                    <div class="grid grid-cols-2 divide-x divide-y divide-border/60 bg-panel/30 sm:grid-cols-3 lg:grid-cols-4">
                      <div v-for="stat in coreStats(signal)" :key="stat.key" class="px-3 py-2">
                        <div class="text-[9px] uppercase tracking-wide text-muted">{{ stat.label }}</div>
                        <div class="font-mono text-xs" :class="statToneClass(stat.tone)">
                          {{ stat.value }}
                        </div>
                      </div>
                    </div>
                  </div>

                  <div class="rounded-md border border-border bg-surface/70">
                    <div class="border-b border-border/60 px-3 py-2 text-[10px] uppercase tracking-wide text-muted">
                      Momentum
                    </div>
                    <div class="grid grid-cols-2 divide-x divide-y divide-border/60 bg-panel/30 sm:grid-cols-3 lg:grid-cols-6">
                      <div v-for="stat in slopeStats(signal)" :key="stat.key" class="px-3 py-2">
                        <div class="text-[9px] uppercase tracking-wide text-muted">{{ stat.label }}</div>
                        <div class="font-mono text-xs" :class="statToneClass(stat.tone)">
                          {{ stat.value }}
                        </div>
                      </div>
                    </div>
                  </div>

                  <div class="rounded-md border border-border bg-surface/70">
                    <div class="border-b border-border/60 px-3 py-2 text-[10px] uppercase tracking-wide text-muted">
                      Order Book Depth
                    </div>
                    <div class="grid grid-cols-2 divide-x divide-y divide-border/60 bg-panel/30 sm:grid-cols-3 lg:grid-cols-4">
                      <div v-for="stat in depthStats(signal)" :key="stat.key" class="px-3 py-2">
                        <div class="text-[9px] uppercase tracking-wide text-muted">{{ stat.label }}</div>
                        <div class="font-mono text-xs" :class="statToneClass(stat.tone)">
                          {{ stat.value }}
                        </div>
                      </div>
                    </div>
                  </div>

                  <div class="rounded-md border border-border bg-surface/70">
                    <div class="border-b border-border/60 px-3 py-2 text-[10px] uppercase tracking-wide text-muted">
                      Market Context
                    </div>
                    <div class="grid grid-cols-2 divide-x divide-y divide-border/60 bg-panel/30 sm:grid-cols-3 lg:grid-cols-4">
                      <div v-for="stat in marketContextStats(signal)" :key="stat.key" class="px-3 py-2">
                        <div class="text-[9px] uppercase tracking-wide text-muted">{{ stat.label }}</div>
                        <div class="font-mono text-xs" :class="statToneClass(stat.tone)">
                          {{ stat.value }}
                        </div>
                      </div>
                    </div>
                  </div>

                  <div
                    v-if="anomalyCards(signal).length > 0"
                    class="rounded-md border border-border bg-surface/70"
                  >
                    <div class="border-b border-border/60 px-3 py-2 text-[10px] uppercase tracking-wide text-muted">
                      Significant Anomalies
                    </div>
                    <div class="grid grid-cols-1 divide-y divide-border/60 bg-panel/30 sm:grid-cols-3 sm:divide-x sm:divide-y-0">
                      <div v-for="card in anomalyCards(signal)" :key="card.key" class="px-3 py-2">
                        <div class="text-[9px] uppercase tracking-wide text-muted">{{ card.label }}</div>
                        <div class="mt-1 grid grid-cols-[72px_1fr] gap-y-1 text-[10px] text-muted">
                          <span>Type</span>
                          <span class="font-mono text-xs text-text">
                            {{ formatText(card.data?.anomaly_type) }}
                          </span>
                          <span>Z</span>
                          <span class="font-mono text-xs" :class="statToneClass(toneFromNumber(card.data?.z_score))">
                            {{ formatNumber(card.data?.z_score, 2) }}
                          </span>
                          <span>Magnitude</span>
                          <span class="font-mono text-xs">
                            {{ formatPercent(card.data?.magnitude_pct, 2) }}
                          </span>
                          <span>Current</span>
                          <span class="font-mono text-xs">
                            {{ formatCompact(card.data?.current_value, 2) }}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                <div v-if="signalActions(signal)" class="mt-3 grid grid-cols-1 gap-2 text-[11px] sm:grid-cols-3">
                  <div class="rounded-md border border-border bg-surface/70 px-2 py-2">
                    <div class="text-[10px] uppercase tracking-wide text-muted">Flat</div>
                    <div class="mt-1 text-xs text-text">
                      {{ signalActions(signal)?.flat?.action || "--" }}
                    </div>
                    <div class="text-[10px] text-muted">
                      {{ signalActions(signal)?.flat?.detail || "" }}
                    </div>
                  </div>
                  <div class="rounded-md border border-border bg-surface/70 px-2 py-2">
                    <div class="text-[10px] uppercase tracking-wide text-muted">Long</div>
                    <div class="mt-1 text-xs text-text">
                      {{ signalActions(signal)?.long?.action || "--" }}
                    </div>
                    <div class="text-[10px] text-muted">
                      {{ signalActions(signal)?.long?.detail || "" }}
                    </div>
                  </div>
                  <div class="rounded-md border border-border bg-surface/70 px-2 py-2">
                    <div class="text-[10px] uppercase tracking-wide text-muted">Short</div>
                    <div class="mt-1 text-xs text-text">
                      {{ signalActions(signal)?.short?.action || "--" }}
                    </div>
                    <div class="text-[10px] text-muted">
                      {{ signalActions(signal)?.short?.detail || "" }}
                    </div>
                  </div>
                </div>

                <p
                  v-if="signalInterpretation(signal)"
                  class="mt-3 text-[11px] text-muted"
                  :title="signalInterpretation(signal) || ''"
                >
                  {{ signalInterpretation(signal) }}
                </p>
              </div>
            </div>
          </div>

          <BaseEmptyState
            v-if="groupedOpportunities.length === 0"
            title="No active signals"
            subtitle="Signals will appear as the scanner runs."
          />
        </div>
      </aside>
    </div>

    <TransitionRoot :show="showHistoryModal" as="template">
      <Dialog class="relative z-50" @close="closeHistoryModal">
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
            <DialogPanel
              class="w-full max-w-3xl rounded-lg border border-border bg-surface p-6 shadow-panel"
            >
              <div class="flex items-center justify-between">
                <DialogTitle class="font-display text-base">Signal History</DialogTitle>
                <button
                  class="rounded-md border border-border bg-panel px-2 py-1 text-xs text-muted"
                  type="button"
                  @click="closeHistoryModal"
                >
                  Close
                </button>
              </div>

              <div class="mt-4">
                <label class="text-xs uppercase tracking-wide text-muted">
                  Select Signal
                </label>
                <select
                  class="mt-2 w-full rounded-md border border-border bg-panel px-3 py-2 text-sm text-text"
                  :disabled="historyOptions.length === 0"
                  :value="selectedHistoryKey || ''"
                  @change="handleHistorySelect"
                >
                  <option v-if="historyOptions.length === 0" value="">
                    No active signals
                  </option>
                  <option
                    v-for="option in historyOptions"
                    :key="option.key"
                    :value="option.key"
                  >
                    {{ option.label }}
                  </option>
                </select>
              </div>

              <div
                class="mt-4 max-h-[60vh] space-y-3 overflow-y-auto rounded-md border border-border bg-panel p-4 text-sm scrollbar-hidden"
              >
                <div v-if="historyLoading" class="text-xs text-muted">
                  Loading history...
                </div>
                <div v-else-if="historyError" class="text-xs text-negative">
                  {{ historyError }}
                </div>
                <div v-else-if="historyEntries.length === 0" class="text-xs text-muted">
                  No history available.
                </div>
                <div
                  v-for="(entry, idx) in historyEntries"
                  :key="`${entry.timestamp}-${idx}`"
                  class="rounded-md border border-border bg-surface px-3 py-2"
                >
                  <div class="flex items-center justify-between">
                    <div class="font-display text-sm text-text">
                      {{ entry.signal_type || "Signal" }}
                      <span v-if="entry.direction" class="text-xs text-muted">
                        · {{ entry.direction }}
                      </span>
                    </div>
                    <span class="text-[11px] text-muted">
                      {{ formatTimestamp(entry.timestamp) }}
                    </span>
                  </div>
                  <div class="mt-2 flex flex-wrap gap-2 text-[10px] uppercase tracking-wide text-muted">
                    <span v-if="entry.category" class="rounded-full border border-border px-2 py-0.5">
                      {{ entry.category }}
                    </span>
                    <span v-if="entry.is_flip" class="rounded-full border border-border px-2 py-0.5">
                      Flip
                    </span>
                    <span v-if="entry.is_exit" class="rounded-full border border-border px-2 py-0.5">
                      Exit
                    </span>
                    <span v-if="entry.from_signal" class="rounded-full border border-border px-2 py-0.5">
                      From {{ entry.from_signal }}
                    </span>
                  </div>
                </div>
              </div>
            </DialogPanel>
          </TransitionChild>
        </div>
      </Dialog>
    </TransitionRoot>
  </div>
</template>

<script setup lang="ts">
import {
  computed,
  nextTick,
  onActivated,
  onBeforeUnmount,
  onDeactivated,
  onMounted,
  ref,
  watch,
} from "vue";
import {
  Dialog,
  DialogPanel,
  DialogTitle,
  Disclosure,
  DisclosureButton,
  DisclosurePanel,
  TransitionChild,
  TransitionRoot,
} from "@headlessui/vue";
import BaseBadge from "@/components/BaseBadge.vue";
import BaseCard from "@/components/BaseCard.vue";
import BaseEmptyState from "@/components/BaseEmptyState.vue";
import { useScannerQuantStore } from "@/stores/scannerQuantStore";
import type { AnomalyContextFactor, QuantSignal } from "@/types/quant";
import { readMarketCache, subscribeMarketCache } from "@/services/settingsCache";
import type { MarketCacheData } from "@/services/settingsCache";

defineOptions({ name: "QuantScannerView" });

type HistoryEntry = {
  timestamp: string;
  signal_type?: string;
  direction?: string;
  category?: string;
  is_flip?: boolean;
  is_exit?: boolean;
  from_signal?: string;
};

type HistoryOption = {
  key: string;
  symbol: string;
  interval?: string;
  label: string;
};

type ConfigItem = {
  key: string;
  label: string;
  type: "range" | "toggle";
  value: number | boolean;
  min?: number;
  max?: number;
  step?: number;
  hint: string;
  display: (value: number | boolean) => string;
};

type ConfigSection = {
  key: string;
  label: string;
  items: ConfigItem[];
};

type GroupStatus = "long" | "short" | "mixed" | "flat";

type OpportunityGroup = {
  symbol: string;
  signals: QuantSignal[];
  status: GroupStatus;
  activeCount: number;
};

type ContextChip = {
  label: string;
  value: string;
  tone: "accent" | "positive" | "negative" | "warning" | "muted";
};

type StatTone = "accent" | "positive" | "negative" | "warning" | "muted";

type StatItem = {
  key: string;
  label: string;
  value: string;
  tone?: StatTone;
};

type AnomalyCard = {
  key: string;
  label: string;
  data?: AnomalyContextFactor;
};

const store = useScannerQuantStore();
const automationIsRunning = ref(false);
const automationStateReady = ref(false);
let automationPollTimer: ReturnType<typeof setInterval> | null = null;
const leftPanelRef = ref<HTMLElement | null>(null);
const leftPanelScrollTop = ref(0);
let unsubscribeMarketCache: (() => void) | null = null;
const showHistoryModal = ref(false);
const historyEntries = ref<HistoryEntry[]>([]);
const historyLoading = ref(false);
const historyError = ref<string | null>(null);
const selectedHistoryKey = ref<string | null>(null);
const logFilter = ref("all");
const logListRef = ref<HTMLElement | null>(null);
const logAutoScroll = ref(true);

const timeframeOrder = [
  "1m",
  "3m",
  "5m",
  "15m",
  "30m",
  "1h",
  "2h",
  "4h",
  "6h",
  "8h",
  "12h",
  "1d",
  "3d",
  "1w",
];

const normalizeDirection = (value?: string): "LONG" | "SHORT" | "NEUTRAL" => {
  if (!value) return "NEUTRAL";
  const normalized = value.toUpperCase();
  if (normalized === "LONG" || normalized === "SHORT") return normalized;
  return "NEUTRAL";
};

const inferDirectionFromType = (signalType?: string): "LONG" | "SHORT" | "NEUTRAL" => {
  if (!signalType) return "NEUTRAL";
  const value = signalType.toLowerCase();
  if (value.includes("bull") || value.includes("long")) return "LONG";
  if (value.includes("bear") || value.includes("short")) return "SHORT";
  if (value.includes("neutral")) return "NEUTRAL";
  return "NEUTRAL";
};

const getSignalDirection = (signal: QuantSignal): "LONG" | "SHORT" | "NEUTRAL" => {
  const direction = normalizeDirection(signal.signal_metadata?.direction);
  if (direction === "LONG" || direction === "SHORT") return direction;
  const inferred = inferDirectionFromType(signal.signal_type);
  return inferred;
};

const isNeutralSignal = (signal: QuantSignal) => getSignalDirection(signal) === "NEUTRAL";

const getTimeframeRank = (interval?: string) => {
  if (!interval) return 999;
  const index = timeframeOrder.indexOf(interval);
  return index === -1 ? 999 : index;
};

const activeSignals = computed(() => Object.values(store.opportunities) as QuantSignal[]);
const groupedOpportunities = computed<OpportunityGroup[]>(() => {
  const grouped: Record<string, QuantSignal[]> = {};
  activeSignals.value.forEach((signal) => {
    if (!signal.symbol) return;
    if (!grouped[signal.symbol]) grouped[signal.symbol] = [];
    grouped[signal.symbol].push(signal);
  });

  const groups = Object.entries(grouped).map(([symbol, signals]) => {
    const ordered = [...signals].sort((a, b) => {
      const aNeutral = isNeutralSignal(a);
      const bNeutral = isNeutralSignal(b);
      if (aNeutral !== bNeutral) return aNeutral ? 1 : -1;
      return getTimeframeRank(a.interval) - getTimeframeRank(b.interval);
    });

    const status = getGroupStatus(ordered);
    const activeCount = ordered.filter((signal) => !isNeutralSignal(signal)).length;
    return { symbol, signals: ordered, status, activeCount };
  });

  return groups.sort((a, b) => {
    const aNeutral = a.activeCount === 0;
    const bNeutral = b.activeCount === 0;
    if (aNeutral !== bNeutral) return aNeutral ? 1 : -1;
    return a.symbol.localeCompare(b.symbol);
  });
});

const sentiment = computed(() => {
  let bullCount = 0;
  let bearCount = 0;

  activeSignals.value.forEach((signal) => {
    const direction = getSignalDirection(signal);
    if (direction === "LONG") bullCount += 1;
    if (direction === "SHORT") bearCount += 1;
  });

  const total = bullCount + bearCount;
  let bullPercent = 50;
  let bearPercent = 50;
  let label = "Neutral";

  if (total > 0) {
    bullPercent = (bullCount / total) * 100;
    bearPercent = 100 - bullPercent;
    if (bullPercent > 60) {
      label = `${Math.round(bullPercent)}% Bullish`;
    } else if (bearPercent > 60) {
      label = `${Math.round(bearPercent)}% Bearish`;
    }
  }

  return {
    bullCount,
    bearCount,
    bullPercent,
    bearPercent,
    label,
  };
});

const monitoredAssets = computed(() => store.assets);

const applyMarketAssets = (data: MarketCacheData) => {
  if (Array.isArray(data.assets)) {
    store.assets = [...data.assets];
  }
};

const historyOptions = computed<HistoryOption[]>(() =>
  groupedOpportunities.value.flatMap((group) =>
    group.signals.map((signal) => {
      const interval = signal.interval || "15m";
      const key = `${signal.symbol}@${interval}`;
      return {
        key,
        symbol: signal.symbol,
        interval,
        label: `${signal.symbol} @ ${interval}`,
      };
    }),
  ),
);

const configSections = ref<ConfigSection[]>([
  {
    key: "trend",
    label: "Trend Analysis",
    items: [
      {
        key: "trend_window_size",
        label: "Regression Window",
        type: "range",
        value: 6,
        min: 3,
        max: 20,
        step: 1,
        hint: "Candles for linear regression slope.",
        display: (value) => `${value}`,
      },
      {
        key: "price_trend_threshold",
        label: "Min Price Slope",
        type: "range",
        value: 0.05,
        min: 0.01,
        max: 0.5,
        step: 0.01,
        hint: "Min slope for bullish price trend.",
        display: (value) => Number(value).toFixed(2),
      },
      {
        key: "oi_trend_threshold",
        label: "Min OI Slope",
        type: "range",
        value: 0.1,
        min: 0.01,
        max: 0.5,
        step: 0.01,
        hint: "Min slope for money flow entering.",
        display: (value) => Number(value).toFixed(2),
      },
      {
        key: "cvd_trend_threshold",
        label: "Min CVD Slope",
        type: "range",
        value: 0,
        min: 0,
        max: 0.5,
        step: 0.01,
        hint: "Min slope for buying aggression.",
        display: (value) => Number(value).toFixed(2),
      },
    ],
  },
  {
    key: "reversal",
    label: "Reversal Logic",
    items: [
      {
        key: "div_lookback",
        label: "Divergence Lookback",
        type: "range",
        value: 20,
        min: 10,
        max: 50,
        step: 1,
        hint: "Candles to look back for highs/lows.",
        display: (value) => `${value}`,
      },
      {
        key: "div_price_breakout_pct",
        label: "Min Breakout %",
        type: "range",
        value: 0.2,
        min: 0.1,
        max: 1.0,
        step: 0.1,
        hint: "Price must break high/low by this %.",
        display: (value) => `${Number(value).toFixed(1)}%`,
      },
      {
        key: "div_indicator_gap_pct",
        label: "Min Divergence Gap %",
        type: "range",
        value: 1.5,
        min: 0.5,
        max: 5.0,
        step: 0.1,
        hint: "Indicator must lag by this %.",
        display: (value) => `${Number(value).toFixed(1)}%`,
      },
      {
        key: "strict_divergence",
        label: "Strict Divergence",
        type: "toggle",
        value: true,
        hint: "Require both OI and CVD to diverge.",
        display: (value) => (value ? "On" : "Off"),
      },
    ],
  },
  {
    key: "exit",
    label: "Exit Triggers",
    items: [
      {
        key: "tp_price_exhaustion_pct",
        label: "Exhaustion Move %",
        type: "range",
        value: 2.0,
        min: 0.1,
        max: 2.0,
        step: 0.1,
        hint: "Price move for profit-taking check.",
        display: (value) => `${Number(value).toFixed(1)}%`,
      },
      {
        key: "tp_oi_crash_pct",
        label: "Fuel Crash %",
        type: "range",
        value: 5.0,
        min: -5.0,
        max: -0.5,
        step: 0.1,
        hint: "OI drop signaling exhaustion.",
        display: (value) => `${Number(value).toFixed(1)}%`,
      },
      {
        key: "tp_price_stall_pct",
        label: "Stall Threshold %",
        type: "range",
        value: 0.3,
        min: 0.01,
        max: 0.5,
        step: 0.01,
        hint: "Price move considered a stall.",
        display: (value) => `${Number(value).toFixed(2)}%`,
      },
    ],
  },
  {
    key: "system",
    label: "System Operations",
    items: [
      {
        key: "scan_interval",
        label: "Scan Interval",
        type: "range",
        value: 60,
        min: 10,
        max: 3600,
        step: 5,
        hint: "Seconds between scans.",
        display: (value) => `${value}s`,
      },
      {
        key: "lookback_periods",
        label: "Data Window",
        type: "range",
        value: 50,
        min: 20,
        max: 300,
        step: 10,
        hint: "Number of datapoints to fetch.",
        display: (value) => `${value}`,
      },
      {
        key: "rate_limit_delay_ms",
        label: "API Delay",
        type: "range",
        value: 200,
        min: 50,
        max: 1000,
        step: 50,
        hint: "Delay between API calls.",
        display: (value) => `${value}ms`,
      },
    ],
  },
]);

const filteredLogs = computed(() => {
  if (logFilter.value === "all") return store.logs;
  const key = logFilter.value.toLowerCase();
  return store.logs.filter((log) => (log.type || "").toLowerCase().includes(key));
});

const scanButtonLabel = computed(() => {
  if (!automationStateReady.value) return "Checking automation...";
  if (store.isRunning) return "Scanning...";
  if (automationIsRunning.value) return "managed by agent";
  return "Run Scan Once";
});

const isScanDisabled = computed(
  () => !automationStateReady.value || store.isRunning || automationIsRunning.value,
);

const loadAutomationState = async () => {
  try {
    const response = await fetch("/api/v1/automation/state");
    const data = await response.json();
    const payload = data?.data;
    if (!payload) return;
    automationIsRunning.value = Boolean(payload.is_running);
  } catch {
    // Ignore automation state load errors.
  } finally {
    automationStateReady.value = true;
  }
};

const handleRun = () => {
  if (isScanDisabled.value) return;
  void store.runScan();
};

const getGroupStatus = (signals: QuantSignal[]): GroupStatus => {
  let hasLong = false;
  let hasShort = false;

  signals.forEach((signal) => {
    const direction = getSignalDirection(signal);
    if (direction === "LONG") hasLong = true;
    if (direction === "SHORT") hasShort = true;
  });

  if (hasLong && hasShort) return "mixed";
  if (hasLong) return "long";
  if (hasShort) return "short";
  return "flat";
};

const groupStatusLabel = (status: GroupStatus) => {
  if (status === "long") return "LONG";
  if (status === "short") return "SHORT";
  if (status === "mixed") return "MIXED";
  return "FLAT";
};

const groupStatusDotClass = (status: GroupStatus) => {
  if (status === "long") return "bg-positive";
  if (status === "short") return "bg-negative";
  if (status === "mixed") return "bg-warning";
  return "bg-muted";
};

const groupStatusBadgeClass = (status: GroupStatus) => {
  if (status === "long") return "border-positive/40 text-positive bg-positive/10";
  if (status === "short") return "border-negative/40 text-negative bg-negative/10";
  if (status === "mixed") return "border-warning/40 text-warning bg-warning/10";
  return "border-border text-muted bg-surface/50";
};

const signalGridClass = (count: number) =>
  count > 1 ? "grid grid-cols-1 gap-4 lg:grid-cols-2" : "grid grid-cols-1 gap-4";

const groupHeaderClass = (status: GroupStatus) => {
  if (status === "long") return "bg-positive/10";
  if (status === "short") return "bg-negative/10";
  if (status === "mixed") return "bg-warning/10";
  return "bg-panel/70";
};

const groupBorderClass = (status: GroupStatus) => {
  if (status === "long") return "border-l-4 border-l-positive/60";
  if (status === "short") return "border-l-4 border-l-negative/60";
  if (status === "mixed") return "border-l-4 border-l-warning/60";
  return "border-l-4 border-l-border";
};

const signalToneTextClass = (signal: QuantSignal) => {
  const direction = getSignalDirection(signal);
  if (direction === "LONG") return "text-positive";
  if (direction === "SHORT") return "text-negative";
  return "text-muted";
};

const signalPanelClass = (signal: QuantSignal) => {
  const direction = getSignalDirection(signal);
  if (direction === "LONG") return "border-l-4 border-l-positive/60";
  if (direction === "SHORT") return "border-l-4 border-l-negative/60";
  return "border-l-4 border-l-border";
};

const signalDirectionLabel = (signal: QuantSignal) => {
  const direction = getSignalDirection(signal);
  if (direction === "LONG") return "Long";
  if (direction === "SHORT") return "Short";
  return "Neutral";
};

const signalDirectionBadgeClass = (signal: QuantSignal) => {
  const direction = getSignalDirection(signal);
  if (direction === "LONG") return "border-positive/40 text-positive bg-positive/10";
  if (direction === "SHORT") return "border-negative/40 text-negative bg-negative/10";
  return "border-border text-muted bg-surface/40";
};

const signalTonePillClass = (signal: QuantSignal) => {
  const direction = getSignalDirection(signal);
  if (direction === "LONG") return "border-positive/40 text-positive bg-positive/10";
  if (direction === "SHORT") return "border-negative/40 text-negative bg-negative/10";
  return "border-border text-muted bg-surface/40";
};

const formatSignalName = (signal: QuantSignal) => {
  const meta = signal.signal_metadata;
  if (meta?.signal_name) {
    const name = meta.signal_name.toUpperCase();
    const direction = normalizeDirection(meta.direction);
    if (direction === "LONG") return `${name} LONG`;
    if (direction === "SHORT") return `${name} SHORT`;
    return name;
  }
  if (!signal.signal_type) return "SIGNAL";
  return signal.signal_type.replace(/_/g, " ").toUpperCase();
};

const formatPrice = (price?: number) => {
  if (
    price === null ||
    price === undefined ||
    Number.isNaN(price) ||
    !Number.isFinite(price)
  )
    return "--";
  if (price >= 10000) return `${(price / 1000).toFixed(1)}k`;
  if (price >= 1000) return price.toFixed(0);
  if (price >= 1) return price.toFixed(2);
  return price.toPrecision(4);
};

const formatNumber = (value?: number, decimals = 2) => {
  if (
    value === null ||
    value === undefined ||
    Number.isNaN(value) ||
    !Number.isFinite(value)
  )
    return "--";
  return value.toFixed(decimals);
};

const formatCompact = (value?: number, decimals = 2) => {
  if (
    value === null ||
    value === undefined ||
    Number.isNaN(value) ||
    !Number.isFinite(value)
  )
    return "--";
  const abs = Math.abs(value);
  const sign = value < 0 ? "-" : "";
  if (abs >= 1_000_000_000) return `${sign}${(abs / 1_000_000_000).toFixed(decimals)}B`;
  if (abs >= 1_000_000) return `${sign}${(abs / 1_000_000).toFixed(decimals)}M`;
  if (abs >= 1_000) return `${sign}${(abs / 1_000).toFixed(decimals)}k`;
  return `${value.toFixed(decimals)}`;
};

const formatUsdValue = (value: string) => {
  if (value === "--") return "--";
  if (value.startsWith("-")) return `-$${value.slice(1)}`;
  return `$${value}`;
};

const formatUsd = (value?: number) => formatUsdValue(formatPrice(value));

const formatUsdCompact = (value?: number, decimals = 2) =>
  formatUsdValue(formatCompact(value, decimals));

const formatUsdNumber = (value?: number, decimals = 2) =>
  formatUsdValue(formatNumber(value, decimals));

const formatPercent = (value?: number, decimals = 2) => {
  if (
    value === null ||
    value === undefined ||
    Number.isNaN(value) ||
    !Number.isFinite(value)
  )
    return "--";
  return `${value >= 0 ? "+" : ""}${value.toFixed(decimals)}%`;
};

const formatText = (value?: string | null) => {
  if (!value) return "--";
  return value.replace(/_/g, " ").toUpperCase();
};

const formatTimestampMs = (value?: number | null) => {
  if (value === null || value === undefined) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "--";
  return date.toLocaleString();
};

const formatDateTime = (value?: string) => {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "--";
  return date.toLocaleString();
};

const formatSlope = (slope?: number) => {
  if (
    slope === null ||
    slope === undefined ||
    Number.isNaN(slope) ||
    !Number.isFinite(slope)
  )
    return "--";
  return `${slope >= 0 ? "+" : ""}${slope.toFixed(1)}%`;
};

const formatAge = (openedAt?: string) => {
  if (!openedAt) return "--";
  const opened = new Date(openedAt);
  if (Number.isNaN(opened.getTime())) return "--";
  const diffMs = Date.now() - opened.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 60) return `${diffMins}m`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h`;
  return `${Math.floor(diffHours / 24)}d`;
};

const toneFromNumber = (value?: number | null): StatTone => {
  if (
    value === null ||
    value === undefined ||
    Number.isNaN(value) ||
    !Number.isFinite(value)
  )
    return "muted";
  if (value > 0) return "positive";
  if (value < 0) return "negative";
  return "muted";
};

const statToneClass = (tone?: StatTone) => {
  if (tone === "positive") return "text-positive";
  if (tone === "negative") return "text-negative";
  if (tone === "warning") return "text-warning";
  if (tone === "accent") return "text-accent";
  if (tone === "muted") return "text-muted";
  return "text-text";
};

const makeStat = (key: string, label: string, value: string, tone?: StatTone): StatItem => ({
  key,
  label,
  value,
  tone,
});

const coreStats = (signal: QuantSignal): StatItem[] => [
  makeStat(
    "price",
    "Price",
    formatUsd(signal.current_price ?? signal.entry_price),
    toneFromNumber(signal.price_slope),
  ),
  makeStat("age", "Age", formatAge(signal.opened_at)),
  makeStat(
    "oi",
    "OI Current",
    formatUsdCompact(signal.current_oi, 0),
    toneFromNumber(signal.oi_slope),
  ),
  makeStat(
    "cvd",
    "CVD Current",
    formatCompact(signal.cvd_current, 0),
    toneFromNumber(signal.cvd_current),
  ),
  makeStat(
    "cvd_delta",
    "CVD Delta",
    formatCompact(signal.cvd_delta, 0),
    toneFromNumber(signal.cvd_delta),
  ),
  makeStat(
    "net_depth",
    "Net Depth",
    formatUsdCompact(signal.net_depth_usd, 0),
    toneFromNumber(signal.net_depth_usd),
  ),
  makeStat(
    "depth_regime",
    "Depth Regime",
    formatText(signal.depth_regime),
    toneFromNumber(signal.net_depth_usd),
  ),
];

const slopeStats = (signal: QuantSignal): StatItem[] => [
  makeStat(
    "price_slope",
    "Price Slope",
    formatSlope(signal.price_slope),
    toneFromNumber(signal.price_slope),
  ),
  makeStat(
    "price_z",
    "Price Z",
    formatNumber(signal.price_slope_z ?? undefined, 2),
    toneFromNumber(signal.price_slope_z),
  ),
  makeStat(
    "oi_slope",
    "OI Slope",
    formatSlope(signal.oi_slope),
    toneFromNumber(signal.oi_slope),
  ),
  makeStat(
    "oi_z",
    "OI Z",
    formatNumber(signal.oi_slope_z ?? undefined, 2),
    toneFromNumber(signal.oi_slope_z),
  ),
  makeStat(
    "cvd_slope",
    "CVD Slope",
    formatSlope(signal.cvd_slope),
    toneFromNumber(signal.cvd_slope),
  ),
  makeStat(
    "cvd_z",
    "CVD Z",
    formatNumber(signal.cvd_slope_z ?? undefined, 2),
    toneFromNumber(signal.cvd_slope_z),
  ),
];

const depthStats = (signal: QuantSignal): StatItem[] => {
  const depth = signal.depth_context;
  return [
    makeStat(
      "bid_volume",
      "Bid Volume",
      formatUsdCompact(depth?.bid_volume_usd, 0),
      toneFromNumber(depth?.bid_volume_usd),
    ),
    makeStat(
      "ask_volume",
      "Ask Volume",
      formatUsdCompact(depth?.ask_volume_usd, 0),
      toneFromNumber(depth?.ask_volume_usd),
    ),
    makeStat(
      "net_depth",
      "Net Depth",
      formatUsdCompact(depth?.net_depth_usd, 0),
      toneFromNumber(depth?.net_depth_usd),
    ),
    makeStat(
      "imbalance",
      "Imbalance",
      formatPercent(depth?.imbalance_pct, 2),
      toneFromNumber(depth?.imbalance_pct),
    ),
  ];
};

const vwapStats = (signal: QuantSignal): StatItem[] => {
  const vwap = signal.vwap_context;
  return [
    makeStat("vwap", "VWAP", formatUsd(vwap?.vwap), toneFromNumber(vwap?.distance_sd)),
    makeStat(
      "vwap_dist",
      "Distance SD",
      formatNumber(vwap?.distance_sd, 2),
      toneFromNumber(vwap?.distance_sd),
    ),
  ];
};

const fundingStats = (signal: QuantSignal): StatItem[] => {
  const funding = signal.funding_context;
  const ratePct =
    funding?.current_rate_pct ||
    (typeof funding?.current_rate === "number"
      ? `${(funding.current_rate * 100).toFixed(4)}%`
      : "--");
  return [
    makeStat("fund_rate_pct", "Rate Pct", ratePct, toneFromNumber(funding?.current_rate)),
  ];
};

const atrStats = (signal: QuantSignal): StatItem[] => {
  const atr = signal.atr_context;
  return [
    makeStat("atr_value", "ATR", formatUsdNumber(atr?.current_atr, 4)),
    makeStat(
      "atr_slope",
      "ATR Slope",
      formatPercent(atr?.atr_slope, 2),
      toneFromNumber(atr?.atr_slope),
    ),
    makeStat(
      "atr_z",
      "ATR Z",
      formatNumber(atr?.atr_z_score ?? undefined, 2),
      toneFromNumber(atr?.atr_z_score),
    ),
  ];
};

const netflowStats = (signal: QuantSignal): StatItem[] => {
  const flow = signal.fund_inflow_context;
  return [
    makeStat(
      "flow_total",
      "Total",
      formatUsdCompact(flow?.total_netflow, 0),
      toneFromNumber(flow?.total_netflow),
    ),
    makeStat(
      "flow_inst",
      "Institution",
      formatUsdCompact(flow?.institution_netflow, 0),
      toneFromNumber(flow?.institution_netflow),
    ),
    makeStat(
      "flow_retail",
      "Retail",
      formatUsdCompact(flow?.retail_netflow, 0),
      toneFromNumber(flow?.retail_netflow),
    ),
    makeStat("flow_regime", "Regime", formatText(flow?.flow_regime)),
    makeStat("flow_dominant", "Dominant", formatText(flow?.dominant_flow)),
  ];
};

const marketContextStats = (signal: QuantSignal): StatItem[] => {
  const prefix = (value: string, group: string) => `${group} ${value}`;
  return [
    ...vwapStats(signal).map((stat) => ({
      ...stat,
      key: `vwap_${stat.key}`,
      label: prefix(stat.label, "VWAP"),
    })),
    ...fundingStats(signal).map((stat) => ({
      ...stat,
      key: `fund_${stat.key}`,
      label: prefix(stat.label, "Funding"),
    })),
    ...atrStats(signal).map((stat) => ({
      ...stat,
      key: `atr_${stat.key}`,
      label: prefix(stat.label, "ATR"),
    })),
    ...netflowStats(signal).map((stat) => ({
      ...stat,
      key: `flow_${stat.key}`,
      label: prefix(stat.label, "Flow"),
    })),
  ];
};

const anomalyCards = (signal: QuantSignal): AnomalyCard[] => {
  const anomaly = signal.anomaly_context;
  const cards = [
    { key: "price", label: "Price", data: anomaly?.price },
    { key: "oi", label: "Open Interest", data: anomaly?.oi },
    { key: "cvd", label: "CVD", data: anomaly?.cvd },
  ];
  return cards.filter((card) => card.data?.is_significant);
};

const signalActions = (signal: QuantSignal) => signal.signal_actions || signal.actions || null;

const signalInterpretation = (signal: QuantSignal) =>
  signal.signal_metadata?.interpretation || signal.signal_reason || "";

const fundingTone = (regime: string): ContextChip["tone"] => {
  const value = regime.toLowerCase();
  if (value.includes("extreme")) return "warning";
  if (value.includes("positive")) return "negative";
  if (value.includes("negative")) return "positive";
  return "muted";
};

const atrTone = (regime: string): ContextChip["tone"] => {
  const value = regime.toLowerCase();
  if (value.includes("high") || value.includes("elevated")) return "warning";
  if (value.includes("dead") || value.includes("low")) return "muted";
  return "accent";
};

const flowTone = (regime: string): ContextChip["tone"] => {
  const value = regime.toLowerCase();
  if (value.includes("positive")) return "positive";
  if (value.includes("negative")) return "negative";
  return "muted";
};

const contextChips = (signal: QuantSignal): ContextChip[] => {
  const chips: ContextChip[] = [];

  const vwap = signal.vwap_context;
  if (vwap) {
    const state = vwap.vwap_state ? vwap.vwap_state.replace(/_/g, " ").toUpperCase() : "";
    const distance = typeof vwap.distance_sd === "number" ? vwap.distance_sd : null;
    const distanceLabel =
      distance !== null ? `${distance >= 0 ? "+" : ""}${distance.toFixed(1)} SD` : "";
    if (state || distanceLabel) {
      chips.push({
        label: "VWAP",
        value: [state || "VWAP", distanceLabel].filter(Boolean).join(" · "),
        tone: distance !== null ? (distance >= 0 ? "positive" : "negative") : "muted",
      });
    }
  }

  const funding = signal.funding_context;
  if (funding) {
    const regime = funding.regime ? funding.regime.replace(/_/g, " ").toUpperCase() : "";
    const rate =
      funding.current_rate_pct ||
      (typeof funding.current_rate === "number"
        ? `${(funding.current_rate * 100).toFixed(4)}%`
        : "");
    if (regime || rate) {
      chips.push({
        label: "Funding",
        value: [regime || "FUNDING", rate].filter(Boolean).join(" · "),
        tone: fundingTone(funding.regime || ""),
      });
    }
  }

  const atr = signal.atr_context;
  if (atr) {
    const regime = atr.market_regime ? atr.market_regime.replace(/_/g, " ").toUpperCase() : "";
    const percentile =
      typeof atr.percentile_rank === "number" ? `${Math.round(atr.percentile_rank)}th` : "";
    if (regime || percentile) {
      chips.push({
        label: "ATR",
        value: [regime || "ATR", percentile].filter(Boolean).join(" · "),
        tone: atrTone(atr.market_regime || ""),
      });
    }
  }

  const flow = signal.fund_inflow_context;
  if (flow) {
    const regime = flow.flow_regime ? flow.flow_regime.replace(/_/g, " ").toUpperCase() : "";
    const dominant = flow.dominant_flow ? flow.dominant_flow.replace(/_/g, " ").toUpperCase() : "";
    if (regime || dominant) {
      chips.push({
        label: "Flow",
        value: [regime || "FLOW", dominant].filter(Boolean).join(" · "),
        tone: flowTone(flow.flow_regime || ""),
      });
    }
  }

  const anomaly = signal.anomaly_context;
  if (anomaly) {
    const factors = ["price", "oi", "cvd"].flatMap((key) => {
      const factor = anomaly[key as keyof typeof anomaly];
      if (!factor || typeof factor !== "object") return [];
      const record = factor as { is_significant?: boolean; anomaly_type?: string };
      if (!record.is_significant || !record.anomaly_type || record.anomaly_type === "normal") {
        return [];
      }
      return [`${key.toUpperCase()} ${record.anomaly_type.toUpperCase()}`];
    });
    if (factors.length > 0) {
      chips.push({ label: "Anomaly", value: factors.join(", "), tone: "warning" });
    }
  }

  const spot = signal.spot_futures_context;
  if (spot) {
    const coupling = spot.coupling_state
      ? spot.coupling_state.replace(/_/g, " ").toUpperCase()
      : "";
    const divergence = spot.divergence_signal
      ? spot.divergence_signal.replace(/_/g, " ").toUpperCase()
      : "";
    if (coupling || divergence) {
      chips.push({
        label: "Spot/Fut",
        value: [coupling || "COUPLING", divergence].filter(Boolean).join(" · "),
        tone: "accent",
      });
    }
  }

  return chips;
};

const chipToneClass = (tone: ContextChip["tone"]) => {
  if (tone === "positive") return "border-positive/40 text-positive bg-positive/10";
  if (tone === "negative") return "border-negative/40 text-negative bg-negative/10";
  if (tone === "warning") return "border-warning/40 text-warning bg-warning/10";
  if (tone === "accent") return "border-accent/40 text-accent bg-accent/10";
  return "border-border text-muted bg-surface/50";
};

const logEntryClass = (log: { message?: string; type?: string }) => {
  const type = (log.type || "").toLowerCase();
  const base =
    "rounded-md border border-border/40 bg-surface/60 px-2 py-0.5 font-mono text-[11px] leading-relaxed";

  if (type === "system") return `${base} border-transparent bg-transparent text-muted`;
  if (type === "alert")
    return `${base} border-accent/40 bg-accent/15 text-accent font-semibold border-l-4`;
  if (type === "bullish")
    return `${base} border-positive/40 bg-positive/10 text-positive font-medium border-l-4`;
  if (type === "bearish")
    return `${base} border-negative/40 bg-negative/10 text-negative font-medium border-l-4`;
  if (type === "divergence")
    return `${base} border-warning/40 bg-warning/10 text-warning font-medium border-l-4`;
  if (type === "neutral")
    return `${base} border-border/40 bg-surface/40 text-muted`;
  if (type === "error") return `${base} border-negative/40 bg-negative/10 text-negative`;
  if (type === "warning") return `${base} border-warning/40 bg-warning/10 text-warning`;
  if (type === "success") return `${base} border-positive/30 bg-positive/10 text-positive`;
  if (type === "fetch") return `${base} border-accent/30 bg-accent/10 text-accent`;
  if (type === "calc") return `${base} border-warning/30 bg-warning/10 text-warning`;
  if (type === "signal") return `${base} border-accent/30 bg-accent/10 text-accent font-semibold`;
  if (type === "cycle-start")
    return `${base} border-accent/30 bg-surface/40 text-accent border-dashed`;
  if (type === "cycle-end")
    return `${base} border-border/40 bg-surface/40 text-muted border-dashed`;
  if (type.includes("error")) return `${base} border-negative/40 bg-negative/10 text-negative`;
  if (type.includes("warning")) return `${base} border-warning/40 bg-warning/10 text-warning`;
  if (type.includes("success")) return `${base} border-positive/30 bg-positive/10 text-positive`;
  if (type.includes("signal")) return `${base} border-accent/30 bg-accent/10 text-accent font-semibold`;
  return `${base} text-text`;
};

const openHistoryModal = () => {
  showHistoryModal.value = true;
  if (!selectedHistoryKey.value && historyOptions.value.length > 0) {
    selectedHistoryKey.value = historyOptions.value[0].key;
  }
  if (selectedHistoryKey.value) {
    loadHistory(selectedHistoryKey.value);
  }
};

const closeHistoryModal = () => {
  showHistoryModal.value = false;
};

const handleHistorySelect = (event: Event) => {
  const target = event.target as HTMLSelectElement;
  const value = target.value || null;
  selectedHistoryKey.value = value;
  if (value) {
    loadHistory(value);
  }
};

const loadHistory = async (key: string) => {
  const target = historyOptions.value.find((option) => option.key === key);
  if (!target) return;

  historyLoading.value = true;
  historyError.value = null;
  historyEntries.value = [];
  historyLoading.value = false;
  historyError.value = "Signal history is not available yet.";
};

const formatTimestamp = (value: string) => {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
};

const handleLogScroll = () => {
  if (!logListRef.value) return;
  logAutoScroll.value = logListRef.value.scrollTop <= 0;
};

watch(
  () => historyOptions.value,
  (options) => {
    if (options.length === 0) {
      selectedHistoryKey.value = null;
      historyEntries.value = [];
      return;
    }
    if (!selectedHistoryKey.value || !options.some((opt) => opt.key === selectedHistoryKey.value)) {
      selectedHistoryKey.value = options[0].key;
      if (showHistoryModal.value) {
        loadHistory(options[0].key);
      }
    }
  },
  { deep: true },
);

watch(
  () => filteredLogs.value.length,
  async () => {
    if (!logAutoScroll.value) return;
    await nextTick();
    if (logListRef.value) {
      logListRef.value.scrollTop = 0;
    }
  },
);

onMounted(async () => {
  const cached = readMarketCache();
  if (cached) {
    applyMarketAssets(cached);
  }
  unsubscribeMarketCache = subscribeMarketCache((data) => applyMarketAssets(data));
  void loadAutomationState();
  automationPollTimer = setInterval(loadAutomationState, 15000);
  await store.loadAssets();
});

onActivated(() => {
  void nextTick(() => {
    if (leftPanelRef.value) {
      leftPanelRef.value.scrollTop = leftPanelScrollTop.value;
    }
  });
  void store.loadAssets();
});

onDeactivated(() => {
  if (leftPanelRef.value) {
    leftPanelScrollTop.value = leftPanelRef.value.scrollTop;
  }
});

onBeforeUnmount(() => {
  if (unsubscribeMarketCache) {
    unsubscribeMarketCache();
    unsubscribeMarketCache = null;
  }
  if (automationPollTimer) {
    clearInterval(automationPollTimer);
    automationPollTimer = null;
  }
});
</script>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 160ms ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
