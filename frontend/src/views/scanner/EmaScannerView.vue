<template>
  <div class="flex h-full min-h-0 flex-1 flex-col gap-3 overflow-hidden">
    <div
      class="grid min-h-0 flex-1 gap-4 overflow-hidden xl:grid-cols-[280px_minmax(0,1fr)_320px] xl:grid-rows-[auto_minmax(0,1fr)]"
    >
      <div
        class="col-span-full flex flex-wrap items-center justify-between gap-2 xl:col-span-1 xl:col-start-1 xl:row-start-1"
      >
        <h1 class="font-display text-xl">EMA Scanner</h1>
        <BaseBadge>
          {{ store.isConnected ? "Socket: Live" : "Socket: Idle" }}
        </BaseBadge>
      </div>

      <aside class="flex h-full min-h-0 flex-col overflow-hidden xl:col-start-1 xl:row-start-2">
        <div class="shrink-0 space-y-4">
          <BaseCard>
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <span
                  class="h-2 w-2 rounded-full"
                  :class="store.isScanning ? 'bg-warning' : store.isConnected ? 'bg-accent' : 'bg-negative'"
                ></span>
                <span class="font-display text-sm">Market Scanner</span>
              </div>
              <span class="text-[10px] uppercase tracking-wide text-muted">
                {{ store.isScanning ? "Running" : "Idle" }}
              </span>
            </div>
            <p class="mt-2 text-xs text-muted">
              Using default config · EMA resonance
            </p>
            <div class="mt-2 flex items-center justify-between text-[10px] uppercase tracking-wide text-muted">
              <span>Cycle</span>
              <span class="font-mono text-text">
                {{ store.cycleNumber > 0 ? `#${store.cycleNumber}` : "--" }}
              </span>
            </div>
          </BaseCard>

          <button
            class="w-full rounded-md border border-border px-3 py-2 text-sm font-medium transition-colors duration-200 disabled:cursor-not-allowed disabled:opacity-70"
            :class="automationIsRunning || !automationStateReady ? 'bg-panel text-muted' : 'bg-accent text-base'"
            type="button"
            :disabled="isScanDisabled"
            @click="handleScan"
          >
            <Transition name="fade" mode="out-in">
              <span :key="scanButtonLabel">{{ scanButtonLabel }}</span>
            </Transition>
          </button>
        </div>

        <div
          ref="leftPanelRef"
          class="mt-4 flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto pr-1 scrollbar-hidden"
        >
          <div class="flex gap-2">
            <button
              class="w-full rounded-md border border-border bg-panel px-3 py-2 text-xs text-muted hover:text-text"
              type="button"
              :disabled="store.isImporting"
              @click="handleImportClick"
            >
              {{ store.isImporting ? "Importing..." : "Import CSV" }}
            </button>
            <button
              class="w-full rounded-md border border-border bg-panel px-3 py-2 text-xs text-muted hover:text-text"
              type="button"
              @click="handleExport"
            >
              Export CSV
            </button>
            <input
              ref="scanFileInput"
              class="hidden"
              type="file"
              accept=".csv"
              @change="handleImportChange"
            />
          </div>

          <ScannerCalendar
            :data="store.calendarData"
            :selected="store.selectedDate"
            @select="store.loadHistory"
          />

          <button
            class="w-full rounded-md border border-border bg-panel px-3 py-2 text-xs text-muted hover:text-text"
            type="button"
            @click="store.toggleLogOverlay"
          >
            {{ store.showLogOverlay ? "Close Logs" : "View Scan Logs" }}
          </button>

          <BaseCard>
            <div class="flex items-center justify-between">
              <span class="text-xs uppercase tracking-wide text-muted">EMAs</span>
              <form class="flex items-center gap-2" @submit.prevent="handleAddEma">
                <input
                  v-model.number="newEma"
                  class="w-20 rounded-md border border-border bg-panel px-2 py-1 text-xs"
                  type="number"
                  placeholder="+ EMA"
                />
                <button
                  class="rounded-md border border-border bg-surface px-2 py-1 text-[11px] text-muted"
                  type="submit"
                >
                  Add
                </button>
              </form>
            </div>
            <div class="mt-3 flex flex-wrap gap-2">
              <div
                v-for="ema in store.emaLines"
                :key="ema.id"
                class="flex items-center gap-2 rounded-full border border-border bg-panel px-3 py-1 text-xs"
              >
                <span class="text-text">EMA {{ ema.length }}</span>
                <button
                  class="text-muted hover:text-text"
                  type="button"
                  @click="store.removeEmaLine(ema.id)"
                >
                  ×
                </button>
              </div>
              <span v-if="store.emaLines.length === 0" class="text-xs text-muted">
                No EMA params yet.
              </span>
            </div>
          </BaseCard>

          <BaseCard>
            <div class="flex items-center justify-between">
              <span class="text-xs uppercase tracking-wide text-muted">Tolerance</span>
              <span class="text-xs text-accent">{{ toleranceValue.toFixed(1) }}%</span>
            </div>
            <input
              v-model.number="toleranceValue"
              class="mt-3 w-full"
              type="range"
              min="0.1"
              max="2.0"
              step="0.1"
              @change="store.updateTolerance(toleranceValue)"
            />
          </BaseCard>

          <BaseCard>
            <div class="flex items-center justify-between">
              <span class="text-xs uppercase tracking-wide text-muted">State Manager</span>
              <span class="text-[10px] text-muted">
                {{ isSavingStateConfig ? "Saving..." : "Live" }}
              </span>
            </div>
            <div class="mt-3 space-y-4 text-[11px] text-muted">
              <label class="block space-y-1">
                <div class="flex items-center justify-between">
                  <span>Min Resonance</span>
                  <span class="font-mono text-text">{{ stateConfig.min_resonance }}</span>
                </div>
                <input
                  v-model.number="stateConfig.min_resonance"
                  class="w-full"
                  type="range"
                  min="1"
                  max="5"
                  step="1"
                />
              </label>
              <label class="block space-y-1">
                <div class="flex items-center justify-between">
                  <span>EMA Resonance Cooldown</span>
                  <span class="font-mono text-text">
                    {{ formatDuration(stateConfig.ema_resonance_cooldown_seconds) }}
                  </span>
                </div>
                <input
                  v-model.number="stateConfig.ema_resonance_cooldown_seconds"
                  class="w-full"
                  type="range"
                  min="60"
                  max="3600"
                  step="30"
                />
              </label>
              <label class="block space-y-1">
                <div class="flex items-center justify-between">
                  <span>BB Rejection Cooldown</span>
                  <span class="font-mono text-text">
                    {{ formatDuration(stateConfig.bb_rejection_cooldown_seconds) }}
                  </span>
                </div>
                <input
                  v-model.number="stateConfig.bb_rejection_cooldown_seconds"
                  class="w-full"
                  type="range"
                  min="60"
                  max="3600"
                  step="30"
                />
              </label>
              <label class="block space-y-1">
                <div class="flex items-center justify-between">
                  <span>BB Exit Warning Cooldown</span>
                  <span class="font-mono text-text">
                    {{ formatDuration(stateConfig.bb_exit_warning_cooldown_seconds) }}
                  </span>
                </div>
                <input
                  v-model.number="stateConfig.bb_exit_warning_cooldown_seconds"
                  class="w-full"
                  type="range"
                  min="60"
                  max="3600"
                  step="30"
                />
              </label>
              <label class="block space-y-1">
                <div class="flex items-center justify-between">
                  <span>Position Check Interval</span>
                  <span class="font-mono text-text">
                    {{ formatDuration(stateConfig.position_check_interval_seconds) }}
                  </span>
                </div>
                <input
                  v-model.number="stateConfig.position_check_interval_seconds"
                  class="w-full"
                  type="range"
                  min="60"
                  max="3600"
                  step="60"
                />
              </label>
              <label class="block space-y-1">
                <div class="flex items-center justify-between">
                  <span>BB Rejection Min Touches</span>
                  <span class="font-mono text-text">{{ stateConfig.bb_rejection_min_touches }}</span>
                </div>
                <input
                  v-model.number="stateConfig.bb_rejection_min_touches"
                  class="w-full"
                  type="range"
                  min="1"
                  max="30"
                  step="1"
                />
              </label>
              <label class="block space-y-1">
                <div class="flex items-center justify-between">
                  <span>Minimum BB Timeframe</span>
                  <span class="font-mono text-text">{{ htfMinHours }}h</span>
                </div>
                <input
                  v-model.number="htfMinHours"
                  class="w-full"
                  type="range"
                  min="1"
                  max="48"
                  step="1"
                />
              </label>
              <div class="rounded-md border border-border/60 bg-panel/40 p-2">
                <div class="text-[10px] uppercase tracking-wide text-muted">Emit Events</div>
                <div class="mt-2 grid gap-2 sm:grid-cols-2">
                  <label class="flex items-center gap-2 text-[11px] text-muted">
                    <input v-model="stateConfig.emit_new_resonance" type="checkbox" />
                    New Resonance
                  </label>
                  <label class="flex items-center gap-2 text-[11px] text-muted">
                    <input v-model="stateConfig.emit_resonance_increase" type="checkbox" />
                    Resonance Increase
                  </label>
                  <label class="flex items-center gap-2 text-[11px] text-muted">
                    <input v-model="stateConfig.emit_structure_shift" type="checkbox" />
                    Structure Shift
                  </label>
                  <label class="flex items-center gap-2 text-[11px] text-muted">
                    <input v-model="stateConfig.emit_resonance_refresh" type="checkbox" />
                    Resonance Refresh
                  </label>
                  <label class="flex items-center gap-2 text-[11px] text-muted">
                    <input v-model="stateConfig.emit_bb_rejection_upper" type="checkbox" />
                    BB Rejection Upper
                  </label>
                  <label class="flex items-center gap-2 text-[11px] text-muted">
                    <input v-model="stateConfig.emit_bb_rejection_lower" type="checkbox" />
                    BB Rejection Lower
                  </label>
                  <label class="flex items-center gap-2 text-[11px] text-muted">
                    <input v-model="stateConfig.emit_position_management" type="checkbox" />
                    Position Management
                  </label>
                  <label class="flex items-center gap-2 text-[11px] text-muted">
                    <input v-model="stateConfig.emit_bb_exit_warning" type="checkbox" />
                    BB Exit Warning
                  </label>
                </div>
              </div>
              <button
                class="w-full rounded-md border border-border bg-panel px-3 py-2 text-xs text-muted hover:text-text disabled:opacity-60"
                type="button"
                :disabled="isSavingStateConfig"
                @click="saveStateConfig"
              >
                Save State Manager
              </button>
              <div v-if="stateConfigError" class="text-[11px] text-negative">
                {{ stateConfigError }}
              </div>
            </div>
          </BaseCard>

          <BaseCard>
            <div class="text-xs uppercase tracking-wide text-muted">Indicators</div>
            <div class="mt-3 space-y-2 text-sm">
              <label class="flex items-center gap-2 text-muted opacity-70">
                <input checked disabled type="checkbox" />
                EMA
              </label>
              <label class="flex items-center gap-2 text-muted opacity-70">
                <input checked disabled type="checkbox" />
                Bollinger Band
              </label>
            </div>
          </BaseCard>

          <BaseCard>
            <div class="flex items-center justify-between">
              <span class="text-xs uppercase tracking-wide text-muted">Log</span>
              <span class="text-[10px] text-muted">Latest</span>
            </div>
            <div
              ref="logListRef"
              class="mt-3 max-h-32 space-y-2 overflow-y-auto text-[11px] text-muted scrollbar-hidden"
              @scroll="handleLogListScroll"
            >
              <p v-for="(log, idx) in store.logs.slice(0, 8)" :key="idx">
                {{ formatLogMessage(log) }}
              </p>
              <p v-if="store.logs.length === 0">No logs yet.</p>
            </div>
          </BaseCard>
        </div>
      </aside>

      <main
        class="relative flex min-h-0 flex-col overflow-hidden xl:col-start-2 xl:row-span-2 xl:row-start-1"
      >
        <div class="shrink-0 pb-3 pr-1">
          <div class="flex items-center justify-between rounded-lg border border-border bg-surface px-4 py-3">
            <span class="font-display text-sm">Scan Results</span>
            <div class="text-right text-xs text-muted">
              <div>{{ store.results.length }} Found</div>
              <div v-if="store.selectedDate" class="text-[10px]">
                History {{ store.selectedDate }}
              </div>
            </div>
          </div>
        </div>

        <div class="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto pr-1 scrollbar-hidden">
          <div
            v-if="!store.isScanning && store.results.length === 0"
            class="flex min-h-[240px] flex-col items-center justify-center rounded-lg border border-dashed border-border bg-surface text-sm text-muted"
          >
            <div class="text-3xl">📡</div>
            <p class="mt-2">Ready to scan markets.</p>
          </div>

          <div
            v-if="store.results.length > 0"
            class="grid gap-3 md:grid-cols-2 xl:grid-cols-3"
          >
            <BaseCard
              v-for="result in store.results"
              :key="result.id || result.ticker"
              class="transition-transform duration-150 ease-out hover:-translate-y-0.5 hover:shadow-panel"
            >
              <div class="flex items-start justify-between">
                <div>
                  <div class="font-display text-lg font-semibold text-text">{{ result.ticker }}</div>
                  <div class="text-xs text-muted">
                    {{ (result.ema_votes?.length || 0) }} EMA +
                    {{ (result.bb_votes?.length || 0) }} BB signals
                  </div>
                </div>
                <div class="flex items-center gap-2">
                  <BaseBadge>{{ result.votes ?? 0 }} Votes</BaseBadge>
                </div>
              </div>

              <div class="mt-3">
                <ScannerResultChart :data="resolveChartData(result)" />
              </div>

              <div class="mt-3 flex flex-wrap gap-2">
                <span
                  v-for="(vote, idx) in result.ema_votes || []"
                  :key="`ema-${idx}`"
                  class="rounded-full border border-border px-2 py-1 text-[10px] text-muted"
                >
                  {{ vote.interval }} EMA
                </span>
                <span
                  v-for="(vote, idx) in result.bb_votes || []"
                  :key="`bb-${idx}`"
                  class="rounded-full border border-border px-2 py-1 text-[10px] text-muted"
                >
                  {{ vote.interval }} BB
                </span>
              </div>

              <div class="mt-4 flex items-center justify-between">
                <div>
                  <button
                    v-if="result.id"
                    class="rounded-md border border-border/40 bg-transparent px-2 py-1 text-[10px] text-muted/80 hover:border-border hover:text-text"
                    type="button"
                    @click="handleDeleteResult(result)"
                  >
                    Delete
                  </button>
                </div>
                <button
                  class="rounded-md border border-border bg-surface px-3 py-1 text-[11px] text-muted"
                  type="button"
                >
                  Trade
                </button>
              </div>
            </BaseCard>
          </div>
        </div>

        <Transition name="log-overlay">
          <div
            v-if="store.showLogOverlay"
            class="absolute inset-0 z-50 flex items-center justify-center bg-black/70 p-6 backdrop-blur-sm"
          >
            <div class="log-panel w-full max-w-2xl rounded-lg border border-border bg-surface p-4">
              <div class="flex items-center justify-between">
                <span class="font-display text-sm">Scan Logs</span>
                <button
                  class="rounded-md border border-border px-2 py-1 text-xs text-muted"
                  type="button"
                  @click="store.toggleLogOverlay"
                >
                  Close
                </button>
              </div>
              <div
                ref="logOverlayRef"
                class="mt-3 max-h-80 space-y-2 overflow-y-auto text-xs text-muted scrollbar-hidden"
                @scroll="handleLogOverlayScroll"
              >
                <p v-for="(log, idx) in store.logs" :key="`log-${idx}`">
                  {{ formatLogMessage(log, true) }}
                </p>
                <p v-if="store.logs.length === 0">No logs yet.</p>
              </div>
            </div>
          </div>
        </Transition>
      </main>

      <aside
        class="flex h-full min-h-0 flex-col overflow-hidden xl:col-start-3 xl:row-span-2 xl:row-start-1"
      >
        <div class="shrink-0 pr-1">
          <BaseCard>
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <span class="font-display text-sm">Vegas State</span>
                <span class="text-[10px] uppercase tracking-wide" :class="vegasStatusClass">
                  {{ vegasStatusLabel }}
                </span>
              </div>
            </div>
            <div
              class="mt-2 flex items-center justify-between gap-4 text-[10px] uppercase tracking-wide text-muted"
            >
              <div class="flex items-baseline gap-2">
                <span>Tickers</span>
                <span class="text-base font-semibold leading-none text-text tabular-nums normal-case">
                  {{ store.vegasSummary.tickers }}
                </span>
              </div>
              <div class="flex items-baseline gap-2">
                <span>Resonance</span>
                <span
                  class="text-base font-semibold leading-none text-text tabular-nums normal-case"
                >
                  {{ store.vegasSummary.totalResonance }}
                </span>
              </div>
            </div>
          <div class="mt-2 space-y-1 text-[10px] text-muted">
            <div class="flex items-center justify-between">
              <span>{{ automationCountdownLabel }}</span>
              <span class="font-mono text-text">{{ automationCountdownValue }}</span>
            </div>
            <div class="mt-1 h-1.5 w-full rounded-full bg-border/60">
              <div
                class="h-1.5 rounded-full"
                :class="automationCountdownBarClass"
                :style="{ width: `${automationCountdownProgress}%` }"
              ></div>
            </div>
            <div class="text-right">
              {{ vegasLastUpdatedLabel }}
            </div>
          </div>
          </BaseCard>
        </div>

        <div class="mt-3 flex min-h-0 flex-1 flex-col overflow-y-auto pr-1 scrollbar-hidden">
          <div class="space-y-3">
            <BaseCard
              v-for="tickerState in vegasStates"
              :key="tickerState.ticker"
              class="border border-border"
            >
              <div class="flex items-center justify-between">
                <div class="flex items-center gap-2">
                  <span class="font-display text-sm text-text">{{ tickerState.ticker }}</span>
                  <span
                    class="rounded-full border border-border px-2 py-0.5 text-[10px] uppercase tracking-wide"
                    :class="vegasStateBadgeClass(tickerState.state)"
                  >
                    {{ vegasStateLabel(tickerState.state) }}
                  </span>
                </div>
                <span class="text-[11px] text-muted">
                  {{ tickerState.resonance_count || 0 }} resonance
                </span>
              </div>

              <div class="mt-2 grid gap-2 text-[10px] text-muted sm:grid-cols-3">
                <div
                  v-if="tickerState.direction"
                  class="rounded-md border border-border/60 bg-panel/60 px-2 py-1"
                >
                  <div class="text-[9px] uppercase tracking-wide">Direction</div>
                  <div
                    class="text-xs font-semibold leading-tight"
                    :class="directionValueClass(tickerState.direction)"
                  >
                    {{ tickerState.direction }}
                  </div>
                </div>
                <div
                  v-if="tickerState.bb_distance_pct !== null && tickerState.bb_distance_pct !== undefined"
                  class="rounded-md border border-border/60 bg-panel/60 px-2 py-1"
                >
                  <div class="text-[9px] uppercase tracking-wide">BB Dist</div>
                  <div class="text-xs font-semibold leading-tight text-text">
                    {{ formatPercent(tickerState.bb_distance_pct) }}
                  </div>
                </div>
                <div
                  v-if="tickerState.entry_price !== null && tickerState.entry_price !== undefined"
                  class="rounded-md border border-border/60 bg-panel/60 px-2 py-1"
                >
                  <div class="text-[9px] uppercase tracking-wide">Entry</div>
                  <div class="text-xs font-semibold leading-tight text-text">
                    {{ formatPrice(tickerState.entry_price) }}
                  </div>
                </div>
              </div>

              <div v-if="tickerState.entry_time" class="mt-1 text-[10px] text-muted">
                Opened {{ formatTime(tickerState.entry_time) }}
              </div>

              <div v-if="intervalRows(tickerState).length > 0" class="mt-3">
                <div
                  class="flex items-center justify-between text-[9px] uppercase tracking-wide text-muted"
                >
                  <span>Signal Matrix</span>
                  <span>{{ intervalRows(tickerState).length }} intervals</span>
                </div>
                <div
                  class="mt-2 grid grid-cols-[72px_repeat(3,minmax(0,1fr))] gap-2 text-[9px] uppercase tracking-wide text-muted"
                >
                  <span>Interval</span>
                  <span class="text-center">Tunnel</span>
                  <span class="text-center">BB+</span>
                  <span class="text-center">BB-</span>
                </div>
                <div class="mt-2 space-y-1.5">
                  <div
                    v-for="row in intervalRows(tickerState)"
                    :key="`${tickerState.ticker}-${row.interval}`"
                    class="grid grid-cols-[72px_repeat(3,minmax(0,1fr))] items-center gap-2"
                  >
                    <div class="flex items-center gap-2">
                      <span
                        class="h-2 w-1 rounded-full"
                        :class="row.active ? 'bg-accent' : 'bg-border/60'"
                      ></span>
                      <span class="font-mono text-[10px] text-muted">
                        {{ row.interval }}
                      </span>
                    </div>
                    <div
                      class="h-1.5 w-full rounded-full"
                      :class="signalCellClass(row.inTunnel, 'accent')"
                    ></div>
                    <div
                      class="h-1.5 w-full rounded-full"
                      :class="signalCellClass(row.bbUpper, 'warning')"
                    ></div>
                    <div
                      class="h-1.5 w-full rounded-full"
                      :class="signalCellClass(row.bbLower, 'warning')"
                    ></div>
                  </div>
                </div>
              </div>

              <div
                v-if="timerRows(tickerState).length > 0"
                class="mt-3 space-y-3 text-[10px] text-muted"
              >
                <div v-for="timer in timerRows(tickerState)" :key="timer.key">
                  <div class="flex items-center justify-between">
                    <span>{{ timer.label }}</span>
                    <span class="text-text" :class="timer.display ? 'text-[10px]' : 'font-mono'">
                      {{ timer.display ?? formatTimer(timer.remaining) }}
                    </span>
                  </div>
                  <div class="mt-1 h-1.5 w-full rounded-full bg-border/60">
                    <div
                      class="h-1.5 rounded-full"
                      :class="timerBarClass(timer.tone)"
                      :style="{ width: `${timer.progress}%` }"
                    ></div>
                  </div>
                  <div v-if="timer.note" class="mt-1 text-[10px] text-muted">
                    {{ timer.note }}
                  </div>
                </div>
              </div>
            </BaseCard>

            <BaseEmptyState
              v-if="vegasStates.length === 0"
              title="No Vegas state yet"
              subtitle="Run a scan to populate Vegas state data."
            />
          </div>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from "vue";
import BaseBadge from "@/components/BaseBadge.vue";
import BaseCard from "@/components/BaseCard.vue";
import BaseEmptyState from "@/components/BaseEmptyState.vue";
import ScannerCalendar from "@/components/ScannerCalendar.vue";
import ScannerResultChart from "@/components/ScannerResultChart.vue";
import { useScannerEmaStore } from "@/stores/scannerEmaStore";
import type { ScannerChartData, ScannerLog, ScannerResult } from "@/types/scanner";
import type { VegasTickerState } from "@/types/vegas";

defineOptions({ name: "EmaScannerView" });

type StateManagerConfig = {
  min_resonance: number;
  ema_resonance_cooldown_seconds: number;
  bb_rejection_cooldown_seconds: number;
  bb_exit_warning_cooldown_seconds: number;
  position_check_interval_seconds: number;
  bb_rejection_min_touches: number;
  bb_htf_min_interval_minutes: number;
  emit_new_resonance: boolean;
  emit_resonance_increase: boolean;
  emit_structure_shift: boolean;
  emit_resonance_refresh: boolean;
  emit_bb_rejection_upper: boolean;
  emit_bb_rejection_lower: boolean;
  emit_position_management: boolean;
  emit_bb_exit_warning: boolean;
};

const store = useScannerEmaStore();
const newEma = ref<number | null>(null);
const toleranceValue = ref(store.tolerancePct);
const scanFileInput = ref<HTMLInputElement | null>(null);
const automationIsRunning = ref(false);
const automationStateReady = ref(false);
const automationIntervalSeconds = ref<number | null>(null);
const automationLastEmaAt = ref<string | null>(null);
const automationCountdown = ref<number | null>(null);
const automationNextEmaAt = ref<number | null>(null);
const nowTick = ref(Date.now());
let automationPollTimer: ReturnType<typeof setInterval> | null = null;
let automationTickTimer: ReturnType<typeof setInterval> | null = null;
const stateConfig = ref<StateManagerConfig>({
  min_resonance: 2,
  ema_resonance_cooldown_seconds: 600,
  bb_rejection_cooldown_seconds: 1200,
  bb_exit_warning_cooldown_seconds: 600,
  position_check_interval_seconds: 1800,
  bb_rejection_min_touches: 10,
  bb_htf_min_interval_minutes: 480,
  emit_new_resonance: true,
  emit_resonance_increase: true,
  emit_structure_shift: true,
  emit_resonance_refresh: true,
  emit_bb_rejection_upper: true,
  emit_bb_rejection_lower: true,
  emit_position_management: true,
  emit_bb_exit_warning: true,
});
const isSavingStateConfig = ref(false);
const stateConfigError = ref("");
const leftPanelRef = ref<HTMLElement | null>(null);
const leftPanelScrollTop = ref(0);
const logListRef = ref<HTMLElement | null>(null);
const logOverlayRef = ref<HTMLElement | null>(null);
const logListAutoScroll = ref(true);
const logOverlayAutoScroll = ref(true);

const scanButtonLabel = computed(() => {
  if (!automationStateReady.value) return "Checking automation...";
  if (store.isScanning) return "Scanning...";
  if (automationIsRunning.value) return "managed by agent";
  return "Run Scan Once";
});

const isScanDisabled = computed(
  () => !automationStateReady.value || store.isScanning || automationIsRunning.value,
);

const handleScan = () => {
  if (isScanDisabled.value) return;
  void store.runScan();
};

const handleAddEma = () => {
  if (!newEma.value) return;
  store.addEmaLine(newEma.value);
  newEma.value = null;
};

const handleImportClick = () => {
  scanFileInput.value?.click();
};

const handleImportChange = async (event: Event) => {
  const target = event.target as HTMLInputElement | null;
  const file = target?.files?.[0];
  if (!file) return;
  await store.importScanResults(file);
  if (store.selectedDate) {
    await store.loadHistory(store.selectedDate);
  }
  if (target) {
    target.value = "";
  }
};

const handleExport = () => {
  void store.exportScanResults();
};

const handleDeleteResult = async (result: ScannerResult) => {
  if (!result.id) return;
  const confirmed = window.confirm("Delete this scan result?");
  if (!confirmed) return;
  await store.deleteResult(result.id);
};

const handleLogListScroll = () => {
  if (!logListRef.value) return;
  logListAutoScroll.value = logListRef.value.scrollTop <= 0;
};

const handleLogOverlayScroll = () => {
  if (!logOverlayRef.value) return;
  logOverlayAutoScroll.value = logOverlayRef.value.scrollTop <= 0;
};

const scrollLogsToTop = async () => {
  await nextTick();
  if (logListAutoScroll.value && logListRef.value) {
    logListRef.value.scrollTop = 0;
  }
  if (logOverlayAutoScroll.value && logOverlayRef.value) {
    logOverlayRef.value.scrollTop = 0;
  }
};

const resolvePrimaryInterval = (result: ScannerResult) => {
  if (result.intervals?.length) return result.intervals[0];
  if (result.ema_votes?.length) return result.ema_votes[0].interval;
  if (result.bb_votes?.length) return result.bb_votes[0].interval;
  const keys = result.chart_data ? Object.keys(result.chart_data) : [];
  return keys[0] ?? null;
};

const resolveChartData = (result: ScannerResult): ScannerChartData | undefined => {
  const interval = resolvePrimaryInterval(result);
  if (!interval || !result.chart_data) return undefined;
  return result.chart_data[interval];
};

type IntervalRow = {
  interval: string;
  active: boolean;
  inTunnel: boolean;
  bbUpper: boolean;
  bbLower: boolean;
};

type Tone = "accent" | "positive" | "negative" | "warning" | "muted" | "state";

type TimerRow = {
  key: string;
  label: string;
  remaining: number;
  progress: number;
  tone: Tone;
  note?: string;
  display?: string;
};

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

const vegasStates = computed(() => {
  const states = [...store.vegasStates];
  return states.sort((a, b) => {
    const aRes = a.resonance_count || 0;
    const bRes = b.resonance_count || 0;
    const aRank = vegasStateRank(a);
    const bRank = vegasStateRank(b);
    if (aRank !== bRank) return aRank - bRank;
    if (aRank === 1 && aRes !== bRes) return bRes - aRes;
    if (aRank === 0 && aRes !== bRes) return bRes - aRes;
    return a.ticker.localeCompare(b.ticker);
  });
});

const vegasStateRank = (state: VegasTickerState) => {
  if (state.state === "POSITION_ACTIVE") return 0;
  const crossings = state.interval_crossings || {};
  const hasEma =
    (state.resonance_count || 0) > 0 ||
    state.state === "IN_TUNNEL" ||
    Object.values(crossings).some((entry) => entry?.in_tunnel);
  if (hasEma) return 1;
  const timers = state.timers || {};
  const hasBb =
    Boolean(state.bb_rejection_direction) ||
    typeof timers.bb_rejection_remaining_sec === "number" ||
    typeof timers.bb_exit_warning_remaining_sec === "number" ||
    Object.values(crossings).some((entry) => entry?.bb_upper || entry?.bb_lower);
  if (hasBb) return 2;
  return 3;
};

const vegasStatusLabel = computed(() => {
  if (store.isScanning) return "Scanning";
  if (store.vegasSummary.tickers > 0) return "Active";
  return "Idle";
});

const vegasStatusClass = computed(() => {
  if (store.isScanning) return "text-warning";
  if (store.vegasSummary.tickers > 0) return "text-positive";
  return "text-muted";
});

const vegasLastUpdatedLabel = computed(() => {
  if (!store.vegasLastUpdated) return "No updates";
  return `Updated ${formatTime(store.vegasLastUpdated)}`;
});

const htfMinHours = computed({
  get: () => Math.max(1, Math.round((stateConfig.value.bb_htf_min_interval_minutes || 0) / 60)),
  set: (value: number) => {
    const minutes = Math.max(60, Math.round(value) * 60);
    stateConfig.value.bb_htf_min_interval_minutes = minutes;
  },
});

const vegasElapsedSeconds = computed(() => {
  if (!store.vegasLastUpdated) return null;
  const lastMs = Date.parse(store.vegasLastUpdated);
  if (Number.isNaN(lastMs)) return null;
  return Math.max(0, Math.floor((nowTick.value - lastMs) / 1000));
});

const isEmaScanning = computed(
  () => store.isScanning || store.activeCycleNumber !== null,
);

const automationCountdownLabel = computed(() => {
  if (isEmaScanning.value) return "Scanning";
  if (!automationIsRunning.value) return "Automation idle";
  if (automationCountdown.value === null) return "Next EMA scan";
  return "Next EMA scan";
});

const automationCountdownValue = computed(() => {
  if (isEmaScanning.value) return "In progress";
  if (!automationIsRunning.value) return "--";
  if (automationCountdown.value === null) return "--";
  return formatTimer(automationCountdown.value);
});

const automationCountdownProgress = computed(() => {
  if (!automationIsRunning.value) return 0;
  if (isEmaScanning.value) return 100;
  if (automationCountdown.value === null || !automationIntervalSeconds.value) return 0;
  return clampProgress(automationCountdown.value, automationIntervalSeconds.value);
});

const automationCountdownBarClass = computed(() => {
  if (!automationIsRunning.value) return "bg-border/60";
  if (isEmaScanning.value) return "bg-state animate-pulse";
  return "bg-state";
});

const vegasStateLabel = (state: VegasTickerState["state"]) => {
  if (state === "POSITION_ACTIVE") return "Position";
  if (state === "IN_TUNNEL") return "In Tunnel";
  return "Idle";
};

const vegasStateBadgeClass = (state: VegasTickerState["state"]) => {
  if (state === "POSITION_ACTIVE") return "border-positive/40 text-positive bg-positive/10";
  if (state === "IN_TUNNEL") return "border-accent/40 text-accent bg-accent/10";
  return "border-border text-muted bg-surface/50";
};

const directionValueClass = (direction: string) => {
  const value = direction.toUpperCase();
  if (value === "LONG") return "text-positive";
  if (value === "SHORT") return "text-negative";
  return "text-text";
};

const formatPrice = (price: number) => {
  if (Number.isNaN(price)) return "--";
  if (price >= 10000) return `${(price / 1000).toFixed(1)}k`;
  if (price >= 1000) return price.toFixed(0);
  if (price >= 1) return price.toFixed(2);
  return price.toPrecision(4);
};

const formatPercent = (value: number) => `${value.toFixed(2)}%`;

const formatTime = (value: string) => {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleTimeString();
};

const formatLogMessage = (log: ScannerLog, withPrompt = false) => {
  let message = log.message?.trim() || "";
  const data = (log.data || {}) as Record<string, unknown>;

  const asNumber = (value: unknown) => {
    if (typeof value === "number") return value;
    const parsed = Number(value);
    return Number.isNaN(parsed) ? null : parsed;
  };

  const asText = (value: unknown) => (typeof value === "string" ? value : "");

  const formatUsd = (value: unknown) => {
    const num = asNumber(value);
    return num === null ? "--" : num.toFixed(2);
  };

  const formatLengths = (value: unknown) => {
    if (!Array.isArray(value)) return "";
    return value
      .map((item) => {
        const num = asNumber(item);
        return num === null ? "" : `EMA${num}`;
      })
      .filter(Boolean)
      .join(", ");
  };

  if (!message && log.event) {
    switch (log.event) {
      case "scan_init":
        message = "INITIALIZING SCAN PROTOCOL...";
        break;
      case "scan_assets": {
        const assets = data.assets;
        if (Array.isArray(assets) && assets.length) {
          message = `Assets: ${assets.join(", ")}`;
        }
        break;
      }
      case "missing_tolerance": {
        const fallback = asNumber(data.default);
        message = `⚠ WARNING: PROXIMITY parameter not found. Using default ${fallback ?? 0.2}%.`;
        break;
      }
      case "scan_start_asset":
        message = `━━━ Starting scan for ${asText(data.symbol)} (${asText(data.source)}) ━━━`;
        break;
      case "scan_interval_check":
        message = `▸ [${asText(data.interval)}] Checking ${asText(data.symbol)}...`;
        break;
      case "scan_fetch_failed":
        message = `  ✗ Failed to fetch ${asText(data.source)} data for ${asText(data.interval)}. Skipping.`;
        break;
      case "scan_no_price":
        message = `  ⚠ Skipping ${asText(data.interval)}: Current price is NaN/None.`;
        break;
      case "scan_short_series":
        message = `  ⚠ ${asText(data.interval)}: only ${asNumber(data.candles) ?? 0} candles; BB(20) unavailable, EMA limited`;
        break;
      case "scan_skip_ema":
        message = `  ⚠ ${asText(data.interval)}: skipping ${formatLengths(data.lengths) || "EMA lines"} (need >= length candles, have ${asNumber(data.candles) ?? 0})`;
        break;
      case "scan_ema_hit":
        message = `  ✓ [EMA] ${asText(data.interval)} @ EMA-${asNumber(data.length) ?? ""}: Price $${formatUsd(data.price)} near $${formatUsd(data.ema_value)}`;
        break;
      case "scan_skip_bb":
        message = `  ⚠ ${asText(data.interval)}: skipping BB(20) (need >= 20 candles, have ${asNumber(data.candles) ?? 0})`;
        break;
      case "scan_asset_complete":
        message = `━━━ ${asText(data.symbol)} complete: ${asNumber(data.ema_votes) ?? 0} EMA votes, ${asNumber(data.bb_votes) ?? 0} BB votes ━━━`;
        break;
      case "scan_empty_config":
        message = "⚠ Scanner config incomplete. Check assets, intervals, and EMA lines.";
        break;
      case "scan_error": {
        const symbol = asText(data.symbol);
        const error = asText(data.error);
        message = symbol
          ? `✗ ERROR during scan for ${symbol}: ${error}`
          : `✗ ERROR during scan: ${error}`;
        break;
      }
      default:
        message = "";
    }
  }

  if (!message) return "";
  const cycle = asNumber(data.cycle ?? data.cycle_number ?? data.cycleNumber ?? data.cycleIndex);
  if (cycle && cycle > 0) {
    message = `#${cycle} · ${message}`;
  }
  return withPrompt ? `> ${message}` : message;
};

const intervalRows = (state: VegasTickerState): IntervalRow[] => {
  const crossings = state.interval_crossings || {};
  const activeIntervals = state.active_intervals || [];
  const activeSet = new Set(activeIntervals);
  const intervals = new Set([...Object.keys(crossings), ...activeIntervals]);
  const rows = Array.from(intervals).map((interval) => {
    const info = crossings[interval] || {};
    return {
      interval,
      active: activeSet.has(interval),
      inTunnel: Boolean(info.in_tunnel),
      bbUpper: Boolean(info.bb_upper),
      bbLower: Boolean(info.bb_lower),
    };
  });

  return rows
    .filter((row) => row.active || row.inTunnel || row.bbUpper || row.bbLower)
    .sort((a, b) => {
      const aIndex = timeframeOrder.indexOf(a.interval);
      const bIndex = timeframeOrder.indexOf(b.interval);
      return (aIndex === -1 ? 999 : aIndex) - (bIndex === -1 ? 999 : bIndex);
    });
};

const signalCellClass = (active: boolean, tone: Tone) => {
  if (!active) return "bg-border/40";
  if (tone === "positive") return "bg-positive";
  if (tone === "negative") return "bg-negative";
  if (tone === "warning") return "bg-warning";
  if (tone === "accent") return "bg-accent";
  return "bg-border";
};

const clampProgress = (remaining: number, total?: number) => {
  if (!total || total <= 0) return 0;
  return Math.max(0, Math.min(100, (remaining / total) * 100));
};

const formatDuration = (seconds?: number) => {
  if (seconds === null || seconds === undefined) return "--";
  const total = Math.max(0, Math.floor(seconds));
  const mins = Math.floor(total / 60);
  const secs = total % 60;
  if (mins <= 0) return `${secs}s`;
  if (secs <= 0) return `${mins}m`;
  return `${mins}m ${secs}s`;
};

const formatTimer = (seconds?: number) => {
  if (seconds === null || seconds === undefined) return "--";
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, "0")}`;
};

const timerRows = (state: VegasTickerState): TimerRow[] => {
  const timers = state.timers || {};
  const elapsed = vegasElapsedSeconds.value ?? 0;
  const rows: TimerRow[] = [];

  if (typeof timers.position_mgmt_remaining_sec === "number") {
    const remaining = Math.max(0, timers.position_mgmt_remaining_sec - elapsed);
    rows.push({
      key: "position_mgmt",
      label: "Position Check",
      remaining,
      progress: clampProgress(
        remaining,
        timers.position_mgmt_total_sec,
      ),
      tone: "state",
    });
  }

  if (typeof timers.ema_resonance_remaining_sec === "number") {
    const remaining = Math.max(0, timers.ema_resonance_remaining_sec - elapsed);
    rows.push({
      key: "ema_resonance",
      label: "EMA Resonance",
      remaining,
      progress: clampProgress(
        remaining,
        timers.ema_resonance_total_sec,
      ),
      tone: "state",
    });
  }

  if (typeof timers.bb_rejection_remaining_sec === "number") {
    const touchCount = timers.bb_touch_count ?? 0;
    const touchRequired = timers.bb_touch_required ?? 0;
    const touchDirection = timers.bb_touch_direction;
    const directionLabel =
      touchDirection === "UPPER" ? "Upper" : touchDirection === "LOWER" ? "Lower" : "";
    const noteParts = [];
    if (directionLabel) {
      noteParts.push(directionLabel);
    }
    if (touchRequired > 0) {
      noteParts.push(`Touches ${touchCount}/${touchRequired}`);
    }
    const note = noteParts.length ? noteParts.join(" • ") : undefined;
    const remaining = Math.max(0, timers.bb_rejection_remaining_sec - elapsed);
    const waitingForConfirmation =
      remaining === 0 && touchRequired > 0 && touchCount < touchRequired;
    rows.push({
      key: "bb_rejection",
      label: "BB Rejection",
      remaining,
      progress: clampProgress(
        remaining,
        timers.bb_rejection_total_sec,
      ),
      tone: "state",
      note,
      display: waitingForConfirmation ? "Waiting for confirmation" : undefined,
    });
  }

  if (typeof timers.bb_exit_warning_remaining_sec === "number") {
    const remaining = Math.max(0, timers.bb_exit_warning_remaining_sec - elapsed);
    rows.push({
      key: "bb_exit_warning",
      label: "BB Exit Warning",
      remaining,
      progress: clampProgress(
        remaining,
        timers.bb_exit_warning_total_sec,
      ),
      tone: "negative",
    });
  }

  return rows;
};

const timerBarClass = (tone: Tone) => {
  if (tone === "positive") return "bg-positive";
  if (tone === "negative") return "bg-negative";
  if (tone === "warning") return "bg-warning";
  if (tone === "state") return "bg-state";
  if (tone === "accent") return "bg-accent";
  return "bg-border";
};

const updateAutomationCountdown = () => {
  if (!automationIsRunning.value || !automationNextEmaAt.value) {
    automationCountdown.value = null;
    return;
  }
  const remaining = Math.ceil((automationNextEmaAt.value - Date.now()) / 1000);
  automationCountdown.value = Math.max(0, remaining);
};

const computeNextEmaAt = () => {
  if (!automationIsRunning.value || !automationLastEmaAt.value || !automationIntervalSeconds.value) {
    automationNextEmaAt.value = null;
    automationCountdown.value = null;
    return;
  }
  const lastMs = Date.parse(automationLastEmaAt.value);
  if (Number.isNaN(lastMs)) {
    automationNextEmaAt.value = null;
    automationCountdown.value = null;
    return;
  }
  automationNextEmaAt.value = lastMs + automationIntervalSeconds.value * 1000;
  updateAutomationCountdown();
};

const loadAutomationState = async () => {
  try {
    const response = await fetch("/api/v1/automation/state");
    const data = await response.json();
    const payload = data?.data;
    if (!payload) return;
    automationIsRunning.value = Boolean(payload.is_running);
    automationIntervalSeconds.value =
      typeof payload.ema_interval_seconds === "number" ? payload.ema_interval_seconds : null;
    automationLastEmaAt.value = payload.last_ema_cycle_at || null;
    if (typeof payload.ema_cycles === "number") {
      store.setCycleNumber(payload.ema_cycles);
    }
    computeNextEmaAt();
  } catch {
    // Ignore automation state load errors.
  } finally {
    automationStateReady.value = true;
  }
};

const loadStateConfig = async () => {
  stateConfigError.value = "";
  try {
    const res = await fetch("/api/v1/scanner/ema/state/config");
    const data = await res.json().catch(() => null);
    if (!res.ok) {
      const message = data?.error?.message || `Failed to load config (${res.status}).`;
      throw new Error(message);
    }
    const payload = data?.data;
    if (!payload) {
      throw new Error("Failed to load config.");
    }
    const resolveBool = (value: unknown, fallback: boolean) =>
      typeof value === "boolean" ? value : fallback;
    stateConfig.value = {
      min_resonance: Number(payload.min_resonance) || stateConfig.value.min_resonance,
      ema_resonance_cooldown_seconds:
        Number(payload.ema_resonance_cooldown_seconds) ||
        stateConfig.value.ema_resonance_cooldown_seconds,
      bb_rejection_cooldown_seconds:
        Number(payload.bb_rejection_cooldown_seconds) ||
        stateConfig.value.bb_rejection_cooldown_seconds,
      bb_exit_warning_cooldown_seconds:
        Number(payload.bb_exit_warning_cooldown_seconds) ||
        stateConfig.value.bb_exit_warning_cooldown_seconds,
      position_check_interval_seconds:
        Number(payload.position_check_interval_seconds) ||
        stateConfig.value.position_check_interval_seconds,
      bb_rejection_min_touches:
        Number(payload.bb_rejection_min_touches) || stateConfig.value.bb_rejection_min_touches,
      bb_htf_min_interval_minutes:
        Number(payload.bb_htf_min_interval_minutes) ||
        stateConfig.value.bb_htf_min_interval_minutes,
      emit_new_resonance: resolveBool(
        payload.emit_new_resonance,
        stateConfig.value.emit_new_resonance,
      ),
      emit_resonance_increase: resolveBool(
        payload.emit_resonance_increase,
        stateConfig.value.emit_resonance_increase,
      ),
      emit_structure_shift: resolveBool(
        payload.emit_structure_shift,
        stateConfig.value.emit_structure_shift,
      ),
      emit_resonance_refresh: resolveBool(
        payload.emit_resonance_refresh,
        stateConfig.value.emit_resonance_refresh,
      ),
      emit_bb_rejection_upper: resolveBool(
        payload.emit_bb_rejection_upper,
        stateConfig.value.emit_bb_rejection_upper,
      ),
      emit_bb_rejection_lower: resolveBool(
        payload.emit_bb_rejection_lower,
        stateConfig.value.emit_bb_rejection_lower,
      ),
      emit_position_management: resolveBool(
        payload.emit_position_management,
        stateConfig.value.emit_position_management,
      ),
      emit_bb_exit_warning: resolveBool(
        payload.emit_bb_exit_warning,
        stateConfig.value.emit_bb_exit_warning,
      ),
    };
  } catch (err) {
    stateConfigError.value = err instanceof Error ? err.message : "Failed to load config.";
  }
};

const saveStateConfig = async () => {
  isSavingStateConfig.value = true;
  stateConfigError.value = "";
  try {
    const res = await fetch("/api/v1/scanner/ema/state/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(stateConfig.value),
    });
    const data = await res.json();
    if (!res.ok) {
      const message = data?.error?.message || "Failed to save config.";
      throw new Error(message);
    }
    if (data?.data) {
      await loadStateConfig();
    }
  } catch (err) {
    stateConfigError.value = err instanceof Error ? err.message : "Failed to save config.";
  } finally {
    isSavingStateConfig.value = false;
  }
};

watch(
  () => store.tolerancePct,
  (value) => {
    toleranceValue.value = value;
  },
);

watch(
  () => store.logs.length,
  () => {
    void scrollLogsToTop();
  },
);

onMounted(() => {
  store.loadConfig();
  store.loadCalendar();
  store.loadVegasState();
  void loadStateConfig();
  void loadAutomationState();
  automationPollTimer = setInterval(loadAutomationState, 15000);
  automationTickTimer = setInterval(() => {
    nowTick.value = Date.now();
    updateAutomationCountdown();
  }, 1000);
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
  if (automationPollTimer) {
    clearInterval(automationPollTimer);
    automationPollTimer = null;
  }
  if (automationTickTimer) {
    clearInterval(automationTickTimer);
    automationTickTimer = null;
  }
});
</script>

<style scoped>
.log-overlay-enter-active,
.log-overlay-leave-active {
  transition: opacity 160ms ease;
}

.log-overlay-enter-from,
.log-overlay-leave-to {
  opacity: 0;
}

.log-overlay-enter-active .log-panel,
.log-overlay-leave-active .log-panel {
  transition: transform 180ms ease, opacity 180ms ease;
}

.log-overlay-enter-from .log-panel,
.log-overlay-leave-to .log-panel {
  opacity: 0;
  transform: translateY(6px) scale(0.98);
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 160ms ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

</style>
