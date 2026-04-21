<!--
  AutomationView.vue
  ==================
  Main control panel for the autonomous trading pipeline.

  This is the primary operator interface. It provides:
  - Session controls for prompt_test / dry_run / production execution modes
  - AI configuration and prompt mapping controls
  - Live automation log and queue-stage visibility
  - Position monitoring with real-time PnL and trade history
  - Session replay hooks through the shared automation and agent stores

  Data flow:
  Pinia stores <-> Socket.IO services <-> FastAPI backend <-> queue workers / event bus
-->
<template>
  <div class="flex h-full min-h-0 flex-1 flex-col gap-3 overflow-hidden">
    <div
      class="grid min-h-0 flex-1 gap-4 overflow-hidden xl:grid-cols-[280px_minmax(0,0.8fr)_minmax(0,1.5fr)] xl:grid-rows-[auto_minmax(0,1fr)]"
    >
      <div class="col-span-full flex flex-wrap items-center justify-between gap-2 xl:col-span-2">
        <h1 class="font-display text-xl">Automation</h1>
        <div class="flex flex-wrap items-center gap-2">
          <BaseBadge>Mode: {{ executionModeLabel }}</BaseBadge>
          <BaseBadge>Socket: {{ store.isConnected ? "Live" : "Idle" }}</BaseBadge>
          <BaseBadge>{{ promptRateLabel }}</BaseBadge>
        </div>
      </div>

      <aside class="flex h-full min-h-0 flex-col gap-3 overflow-hidden xl:row-start-2">
        <div class="flex flex-col gap-3">
          <BaseCard>
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <span
                  class="h-2 w-2 rounded-full"
                  :class="
                    store.status.isRunning
                      ? 'bg-warning'
                      : store.isConnected
                        ? 'bg-accent'
                        : 'bg-muted'
                  "
                ></span>
                <span class="font-display text-sm">Control</span>
              </div>
              <span
                class="text-[10px] uppercase tracking-wide"
                :class="store.status.isRunning ? 'text-warning' : 'text-muted'"
              >
                {{ store.status.isRunning ? "Running" : "Idle" }}
              </span>
            </div>
            <div class="mt-3 flex flex-wrap items-center gap-2">
              <button
                class="group relative flex-1 overflow-hidden rounded-md border border-border bg-panel px-3 py-2 text-xs font-semibold text-muted shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-accent/60 hover:text-text hover:shadow-md active:translate-y-0 active:scale-[0.99] disabled:opacity-50"
                type="button"
                :disabled="isStarting || isStopping"
                @click="handleToggle"
              >
                <span
                  class="pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-300 group-hover:opacity-100"
                >
                  <span
                    class="absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(94,234,212,0.18),transparent_55%)]"
                  ></span>
                  <span
                    class="absolute -left-1/3 top-0 h-full w-1/2 bg-white/10 blur-sm transition-transform duration-500 group-hover:translate-x-[220%]"
                  ></span>
                </span>
                <span class="relative z-10 tracking-wide">
                  {{ store.status.isRunning ? "Stop" : "Start" }}
                </span>
              </button>
              <button
                class="rounded-md border border-negative/40 bg-negative/10 px-3 py-2 text-xs text-negative hover:text-negative/80 disabled:opacity-50"
                type="button"
                :disabled="isStopping"
                @click="handleEmergencyStop"
              >
                Emergency
              </button>
            </div>
            <div v-if="missingProviderModel" class="mt-2 text-[11px] text-warning">
              Select a provider and model before starting automation.
            </div>
            <div class="mt-3 flex items-center justify-between text-[11px] text-muted">
              <span>Cycle</span>
              <span class="font-mono text-text">#{{ store.status.currentCycle }}</span>
            </div>
          </BaseCard>
        </div>

        <div
          ref="leftPanelRef"
          class="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto pr-1 scrollbar-hidden"
        >
          <BaseCard>
            <div class="flex items-center justify-between gap-2">
              <div>
                <div class="text-xs uppercase tracking-wide text-muted">Trading API</div>
                <div class="text-[11px] text-muted">Active exchange status</div>
              </div>
              <span class="h-2 w-2 rounded-full" :class="tradingStatusDotClass"></span>
            </div>
            <div class="mt-3">
              <div class="font-display text-sm text-text">{{ tradingApiStatus.label }}</div>
              <div class="text-[11px] text-muted">{{ tradingApiStatus.detail || "No account selected" }}</div>
              <div v-if="tradingApiStatus.isTestnet" class="mt-1 text-[10px] text-warning">
                Testnet
              </div>
            </div>
          </BaseCard>

          <BaseCard>
            <div class="text-xs uppercase tracking-wide text-muted">Execution Mode</div>
            <div class="mt-3 grid gap-2">
              <label
                v-for="mode in executionModes"
                :key="mode.value"
                class="flex items-center justify-between rounded-md border border-border bg-panel/50 px-3 py-2 text-xs text-muted"
              >
                <span class="font-display text-sm text-text">{{ mode.label }}</span>
                <input
                  type="radio"
                  name="execution-mode"
                  :value="mode.value"
                  v-model="executionModeSelection"
                  @change="setExecutionMode(mode.value)"
                />
              </label>
            </div>
          </BaseCard>

          <BaseCard>
            <div class="text-xs uppercase tracking-wide text-muted">Scanner Intervals</div>
            <div class="mt-3 space-y-3 text-[11px] text-muted">
              <label class="space-y-2">
                <div class="flex items-center justify-between">
                  <span class="font-display text-sm text-text">EMA Scanner</span>
                  <span class="font-mono text-text">{{ automationConfig.ema_interval_seconds }}s</span>
                </div>
                <input
                  v-model.number="automationConfig.ema_interval_seconds"
                  class="w-full"
                  type="range"
                  min="5"
                  max="300"
                  step="5"
                  @change="updateConfigPersisted({ ema_interval_seconds: automationConfig.ema_interval_seconds })"
                />
              </label>
              <label class="space-y-2">
                <div class="flex items-center justify-between">
                  <span class="font-display text-sm text-text">Quant Scanner</span>
                  <span class="font-mono text-text">{{ automationConfig.quant_interval_seconds }}s</span>
                </div>
                <input
                  v-model.number="automationConfig.quant_interval_seconds"
                  class="w-full"
                  type="range"
                  min="5"
                  max="300"
                  step="5"
                  @change="updateConfigPersisted({ quant_interval_seconds: automationConfig.quant_interval_seconds })"
                />
              </label>
            </div>
          </BaseCard>

          <BaseCard>
            <div class="text-xs uppercase tracking-wide text-muted">AI Settings</div>
            <div class="mt-3 space-y-3">
              <label class="text-[11px] text-muted">
                Provider
                <select
                  class="mt-2 w-full rounded-md border border-border bg-panel px-3 py-2 text-xs text-text"
                  :value="automationConfig.provider"
                  @change="handleProviderChange"
                >
                  <option value="">Select provider</option>
                  <option
                    v-for="provider in providers"
                    :key="provider.name"
                    :value="provider.name"
                  >
                    {{ providerLabel(provider) }}
                  </option>
                </select>
              </label>

              <label class="text-[11px] text-muted">
                Model
                <input
                  class="mt-2 w-full rounded-md border border-border bg-panel px-3 py-2 text-xs text-text"
                  :value="automationConfig.model"
                  :list="automationConfig.provider ? `automation-models-${automationConfig.provider}` : undefined"
                  type="text"
                  placeholder="Enter model or pick a suggestion"
                  spellcheck="false"
                  autocomplete="off"
                  @input="handleModelChange"
                />
                <datalist
                  v-if="automationConfig.provider"
                  :id="`automation-models-${automationConfig.provider}`"
                >
                  <option
                    v-for="model in availableModels"
                    :key="modelKey(model)"
                    :value="modelValue(model)"
                  />
                </datalist>
                <div class="mt-2 flex flex-wrap gap-2" v-if="availableModels.length > 0">
                  <button
                    v-for="model in availableModels"
                    :key="modelKey(model)"
                    class="rounded-md border px-2 py-1 text-[11px] transition"
                    :class="
                      modelValue(model) === automationConfig.model
                        ? 'border-accent/60 bg-accent/10 text-text'
                        : 'border-border bg-panel text-muted hover:text-text'
                    "
                    type="button"
                    @click="selectModel(modelValue(model))"
                  >
                    {{ modelLabel(model) }}
                  </button>
                </div>
                <p class="mt-2 text-[10px] text-muted">
                  Supports provider-listed models and manual entries saved from AI Settings.
                </p>
              </label>

              <label v-if="showCodexReasoningEffort" class="text-[11px] text-muted">
                Reasoning Strength
                <select
                  class="mt-2 w-full rounded-md border border-border bg-panel px-3 py-2 text-xs text-text"
                  :value="automationConfig.reasoning_effort"
                  @change="handleReasoningEffortChange"
                >
                  <option
                    v-for="option in codexReasoningOptions"
                    :key="option.value"
                    :value="option.value"
                  >
                    {{ option.label }}
                  </option>
                </select>
              </label>

              <label
                class="flex items-center justify-between rounded-md border border-border bg-panel/50 px-3 py-2 text-[11px] text-muted"
              >
                <div>
                  <div class="text-text">Add 15m Timing Chart</div>
                  <div class="text-[10px] text-muted">
                    Applies to all prompts, including position management.
                  </div>
                </div>
                <input
                  v-model="automationConfig.include_entry_timing_15m_chart"
                  type="checkbox"
                  @change="
                    updateConfigPersisted({
                      include_entry_timing_15m_chart:
                        automationConfig.include_entry_timing_15m_chart,
                    })
                  "
                />
              </label>

              <label
                class="flex items-center justify-between rounded-md border border-border bg-panel/50 px-3 py-2 text-[11px] text-muted"
              >
                <div>
                  <div class="text-text">Use All Monitored Interval Charts</div>
                  <div class="text-[10px] text-muted">
                    When enabled, prompts include charts for every monitored interval instead of only the event-selected intervals.
                  </div>
                </div>
                <input
                  v-model="automationConfig.use_all_monitored_interval_charts"
                  type="checkbox"
                  @change="
                    updateConfigPersisted({
                      use_all_monitored_interval_charts:
                        automationConfig.use_all_monitored_interval_charts,
                    })
                  "
                />
              </label>

              <label
                class="flex items-center justify-between rounded-md border border-border bg-panel/50 px-3 py-2 text-[11px] text-muted"
              >
                <div>
                  <div class="text-text">Reverse Order (Parse Stage)</div>
                  <div class="text-[10px] text-muted">
                    Flip OPEN_LONG/OPEN_SHORT before trade guard checks.
                  </div>
                </div>
                <input
                  v-model="automationConfig.reverse_order_enabled"
                  type="checkbox"
                  @change="
                    updateConfigPersisted({
                      reverse_order_enabled: automationConfig.reverse_order_enabled,
                    })
                  "
                />
              </label>

              <div class="space-y-2">
                <div class="text-[10px] uppercase tracking-wide text-muted">
                  Vegas Prompt Mapping
                </div>
                <label
                  v-for="mapping in vegasPromptMappings"
                  :key="mapping.key"
                  class="text-[11px] text-muted"
                >
                  {{ mapping.label }}
                  <select
                    class="mt-2 w-full rounded-md border border-border bg-panel px-3 py-2 text-xs text-text"
                    :value="vegasPromptValue(mapping.key)"
                    @change="(event) => handleVegasPromptChange(mapping.key, event)"
                  >
                    <option value="">Default</option>
                    <option
                      v-for="config in promptConfigs"
                      :key="config.id"
                      :value="config.id"
                    >
                      {{ config.name }}
                    </option>
                  </select>
                </label>
              </div>

            </div>
          </BaseCard>

          <BaseCard>
            <div class="text-xs uppercase tracking-wide text-muted">Trade Guard</div>
            <div class="mt-1 text-[10px] text-muted">
              Exposure (Risk Config): {{ riskExposureLabel }} · Max Margin: {{ formatUsd(riskExposureUsd) }}
            </div>
            <div class="mt-3 space-y-3 text-[11px] text-muted">
              <label>
                Min Confidence
                <div class="mt-2 flex items-center justify-between">
                  <input
                    v-model.number="tradeGuardConfig.min_confidence"
                    class="w-full"
                    type="range"
                    min="0"
                    max="100"
                    step="5"
                    @change="updateTradeGuardConfigPersisted({ min_confidence: tradeGuardConfig.min_confidence })"
                  />
                </div>
                <span class="mt-1 inline-flex text-[10px] text-muted">
                  {{ tradeGuardConfig.min_confidence }}%
                </span>
              </label>

              <div class="grid grid-cols-2 gap-2">
                <label>
                  SL Min (%)
                  <input
                    v-model.number="tradeGuardConfig.sl_min_roe_pct"
                    class="mt-2 w-full rounded-md border border-border bg-panel px-2 py-1 text-xs text-text"
                    type="number"
                    min="0"
                    step="0.5"
                    @change="updateTradeGuardConfigPersisted({ sl_min_roe_pct: tradeGuardConfig.sl_min_roe_pct })"
                  />
                </label>
                <label>
                  SL Max (%)
                  <input
                    v-model.number="tradeGuardConfig.sl_max_roe_pct"
                    class="mt-2 w-full rounded-md border border-border bg-panel px-2 py-1 text-xs text-text"
                    type="number"
                    min="0"
                    step="0.5"
                    @change="updateTradeGuardConfigPersisted({ sl_max_roe_pct: tradeGuardConfig.sl_max_roe_pct })"
                  />
                </label>
              </div>

              <div class="grid grid-cols-2 gap-2">
                <label>
                  TP Min (%)
                  <input
                    v-model.number="tradeGuardConfig.tp_min_roe_pct"
                    class="mt-2 w-full rounded-md border border-border bg-panel px-2 py-1 text-xs text-text"
                    type="number"
                    min="0"
                    step="0.5"
                    @change="updateTradeGuardConfigPersisted({ tp_min_roe_pct: tradeGuardConfig.tp_min_roe_pct })"
                  />
                </label>
                <label>
                  TP Max (%)
                  <input
                    v-model.number="tradeGuardConfig.tp_max_roe_pct"
                    class="mt-2 w-full rounded-md border border-border bg-panel px-2 py-1 text-xs text-text"
                    type="number"
                    min="0"
                    step="0.5"
                    @change="updateTradeGuardConfigPersisted({ tp_max_roe_pct: tradeGuardConfig.tp_max_roe_pct })"
                  />
                </label>
              </div>

              <label>
                Dust Threshold (USD)
                <input
                  v-model.number="tradeGuardConfig.dust_threshold_usd"
                  class="mt-2 w-full rounded-md border border-border bg-panel px-2 py-1 text-xs text-text"
                  type="number"
                  min="0"
                  step="1"
                  @change="
                    updateTradeGuardConfigPersisted({
                      dust_threshold_usd: tradeGuardConfig.dust_threshold_usd,
                    })
                  "
                />
              </label>

              <label class="space-y-2">
                <div class="flex items-center justify-between">
                  <span class="text-text">Limit Entry Timeout</span>
                  <span class="font-mono text-text">{{ pendingEntryTimeoutMinutes }}m</span>
                </div>
                <input
                  v-model.number="automationConfig.pending_entry_timeout_seconds"
                  class="w-full"
                  type="range"
                  min="300"
                  max="7200"
                  step="300"
                  @change="
                    updateConfigPersisted({
                      pending_entry_timeout_seconds:
                        automationConfig.pending_entry_timeout_seconds,
                    })
                  "
                />
                <p class="text-[10px] text-muted">
                  Resting limit entries auto-cancel after this window.
                </p>
              </label>
            </div>

            <div class="mt-4">
              <div class="text-[10px] uppercase tracking-wide text-muted">Position Size Tiers</div>
              <div class="mt-2 space-y-2 text-[11px] text-muted">
                <div
                  v-for="(range, index) in tradeGuardConfig.position_tier_ranges"
                  :key="`tier-${range.tier}-${index}`"
                  class="grid grid-cols-[44px_1fr_1fr_auto] items-end gap-2"
                >
                  <label class="text-[10px] text-muted">
                    Tier
                    <input
                      v-model.number="range.tier"
                      class="mt-1 w-full rounded-md border border-border bg-panel px-2 py-1 text-xs text-text"
                      type="number"
                      min="1"
                      step="1"
                      @change="handleTierRangesChanged"
                    />
                  </label>
                  <label class="text-[10px] text-muted">
                    Min %
                    <input
                      v-model.number="range.min_pct"
                      class="mt-1 w-full rounded-md border border-border bg-panel px-2 py-1 text-xs text-text"
                      type="number"
                      min="0"
                      max="100"
                      step="1"
                      @change="handleTierRangesChanged"
                    />
                  </label>
                  <label class="text-[10px] text-muted">
                    Max %
                    <input
                      v-model.number="range.max_pct"
                      class="mt-1 w-full rounded-md border border-border bg-panel px-2 py-1 text-xs text-text"
                      type="number"
                      min="0"
                      max="100"
                      step="1"
                      @change="handleTierRangesChanged"
                    />
                  </label>
                  <button
                    class="rounded-md border border-border bg-panel px-2 py-1 text-[10px] text-muted hover:text-negative"
                    type="button"
                    @click="removePositionTierRange(index)"
                  >
                    x
                  </button>
                </div>
                <button
                  class="w-full rounded-md border border-border bg-panel px-2 py-1 text-[11px] text-muted hover:text-text"
                  type="button"
                  @click="addPositionTierRange"
                >
                  Add Tier Range
                </button>
              </div>
            </div>

            <div class="mt-4">
              <div class="text-[10px] uppercase tracking-wide text-muted">Leverage Tiers</div>
              <div class="mt-2 space-y-2 text-[11px] text-muted">
                <label>
                  Default Leverage
                  <div class="mt-1 flex items-center justify-between">
                    <span class="text-[10px] text-muted">
                      {{ tradeGuardConfig.default_leverage }}x
                    </span>
                  </div>
                  <input
                    v-model.number="tradeGuardConfig.default_leverage"
                    class="mt-2 w-full"
                    type="range"
                    min="1"
                    max="5"
                    step="1"
                    @change="
                      updateTradeGuardConfigPersisted({
                        default_leverage: tradeGuardConfig.default_leverage,
                      })
                    "
                  />
                  <p class="mt-1 text-[10px] text-muted">
                    Used when a symbol is not in the tiers.
                  </p>
                </label>
                <div
                  v-for="(tier, index) in tradeGuardConfig.leverage_tiers"
                  :key="`lev-${tier.leverage}-${index}`"
                  class="rounded-md border border-border bg-panel/50 p-2"
                >
                  <div class="flex items-center justify-between gap-2">
                    <label class="text-[10px] text-muted">
                      Leverage
                      <input
                        v-model.number="tier.leverage"
                        class="mt-1 w-full rounded-md border border-border bg-panel px-2 py-1 text-xs text-text"
                        type="number"
                        min="1"
                        step="1"
                        @change="handleLeverageTiersChanged"
                      />
                    </label>
                    <button
                      class="rounded-md border border-border bg-panel px-2 py-1 text-[10px] text-muted hover:text-negative"
                      type="button"
                      @click="removeLeverageTier(index)"
                    >
                      x
                    </button>
                  </div>
                  <label class="mt-2 block text-[10px] text-muted">
                    Symbols (comma separated)
                    <input
                      class="mt-1 w-full rounded-md border border-border bg-panel px-2 py-1 text-xs text-text"
                      type="text"
                      :value="symbolsLabel(tier.symbols)"
                      placeholder="BTC, ETH, SOL"
                      @change="(event) => updateLeverageSymbols(index, event)"
                    />
                  </label>
                </div>
                <button
                  class="w-full rounded-md border border-border bg-panel px-2 py-1 text-[11px] text-muted hover:text-text"
                  type="button"
                  @click="addLeverageTier"
                >
                  Add Leverage Tier
                </button>
              </div>
            </div>
          </BaseCard>

          <BaseCard>
            <div class="flex items-center justify-between gap-2">
              <div>
                <div class="text-xs uppercase tracking-wide text-muted">Circuit Breaker</div>
                <div class="text-[11px] text-muted">Risk guardrails</div>
              </div>
              <span class="text-[10px] uppercase tracking-wide" :class="circuitBreakerStatusClass">
                {{ circuitBreakerStatusLabel }}
              </span>
            </div>
            <div v-if="store.status.circuitBreakerReason" class="mt-2 text-[11px] text-negative">
              {{ store.status.circuitBreakerReason }}
            </div>
            <div class="mt-3 space-y-2 text-[11px] text-muted">
              <div class="flex items-center justify-between">
                <span>Daily Loss</span>
                <span class="font-mono text-text">
                  {{ formatUsd(circuitBreakerState.daily_loss_usd) }}
                </span>
              </div>
              <div class="flex items-center justify-between">
                <span>Max Daily Loss</span>
                <span class="font-mono text-text">
                  {{ formatUsd(circuitBreakerConfig.max_daily_loss_usd) }}
                </span>
              </div>
              <div class="flex items-center justify-between">
                <span>Max Exposure</span>
                <span class="font-mono text-text">
                  {{ circuitBreakerConfig.max_total_exposure_pct }}%
                </span>
              </div>
              <div class="flex items-center justify-between">
                <span>Cooldown Until</span>
                <span class="font-mono text-text">
                  {{ formatDateTime(circuitBreakerState.cooldown_until) }}
                </span>
              </div>
            </div>
            <div class="mt-3 space-y-3">
              <label
                class="flex items-center justify-between rounded-md border border-border bg-panel/50 px-3 py-2 text-[11px] text-muted"
              >
                <span>Enable % limits (loss + exposure)</span>
                <input
                  v-model="circuitBreakerConfig.enable_pct_limits"
                  type="checkbox"
                  @change="
                    updateCircuitBreaker({
                      enable_pct_limits: circuitBreakerConfig.enable_pct_limits,
                    })
                  "
                />
              </label>
              <label class="text-[11px] text-muted">
                Max Consecutive Losses
                <div class="mt-1 flex items-center justify-between">
                  <span class="text-[10px] text-muted">{{ circuitBreakerConfig.max_consecutive_losses }}</span>
                </div>
                <input
                  v-model.number="circuitBreakerConfig.max_consecutive_losses"
                  class="mt-2 w-full"
                  type="range"
                  min="1"
                  max="10"
                  step="1"
                  @change="updateCircuitBreaker({ max_consecutive_losses: circuitBreakerConfig.max_consecutive_losses })"
                />
              </label>
              <label class="text-[11px] text-muted">
                Cooldown Minutes
                <div class="mt-1 flex items-center justify-between">
                  <span class="text-[10px] text-muted">{{ circuitBreakerConfig.cooldown_minutes }}m</span>
                </div>
                <input
                  v-model.number="circuitBreakerConfig.cooldown_minutes"
                  class="mt-2 w-full"
                  type="range"
                  min="5"
                  max="240"
                  step="5"
                  @change="updateCircuitBreaker({ cooldown_minutes: circuitBreakerConfig.cooldown_minutes })"
                />
              </label>
              <label class="text-[11px] text-muted">
                Max Positions
                <div class="mt-1 flex items-center justify-between">
                  <span class="text-[10px] text-muted">{{ automationConfig.max_positions }}</span>
                </div>
                <input
                  v-model.number="automationConfig.max_positions"
                  class="mt-2 w-full"
                  type="range"
                  min="1"
                  max="10"
                  step="1"
                  @change="updateConfigPersisted({ max_positions: automationConfig.max_positions })"
                />
              </label>
            </div>
          </BaseCard>

          <BaseCard>
            <div class="text-xs uppercase tracking-wide text-muted">Auto-Add</div>
            <div class="mt-1 text-[10px] text-muted">
              Server-managed position scaling using fixed 15m ATR(14).
            </div>
            <div class="mt-3 space-y-3 text-[11px] text-muted">
              <label
                class="flex items-center justify-between rounded-md border border-border bg-panel/50 px-3 py-2 text-[11px] text-muted"
              >
                <div>
                  <div class="text-text">Enable Auto-Add</div>
                  <div class="text-[10px] text-muted">
                    Scale into automation-owned winners only.
                  </div>
                </div>
                <input
                  v-model="automationConfig.auto_add_enabled"
                  type="checkbox"
                  @change="
                    updateConfigPersisted({
                      auto_add_enabled: automationConfig.auto_add_enabled,
                    })
                  "
                />
              </label>

              <label class="space-y-2">
                <div class="flex items-center justify-between">
                  <span class="font-display text-sm text-text">ATR Multiple</span>
                  <span class="font-mono text-text">
                    {{ automationConfig.auto_add_trigger_atr_multiple.toFixed(2) }}x
                  </span>
                </div>
                <input
                  v-model.number="automationConfig.auto_add_trigger_atr_multiple"
                  class="w-full"
                  type="range"
                  min="0.25"
                  max="3"
                  step="0.05"
                  @change="
                    updateConfigPersisted({
                      auto_add_trigger_atr_multiple:
                        automationConfig.auto_add_trigger_atr_multiple,
                    })
                  "
                />
              </label>

              <label class="space-y-2">
                <div class="flex items-center justify-between">
                  <span class="font-display text-sm text-text">Tranche Margin</span>
                  <span class="font-mono text-text">{{ autoAddTrancheMarginPctDisplay }}%</span>
                </div>
                <input
                  v-model.number="automationConfig.auto_add_tranche_margin_pct"
                  class="w-full"
                  type="range"
                  min="0.1"
                  max="1"
                  step="0.05"
                  @change="
                    updateConfigPersisted({
                      auto_add_tranche_margin_pct:
                        automationConfig.auto_add_tranche_margin_pct,
                    })
                  "
                />
              </label>

              <label class="space-y-2">
                <div class="flex items-center justify-between">
                  <span class="font-display text-sm text-text">Max Tranches</span>
                  <span class="font-mono text-text">{{ automationConfig.auto_add_max_tranches }}</span>
                </div>
                <input
                  v-model.number="automationConfig.auto_add_max_tranches"
                  class="w-full"
                  type="range"
                  min="1"
                  max="5"
                  step="1"
                  @change="
                    updateConfigPersisted({
                      auto_add_max_tranches: automationConfig.auto_add_max_tranches,
                    })
                  "
                />
              </label>
            </div>
          </BaseCard>

          <div v-if="configError" class="text-xs text-negative">
            {{ configError }}
          </div>
        </div>
      </aside>

      <section class="flex h-full min-h-0 flex-col overflow-hidden xl:row-start-2">
        <BaseCard class="flex min-h-0 flex-1 flex-col">
          <div class="flex items-center justify-between">
            <span class="font-display text-sm">Automation Log</span>
            <div class="flex items-center gap-2 text-[11px] text-muted">
              <button
                class="rounded-md border border-border bg-panel px-2 py-1 text-[11px] text-muted hover:text-text"
                type="button"
                @click="openSessionModal"
              >
                Session History
              </button>
              <select
                v-model="logFilter"
                class="rounded-md border border-border bg-panel px-2 py-1 text-[11px] text-muted"
              >
                <option value="all">All</option>
                <option value="system">System</option>
                <option value="scanner">Scanner</option>
                <option value="state">State Manager</option>
                <option value="prompt">Prompt Builder</option>
                <option value="llm">LLM</option>
                <option value="parser">Response Parser</option>
                <option value="guard">Trade Guard</option>
                <option value="circuit">Circuit Breaker</option>
                <option value="execution">Trade Execution</option>
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
            ref="automationLogRef"
            class="mt-4 min-h-0 flex-1 space-y-1 overflow-y-auto pr-0 text-xs scrollbar-hidden"
            @scroll="handleAutomationLogScroll"
          >
            <div
              v-for="log in filteredLogs"
              :key="log.id || `${log.created_at}-${log.cycle_number}`"
              class="rounded-md border border-border bg-panel/60 px-2 py-1.5"
            >
              <div class="flex items-center justify-between text-[10px] uppercase tracking-wide text-muted">
                <div class="flex items-center gap-2">
                  <span class="rounded-md border border-border/60 bg-panel/70 px-2 py-0.5 font-mono text-[10px] text-text">
                    {{ formatTimestamp(log.created_at) }}
                  </span>
                  <span v-if="log.cycle_number" class="text-[10px] text-muted">
                    Cycle #{{ log.cycle_number }}
                  </span>
                </div>
                <div class="flex items-center gap-2">
                  <template v-if="logTypeKey(log) === 'scanner'">
                    <span class="rounded-full border border-scanner/40 bg-scanner/10 px-2 py-0.5 text-scanner">
                      SCANNER
                    </span>
                  </template>
                  <template v-else-if="logTypeKey(log) === 'state'">
                    <span class="rounded-full border border-state/40 bg-state/10 px-2 py-0.5 text-state">
                      STATE
                    </span>
                  </template>
                  <template v-else-if="logTypeKey(log) === 'prompt'">
                    <span class="rounded-full border border-prompt/40 bg-prompt/10 px-2 py-0.5 text-prompt">
                      PROMPT
                    </span>
                  </template>
                  <template v-else-if="logTypeKey(log) === 'llm'">
                    <span class="rounded-full border border-llm/40 bg-llm/10 px-2 py-0.5 text-llm">
                      LLM
                    </span>
                  </template>
                  <template v-else-if="logTypeKey(log) === 'parser'">
                    <span class="rounded-full border border-parser/40 bg-parser/10 px-2 py-0.5 text-parser">
                      PARSER
                    </span>
                  </template>
                  <template v-else-if="logTypeKey(log) === 'guard'">
                    <span class="rounded-full border border-guard/40 bg-guard/10 px-2 py-0.5 text-guard">
                      GUARD
                    </span>
                  </template>
                  <template v-else-if="logTypeKey(log) === 'circuit'">
                    <span class="rounded-full border border-circuit/40 bg-circuit/10 px-2 py-0.5 text-circuit">
                      CIRCUIT
                    </span>
                  </template>
                  <template v-else-if="logTypeKey(log) === 'execution'">
                    <span
                      class="rounded-full border border-execution/40 bg-execution/10 px-2 py-0.5 text-execution"
                    >
                      EXECUTION
                    </span>
                  </template>
                  <template v-else>
                    <span class="rounded-full border border-border bg-panel px-2 py-0.5 text-muted">
                      {{ (log.log_type || "system").toUpperCase() }}
                    </span>
                  </template>
                </div>
              </div>
              <div class="mt-1 whitespace-pre-wrap break-words text-xs" :class="logMessageClass(log)">
                {{ logMessage(log) }}
              </div>
              <pre
                v-if="isPromptLog(log)"
                class="mt-2 max-h-64 overflow-y-auto rounded-md border border-border bg-surface/60 p-3 font-mono text-[11px] leading-relaxed text-text scrollbar-hidden [tab-size:2] whitespace-pre-wrap break-words"
              >{{ promptText(log) }}</pre>
              <pre
                v-if="isLlmResponseLog(log)"
                class="mt-2 max-h-64 overflow-y-auto rounded-md border border-border bg-surface/60 p-3 font-mono text-[11px] leading-relaxed text-text scrollbar-hidden [tab-size:2] whitespace-pre-wrap break-words"
              >{{ llmResponseText(log) }}</pre>
              <pre
                v-if="isLlmParseLog(log)"
                class="mt-2 max-h-64 overflow-y-auto rounded-md border border-border bg-surface/60 p-3 font-mono text-[11px] leading-relaxed text-text scrollbar-hidden [tab-size:2] whitespace-pre-wrap break-words"
              >{{ llmParseText(log) }}</pre>
              <pre
                v-if="isDetailLog(log)"
                class="mt-2 max-h-64 overflow-y-auto rounded-md border border-border bg-surface/60 p-3 font-mono text-[11px] leading-relaxed text-text scrollbar-hidden [tab-size:2] whitespace-pre-wrap break-words"
              >{{ detailText(log) }}</pre>
            </div>

            <BaseEmptyState
              v-if="filteredLogs.length === 0"
              title="No logs yet"
              subtitle="Automation activity will appear here."
            />
          </div>
        </BaseCard>
      </section>

      <aside class="flex h-full min-h-0 flex-col gap-3 overflow-hidden xl:row-span-2 xl:row-start-1">
        <BaseCard class="flex min-h-0 flex-1 flex-col">
          <div class="flex flex-wrap items-center justify-between gap-2 min-h-[60px]">
            <div>
              <div class="font-display text-sm">
                {{ activeChart === "equity" ? "Equity Curve" : "Position Chart" }}
              </div>
              <div class="text-[11px] text-muted">
                {{ activeChart === "equity" ? "Last 30 days snapshot" : positionChartSubtitle }}
              </div>
            </div>
            <div class="flex items-center gap-2">
              <div class="flex overflow-hidden rounded-md border border-border text-[10px] uppercase tracking-wide">
                <button
                  class="px-3 py-1 text-[11px] transition"
                  :class="activeChart === 'equity' ? 'bg-accent text-text' : 'bg-panel text-muted'"
                  type="button"
                  @click="setActiveChart('equity')"
                >
                  Equity
                </button>
                <button
                  class="px-3 py-1 text-[11px] transition disabled:cursor-not-allowed disabled:opacity-50"
                  :class="
                    activeChart === 'position'
                      ? 'bg-accent text-text'
                      : positionChartAvailable
                        ? 'bg-panel text-muted'
                        : 'bg-panel text-muted/60'
                  "
                  type="button"
                  :disabled="!positionChartAvailable"
                  @click="setActiveChart('position')"
                >
                  Positions
                </button>
              </div>
              <span class="text-[11px] text-muted">
                {{ activeChart === "equity" ? equityStatusLabel : positionChartStatusLabel }}
              </span>
            </div>
          </div>
          <div class="mt-3 min-h-0 flex-1">
            <div v-show="activeChart === 'equity'" class="h-full">
              <AutomationEquityChart :data="equitySeries" />
            </div>
            <div
              v-show="activeChart === 'position'"
              class="relative flex h-full items-center justify-center"
            >
              <TradingViewWidget
                class="h-full w-full"
                :symbol="tradingViewSymbol"
                :interval="tradingViewInterval"
              />
              <div
                v-if="!selectedPositionSymbol"
                class="absolute inset-0 flex items-center justify-center text-xs text-muted"
              >
                Select a position to view the chart.
              </div>
            </div>
          </div>
        </BaseCard>

        <BaseCard class="flex min-h-0 flex-1 flex-col">
          <div class="flex flex-wrap items-center justify-between gap-2 min-h-8">
            <div class="flex items-center gap-2">
              <button
                class="rounded-md border px-3 py-1 text-[11px] transition-colors duration-200 ease-out"
                :class="
                  activeTab === 'positions'
                    ? 'border-accent/40 bg-accent/15 text-text'
                    : 'border-border bg-panel text-muted'
                "
                type="button"
                @click="activeTab = 'positions'"
              >
                Positions
              </button>
              <button
                class="rounded-md border px-3 py-1 text-[11px] transition-colors duration-200 ease-out"
                :class="
                  activeTab === 'pending_entries'
                    ? 'border-accent/40 bg-accent/15 text-text'
                    : 'border-border bg-panel text-muted'
                "
                type="button"
                @click="activeTab = 'pending_entries'"
              >
                Pending Entries
              </button>
              <button
                class="rounded-md border px-3 py-1 text-[11px] transition-colors duration-200 ease-out"
                :class="
                  activeTab === 'trades'
                    ? 'border-accent/40 bg-accent/15 text-text'
                    : 'border-border bg-panel text-muted'
                "
                type="button"
                @click="activeTab = 'trades'"
              >
                Trade History
              </button>
            </div>

            <template v-if="activeTab === 'positions'">
              <div class="flex flex-wrap items-center justify-end gap-3 pr-1">
                <div
                  class="flex min-w-[78px] flex-col items-center text-center text-[10px] text-muted"
                  :title="`${dailyTradeCount} trades today`"
                >
                  <span class="uppercase tracking-wide">Daily PnL</span>
                  <div class="font-mono text-xs" :class="pnlClass(dailyPnl)">
                    {{ formatUsdSigned(dailyPnl) }}
                  </div>
                </div>
                <div class="flex min-w-[78px] flex-col items-center text-center text-[10px] text-muted">
                  <span class="uppercase tracking-wide">Margin Used</span>
                  <div class="font-mono text-xs text-text">{{ formatUsdCompact(positionsMarginExposure) }}</div>
                </div>
                <div class="flex min-w-[78px] flex-col items-center text-center text-[10px] text-muted">
                  <span class="uppercase tracking-wide">Position Value</span>
                  <div class="font-mono text-xs text-text">{{ formatUsdCompact(positionsExposure) }}</div>
                </div>
                <div class="flex min-w-[64px] flex-col items-center text-center text-[10px] text-muted">
                  <span class="uppercase tracking-wide">UPnL</span>
                  <div class="font-mono text-xs" :class="pnlClass(positionsUpnl)">
                    {{ formatUsdSigned(positionsUpnl) }}
                  </div>
                </div>
                <div class="flex min-w-[52px] flex-col items-center text-center text-[10px] text-muted">
                  <span class="uppercase tracking-wide">Count</span>
                  <div class="font-mono text-xs text-text">{{ store.positions.length }}</div>
                </div>
              </div>
            </template>

            <template v-else-if="activeTab === 'pending_entries'">
              <span class="text-[11px] text-muted">
                {{ pendingEntries.length }} active
              </span>
            </template>

            <template v-else>
              <span class="text-[11px] text-muted">
                {{ store.trades.length }} items
              </span>
            </template>
          </div>

          <div class="mt-3 min-h-0 flex-1 overflow-y-auto pr-1 scrollbar-hidden">
            <div v-if="activeTab === 'positions'" class="space-y-2">
              <div v-if="store.positions.length === 0">
                <BaseEmptyState
                  title="No open positions"
                  subtitle="Positions appear when automation opens trades."
                />
              </div>
              <div v-else class="space-y-3">
                <article
                  v-for="position in store.positions"
                  :key="positionKey(position)"
                  class="rounded-md border border-border bg-panel/60 p-3"
                >
                  <div class="flex flex-wrap items-start justify-between gap-3">
                    <div class="space-y-2">
                      <div class="flex flex-wrap items-center gap-2">
                        <button
                          class="font-display text-base transition"
                          :class="positionSymbolClass(position)"
                          type="button"
                          @click="selectPositionSymbol(position.symbol)"
                        >
                          {{ position.symbol }}
                        </button>
                        <span class="rounded-full border border-border px-2 py-0.5 text-[10px] text-muted">
                          {{ positionLeverage(position) }}x
                        </span>
                        <span
                          class="rounded-full border border-border px-2 py-0.5 text-[10px] uppercase"
                          :class="positionToneClass(position)"
                        >
                          {{ positionDirection(position) }}
                        </span>
                        <span
                          v-if="position.auto_add"
                          class="rounded-full border px-2 py-0.5 text-[10px] uppercase"
                          :class="autoAddStatusClass(position.auto_add.status)"
                        >
                          {{ position.auto_add.status.replace(/_/g, " ") }}
                        </span>
                      </div>
                      <div class="text-[11px] text-muted">
                        Opened {{ positionOpenedLabel(position) }}
                      </div>
                    </div>

                    <button
                      class="rounded-md border border-negative/40 bg-negative/10 px-2 py-1 text-[10px] text-negative hover:text-negative/80 disabled:opacity-50"
                      type="button"
                      :disabled="closingPositionSymbol === position.symbol"
                      @click="handleClosePosition(position)"
                    >
                      {{ closingPositionSymbol === position.symbol ? "Closing..." : "Close" }}
                    </button>
                  </div>

                  <div class="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
                    <div class="rounded-md border border-border/70 bg-surface/30 px-3 py-2">
                      <div class="text-[10px] uppercase tracking-wide text-muted">Size</div>
                      <div class="mt-1 font-mono text-xs text-text">
                        {{ formatUsdPrecise(positionSizeUsd(position)) }}
                      </div>
                    </div>
                    <div class="rounded-md border border-border/70 bg-surface/30 px-3 py-2">
                      <div class="text-[10px] uppercase tracking-wide text-muted">Margin</div>
                      <div class="mt-1 font-mono text-xs text-text">
                        {{ formatUsdPrecise(positionMarginUsd(position)) }}
                      </div>
                    </div>
                    <div class="rounded-md border border-border/70 bg-surface/30 px-3 py-2">
                      <div class="text-[10px] uppercase tracking-wide text-muted">Entry</div>
                      <div class="mt-1 font-mono text-xs text-text">{{ formatNumber(position.entry_price) }}</div>
                    </div>
                    <div class="rounded-md border border-border/70 bg-surface/30 px-3 py-2">
                      <div class="text-[10px] uppercase tracking-wide text-muted">Mark</div>
                      <div class="mt-1 font-mono text-xs text-text">{{ formatNumber(position.mark_price) }}</div>
                    </div>
                    <div class="rounded-md border border-border/70 bg-surface/30 px-3 py-2">
                      <div class="text-[10px] uppercase tracking-wide text-muted">Liq</div>
                      <div class="mt-1 font-mono text-xs text-muted">{{ positionLiqPrice(position) }}</div>
                    </div>
                    <div class="rounded-md border border-border/70 bg-surface/30 px-3 py-2">
                      <div class="text-[10px] uppercase tracking-wide text-muted">UPnL</div>
                      <div class="mt-1 font-mono text-xs" :class="pnlClass(position.unrealized_pnl)">
                        {{ formatUsdSigned(position.unrealized_pnl) }}
                      </div>
                    </div>
                    <div class="rounded-md border border-border/70 bg-surface/30 px-3 py-2">
                      <div class="text-[10px] uppercase tracking-wide text-muted">ROE</div>
                      <div class="mt-1 font-mono text-xs" :class="pnlClass(position.unrealized_pnl)">
                        {{ formatPercent(positionRoe(position)) }}
                      </div>
                    </div>
                    <div class="rounded-md border border-border/70 bg-surface/30 px-3 py-2">
                      <div class="text-[10px] uppercase tracking-wide text-muted">Stop</div>
                      <div class="mt-1 font-mono text-xs text-text">{{ positionStopLabel(position) }}</div>
                    </div>
                    <div class="rounded-md border border-border/70 bg-surface/30 px-3 py-2">
                      <div class="text-[10px] uppercase tracking-wide text-muted">TP</div>
                      <div class="mt-1 font-mono text-xs text-text">{{ positionTakeProfitLabel(position) }}</div>
                    </div>
                    <div class="rounded-md border border-border/70 bg-surface/30 px-3 py-2">
                      <div class="text-[10px] uppercase tracking-wide text-muted">Auto-Add</div>
                      <div class="mt-1 font-mono text-xs text-text">{{ positionAutoAddProgress(position) }}</div>
                    </div>
                  </div>

                  <div class="mt-3 rounded-md border border-border/70 bg-surface/20 px-3 py-3">
                    <div class="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <div class="font-display text-sm text-text">Auto-Add</div>
                        <div class="text-[10px] text-muted">
                          {{ position.auto_add ? "Server-armed stop-market ladder." : "This position is not currently tracked by auto-add." }}
                        </div>
                      </div>
                      <span
                        v-if="position.auto_add"
                        class="rounded-full border px-2 py-0.5 text-[10px] uppercase"
                        :class="autoAddStatusClass(position.auto_add.status)"
                      >
                        {{ position.auto_add.status.replace(/_/g, " ") }}
                      </span>
                    </div>

                    <template v-if="position.auto_add">
                      <div class="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
                        <div class="rounded-md border border-border/60 bg-panel/50 px-3 py-2">
                          <div class="text-[10px] uppercase tracking-wide text-muted">Resolved</div>
                          <div class="mt-1 font-mono text-xs text-text">
                            {{ position.auto_add.filled_add_count }}/{{ position.auto_add.max_tranches }}
                          </div>
                        </div>
                        <div class="rounded-md border border-border/60 bg-panel/50 px-3 py-2">
                          <div class="text-[10px] uppercase tracking-wide text-muted">Trigger Basis</div>
                          <div class="mt-1 font-mono text-xs text-text">
                            {{ formatNumber(position.auto_add.next_trigger_basis_price ?? null) }}
                          </div>
                        </div>
                        <div class="rounded-md border border-border/60 bg-panel/50 px-3 py-2">
                          <div class="text-[10px] uppercase tracking-wide text-muted">Next Trigger</div>
                          <div class="mt-1 font-mono text-xs text-text">
                            {{ formatNumber(position.auto_add.next_trigger_price ?? null) }}
                          </div>
                        </div>
                        <div class="rounded-md border border-border/60 bg-panel/50 px-3 py-2">
                          <div class="text-[10px] uppercase tracking-wide text-muted">15m ATR</div>
                          <div class="mt-1 font-mono text-xs text-text">
                            {{ formatNumber(position.auto_add.latest_atr_value ?? null) }}
                          </div>
                        </div>
                        <div class="rounded-md border border-border/60 bg-panel/50 px-3 py-2">
                          <div class="text-[10px] uppercase tracking-wide text-muted">Original Risk</div>
                          <div class="mt-1 font-mono text-xs text-text">
                            {{ formatUsdPrecise(position.auto_add.original_risk_usd ?? null) }}
                          </div>
                        </div>
                        <div class="rounded-md border border-border/60 bg-panel/50 px-3 py-2">
                          <div class="text-[10px] uppercase tracking-wide text-muted">Initial Margin</div>
                          <div class="mt-1 font-mono text-xs text-text">
                            {{ formatUsdPrecise(position.auto_add.initial_margin_used ?? null) }}
                          </div>
                        </div>
                        <div class="rounded-md border border-border/60 bg-panel/50 px-3 py-2">
                          <div class="text-[10px] uppercase tracking-wide text-muted">Current Stop / TP</div>
                          <div class="mt-1 font-mono text-xs text-text">
                            {{ positionStopLabel(position) }} / {{ positionTakeProfitLabel(position) }}
                          </div>
                        </div>
                      </div>

                      <div
                        v-if="position.auto_add.last_error"
                        class="mt-3 rounded-md border border-warning/30 bg-warning/10 px-3 py-2 text-[11px] text-warning"
                      >
                        {{ position.auto_add.last_error }}
                      </div>

                      <div class="mt-3 space-y-2">
                        <div class="text-[10px] uppercase tracking-wide text-muted">Tranches</div>
                        <div class="space-y-2">
                          <div
                            v-for="tranche in position.auto_add.tranches"
                            :key="`${positionKey(position)}-${tranche.tranche_index}`"
                            class="rounded-md border border-border/60 bg-panel/50 px-3 py-2"
                          >
                            <div class="flex flex-wrap items-center justify-between gap-2">
                              <div class="font-display text-sm text-text">
                                {{ autoAddTrancheLabel(tranche.tranche_index) }}
                              </div>
                              <div class="text-[10px] uppercase tracking-wide text-muted">
                                {{ tranche.status || tranche.kind }}
                              </div>
                            </div>
                            <div class="mt-2 grid gap-2 sm:grid-cols-2 xl:grid-cols-4 text-[11px]">
                              <div>
                                <div class="text-[10px] uppercase tracking-wide text-muted">Trigger</div>
                                <div class="mt-1 font-mono text-xs text-text">
                                  {{ formatNumber(tranche.trigger_price ?? null) }}
                                </div>
                              </div>
                              <div>
                                <div class="text-[10px] uppercase tracking-wide text-muted">Fill</div>
                                <div class="mt-1 font-mono text-xs text-text">
                                  {{ formatNumber(tranche.fill_price ?? null) }}
                                </div>
                              </div>
                              <div>
                                <div class="text-[10px] uppercase tracking-wide text-muted">Qty</div>
                                <div class="mt-1 font-mono text-xs text-text">
                                  {{ formatNumber(tranche.filled_quantity ?? null) }}
                                </div>
                              </div>
                              <div>
                                <div class="text-[10px] uppercase tracking-wide text-muted">Margin</div>
                                <div class="mt-1 font-mono text-xs text-text">
                                  {{ formatUsdPrecise(tranche.margin_used ?? null) }}
                                </div>
                              </div>
                              <div>
                                <div class="text-[10px] uppercase tracking-wide text-muted">Notional</div>
                                <div class="mt-1 font-mono text-xs text-text">
                                  {{ formatUsdPrecise(tranche.position_notional_usd ?? null) }}
                                </div>
                              </div>
                              <div>
                                <div class="text-[10px] uppercase tracking-wide text-muted">ATR</div>
                                <div class="mt-1 font-mono text-xs text-text">
                                  {{ formatNumber(tranche.atr_value ?? null) }}
                                </div>
                              </div>
                              <div>
                                <div class="text-[10px] uppercase tracking-wide text-muted">Basis</div>
                                <div class="mt-1 font-mono text-xs text-text">
                                  {{ formatNumber(tranche.trigger_basis_price ?? null) }}
                                </div>
                              </div>
                              <div>
                                <div class="text-[10px] uppercase tracking-wide text-muted">Order Id</div>
                                <div class="mt-1 truncate font-mono text-xs text-text">
                                  {{ tranche.exchange_order_id || "--" }}
                                </div>
                              </div>
                              <div class="sm:col-span-2">
                                <div class="text-[10px] uppercase tracking-wide text-muted">Filled At</div>
                                <div class="mt-1 text-xs text-text">
                                  {{ formatDateTime(tranche.fill_time) }}
                                </div>
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                    </template>
                  </div>
                </article>
              </div>
            </div>

            <div v-else-if="activeTab === 'pending_entries'" class="space-y-2">
              <div class="rounded-md border border-border bg-panel/50">
                <div class="flex items-center justify-between border-b border-border/70 px-3 py-2">
                  <div>
                    <div class="font-display text-sm text-text">Pending Entries</div>
                    <div class="text-[10px] text-muted">Managed resting limit entries</div>
                  </div>
                  <span class="text-[10px] uppercase tracking-wide text-muted">
                    {{ pendingEntries.length }} active
                  </span>
                </div>
                <div v-if="pendingEntries.length === 0" class="px-3 py-4 text-[11px] text-muted">
                  No pending entries.
                </div>
                <div v-else class="overflow-x-auto">
                  <table class="w-full text-left text-[11px]">
                    <thead class="text-[10px] uppercase tracking-wide text-muted">
                      <tr class="border-b border-border/50">
                        <th class="px-3 py-2">Symbol</th>
                        <th class="px-3 py-2">Side</th>
                        <th class="px-3 py-2 text-right">Limit</th>
                        <th class="px-3 py-2 text-right">Mark</th>
                        <th class="px-3 py-2 text-right">Filled</th>
                        <th class="px-3 py-2 text-right">Age</th>
                        <th class="px-3 py-2 text-right">Expires In</th>
                        <th class="px-3 py-2 text-right">Status</th>
                        <th class="px-3 py-2 text-right"></th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-for="entry in pendingEntries"
                        :key="entry.id"
                        class="border-b border-border/50 text-xs last:border-b-0"
                      >
                        <td class="px-3 py-2 font-display text-sm text-text">{{ entry.symbol }}</td>
                        <td class="px-3 py-2">
                          <span
                            class="rounded-full border border-border px-2 py-0.5 text-[10px] uppercase"
                            :class="pendingEntryToneClass(entry)"
                          >
                            {{ entry.side }}
                          </span>
                        </td>
                        <td class="px-3 py-2 text-right font-mono text-text">
                          {{ formatNumber(entry.limit_price) }}
                        </td>
                        <td class="px-3 py-2 text-right font-mono text-text">
                          {{ formatNumber(entry.current_mark ?? null) }}
                        </td>
                        <td class="px-3 py-2 text-right font-mono text-text">
                          {{ pendingEntryFilledLabel(entry) }}
                        </td>
                        <td class="px-3 py-2 text-right text-muted">
                          {{ pendingEntryAgeLabel(entry) }}
                        </td>
                        <td class="px-3 py-2 text-right text-muted">
                          {{ pendingEntryExpiresInLabel(entry) }}
                        </td>
                        <td class="px-3 py-2 text-right text-muted">
                          {{ entry.status }}
                        </td>
                        <td class="px-3 py-2 text-right">
                          <button
                            class="rounded-md border border-border bg-panel px-2 py-1 text-[10px] text-muted hover:text-negative disabled:opacity-50"
                            type="button"
                            :disabled="cancelingPendingEntryId === entry.id"
                            @click="handleCancelPendingEntry(entry)"
                          >
                            Cancel
                          </button>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            <div v-else class="space-y-2">
              <div
                v-for="trade in store.trades"
                :key="tradeKey(trade)"
                class="rounded-md border border-border bg-panel/50 px-3 py-2"
              >
                <div class="flex items-center justify-between text-xs">
                  <span class="font-display text-sm text-text">{{ trade.symbol }}</span>
                  <span class="text-[10px] uppercase tracking-wide" :class="tradeToneClass(trade)">
                    {{ tradeLabel(trade) }}
                  </span>
                </div>
                <div class="mt-2 grid grid-cols-2 gap-2 text-[11px] text-muted">
                  <div>
                    <div class="text-[10px] uppercase tracking-wide text-muted">Size USD</div>
                    <div class="font-mono text-text">{{ formatUsd(trade.size_usd) }}</div>
                  </div>
                  <div>
                    <div class="text-[10px] uppercase tracking-wide text-muted">Entry</div>
                    <div class="font-mono text-text">{{ formatNumber(trade.entry_price) }}</div>
                  </div>
                  <div>
                    <div class="text-[10px] uppercase tracking-wide text-muted">Exit</div>
                    <div class="font-mono text-text">{{ formatNumber(trade.exit_price) }}</div>
                  </div>
                  <div>
                    <div class="text-[10px] uppercase tracking-wide text-muted">PnL</div>
                    <div class="font-mono" :class="pnlClass(trade.pnl)">
                      {{ formatUsd(trade.pnl) }}
                    </div>
                  </div>
                </div>
                <div class="mt-2 text-[10px] text-muted">
                  {{ formatTimestamp(trade.created_at) }}
                </div>
              </div>

              <BaseEmptyState
                v-if="store.trades.length === 0"
                title="No trade history"
                subtitle="Executed trades will appear here."
              />
            </div>
          </div>
        </BaseCard>
      </aside>
    </div>

    <TransitionRoot :show="showSessionModal" as="template">
      <Dialog class="relative z-50" @close="closeSessionModal">
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
            <DialogPanel
              class="w-full max-w-7xl min-w-0 rounded-lg border border-border bg-surface p-6 shadow-panel"
            >
              <div class="flex items-center justify-between">
                <DialogTitle class="font-display text-base text-white">Session History</DialogTitle>
                <button
                  class="rounded-md border border-border bg-panel px-2 py-1 text-xs text-muted"
                  type="button"
                  @click="closeSessionModal"
                >
                  Close
                </button>
              </div>

              <div class="mt-4 grid h-[70vh] min-h-0 gap-4 overflow-hidden lg:grid-cols-[minmax(0,0.30fr)_minmax(0,0.20fr)_minmax(0,0.50fr)]">
                <div class="flex min-h-0 min-w-0 flex-col gap-3">
                  <div class="text-xs uppercase tracking-wide text-muted">Sessions</div>
                  <div class="min-h-0 flex-1 overflow-y-auto pr-1 scrollbar-hidden">
                    <div v-if="sessionsLoading" class="text-xs text-muted">
                      Loading sessions...
                    </div>
                    <div v-else-if="sessions.length === 0" class="text-xs text-muted">
                      No sessions available.
                    </div>
                    <div v-else class="space-y-2">
                      <button
                        v-for="session in sessions"
                        :key="session.id"
                        class="w-full rounded-md border px-3 py-2 text-left text-xs transition"
                        :class="
                          selectedSessionId === session.id
                            ? 'border-accent bg-accent/10 text-text'
                            : 'border-border bg-panel/50 text-muted hover:text-text'
                        "
                        type="button"
                        @click="loadSessionDetail(session.id)"
                      >
                        <div class="flex items-center justify-between gap-2">
                          <div class="flex items-center gap-2">
                            <span class="font-display text-sm text-text">
                              {{ formatDateTime(session.started_at) }}
                            </span>
                            <span
                              class="rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide"
                              :class="modeTagClass(session.execution_mode)"
                            >
                              {{ session.execution_mode || "unknown" }}
                            </span>
                          </div>
                          <div class="flex items-center gap-2">
                            <div class="relative" data-export-menu>
                              <button
                                class="rounded-md border border-border bg-panel px-2 py-0.5 text-[10px] text-muted hover:text-text disabled:opacity-50"
                                type="button"
                                :disabled="exportingSessionId === session.id"
                                @click.stop="toggleExportMenu(session.id)"
                              >
                                {{ exportingSessionId === session.id ? "Exporting..." : "Export" }}
                              </button>
                              <div
                                v-if="exportMenuSessionId === session.id"
                                class="absolute right-0 z-20 mt-2 w-56 rounded-md border border-border bg-surface p-2 text-[11px] text-text shadow-panel"
                              >
                                <div class="mb-1 text-[10px] uppercase tracking-wide text-muted">Export Logs</div>
                                <button
                                  class="w-full rounded-md px-2 py-1 text-left text-[11px] text-muted hover:bg-panel/70 hover:text-text"
                                  type="button"
                                  @click.stop="handleExportSession(session, 'llm')"
                                >
                                  LLM responses only
                                </button>
                                <button
                                  class="mt-1 w-full rounded-md px-2 py-1 text-left text-[11px] text-muted hover:bg-panel/70 hover:text-text"
                                  type="button"
                                  @click.stop="handleExportSession(session, 'prompt_llm')"
                                >
                                  Prompt + response
                                </button>
                                <button
                                  class="mt-1 w-full rounded-md px-2 py-1 text-left text-[11px] text-muted hover:bg-panel/70 hover:text-text"
                                  type="button"
                                  @click.stop="handleExportSession(session, 'llm_trades')"
                                >
                                  LLM + trades summary
                                </button>
                                <button
                                  class="mt-1 w-full rounded-md px-2 py-1 text-left text-[11px] text-muted hover:bg-panel/70 hover:text-text"
                                  type="button"
                                  @click.stop="handleExportSession(session, 'raw')"
                                >
                                  Raw logs (full)
                                </button>
                              </div>
                            </div>
                            <button
                              class="rounded-md border border-border bg-panel px-2 py-0.5 text-[10px] text-muted hover:text-negative"
                              type="button"
                              @click.stop="handleDeleteSession(session.id)"
                            >
                              Delete
                            </button>
                          </div>
                        </div>
                        <div class="mt-1 break-words text-[11px] text-muted">
                          {{ session.provider || "--" }}/{{ session.model || "--" }}
                        </div>
                        <div class="mt-1 break-words text-[10px] text-muted">
                          {{ formatSessionPromptSummary(session) }}
                        </div>
                        <div class="mt-2 grid grid-cols-2 gap-2 text-[10px] text-muted">
                          <span>{{ session.total_cycles ?? 0 }} cycles</span>
                          <span>{{ session.total_trades ?? 0 }} trades</span>
                          <span :class="pnlClass(session.total_pnl)">
                            {{ formatUsd(session.total_pnl) }}
                          </span>
                          <span>Prompts/h: {{ formatRate(session.prompt_rate_per_hour) }}</span>
                        </div>
                      </button>
                    </div>
                  </div>
                  <div class="relative mt-2 flex items-center justify-center text-[11px] text-muted">
                    <div class="flex items-center gap-2">
                      <button
                        class="rounded-md border border-border bg-panel px-2 py-1 text-[10px] text-muted hover:text-text disabled:opacity-50"
                        type="button"
                        :disabled="sessionsLoading || sessionPage === 1"
                        @click="changeSessionPage(sessionPage - 1)"
                      >
                        &lt;
                      </button>
                      <div class="flex items-center gap-1">
                        <template v-for="item in sessionPageItems" :key="item.key">
                          <button
                            v-if="item.type === 'page'"
                            class="rounded-md border px-2 py-0.5 text-[10px]"
                            :class="
                              item.value === sessionPage
                                ? 'border-accent bg-accent/10 text-text'
                                : 'border-border bg-panel text-muted hover:text-text'
                            "
                            type="button"
                            :disabled="sessionsLoading"
                            @click="changeSessionPage(item.value)"
                          >
                            {{ item.value }}
                          </button>
                          <span v-else class="px-1 text-[10px] text-muted">…</span>
                        </template>
                      </div>
                      <button
                        class="rounded-md border border-border bg-panel px-2 py-1 text-[10px] text-muted hover:text-text disabled:opacity-50"
                        type="button"
                        :disabled="sessionsLoading || !hasMoreSessions"
                        @click="changeSessionPage(sessionPage + 1)"
                      >
                        &gt;
                      </button>
                    </div>
                    <span class="absolute right-0">
                      {{ sessionPageRange }}
                    </span>
                  </div>
                </div>

                <div class="flex min-h-0 min-w-0 flex-col gap-3">
                  <div class="flex items-center justify-between">
                    <div class="text-xs uppercase tracking-wide text-muted">Details</div>
                    <div class="text-[10px] text-muted">
                      {{ sessionDetail?.session?.id ? "Selected" : "Select a session" }}
                    </div>
                  </div>

                  <div class="min-h-0 flex-1 overflow-y-auto rounded-md border border-border bg-panel/50 p-3 text-[11px] text-muted scrollbar-hidden">
                    <div v-if="sessionDetailLoading" class="h-full animate-pulse">
                      <div class="space-y-4">
                        <div v-for="idx in 10" :key="idx" class="space-y-2">
                          <div class="h-2 w-20 rounded bg-panel/60"></div>
                          <div class="h-3 w-full max-w-[14rem] rounded bg-panel/40"></div>
                        </div>
                      </div>
                    </div>
                    <div v-else-if="!sessionDetail" class="text-[11px] text-muted">
                      No session selected.
                    </div>
                    <div v-else class="space-y-4">
                      <div class="space-y-1">
                        <div class="text-[10px] uppercase tracking-wide text-muted">Session ID</div>
                        <div class="break-all font-mono text-text" :title="sessionDetail.session.id">
                          {{ sessionDetail.session.id }}
                        </div>
                      </div>
                      <div class="space-y-1">
                        <div class="text-[10px] uppercase tracking-wide text-muted">Mode</div>
                        <div class="text-text">{{ sessionDetail.session.execution_mode || "--" }}</div>
                      </div>
                      <div class="space-y-1">
                        <div class="text-[10px] uppercase tracking-wide text-muted">Started</div>
                        <div class="text-text">
                          {{ formatDateTime(sessionDetail.session.started_at) }}
                        </div>
                      </div>
                      <div class="space-y-1">
                        <div class="text-[10px] uppercase tracking-wide text-muted">Ended</div>
                        <div class="text-text">
                          {{ sessionDetail.session.ended_at ? formatDateTime(sessionDetail.session.ended_at) : "Active" }}
                        </div>
                      </div>
                      <div class="space-y-1">
                        <div class="text-[10px] uppercase tracking-wide text-muted">Duration</div>
                        <div class="text-text">
                          {{
                            formatDuration(
                              sessionDetail.session.started_at,
                              sessionDetail.session.ended_at,
                            )
                          }}
                        </div>
                      </div>
                      <div class="space-y-1">
                        <div class="text-[10px] uppercase tracking-wide text-muted">Cycles</div>
                        <div class="text-text">{{ sessionDetail.session.total_cycles ?? 0 }}</div>
                      </div>
                      <div class="space-y-1">
                        <div class="text-[10px] uppercase tracking-wide text-muted">Trades</div>
                        <div class="text-text">{{ sessionDetail.session.total_trades ?? 0 }}</div>
                      </div>
                      <div class="space-y-1">
                        <div class="text-[10px] uppercase tracking-wide text-muted">Prompts</div>
                        <div class="text-text">{{ sessionDetail.session.prompt_count ?? 0 }}</div>
                      </div>
                      <div class="space-y-1">
                        <div class="text-[10px] uppercase tracking-wide text-muted">Prompts / h</div>
                        <div class="text-text">{{ formatRate(sessionDetail.session.prompt_rate_per_hour) }}</div>
                      </div>
                      <div class="space-y-1">
                        <div class="text-[10px] uppercase tracking-wide text-muted">Total PnL</div>
                        <div :class="pnlClass(sessionDetail.session.total_pnl)">
                          {{ formatUsd(sessionDetail.session.total_pnl) }}
                        </div>
                      </div>
                      <div class="space-y-1">
                        <div class="text-[10px] uppercase tracking-wide text-muted">New Resonance Prompt</div>
                        <div class="text-text">
                          {{ formatPromptVersion(sessionDetail.session.new_resonance_prompt_version) }}
                        </div>
                      </div>
                      <div class="space-y-1">
                        <div class="text-[10px] uppercase tracking-wide text-muted">Position Mgmt Prompt</div>
                        <div class="text-text">
                          {{ formatPromptVersion(sessionDetail.session.position_management_prompt_version) }}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                <div class="flex min-h-0 min-w-0 flex-col gap-3">
                  <div class="flex items-center gap-2">
                    <button
                      class="rounded-md border border-border px-3 py-1 text-[11px] transition-colors duration-150"
                      :class="
                        activeSessionTab === 'logs'
                          ? 'bg-accent/20 text-text'
                          : 'bg-panel text-muted hover:text-text'
                      "
                      type="button"
                      @click="activeSessionTab = 'logs'"
                    >
                      Logs
                    </button>
                    <button
                      class="rounded-md border border-border px-3 py-1 text-[11px] transition-colors duration-150"
                      :class="
                        activeSessionTab === 'trades'
                          ? 'bg-accent/20 text-text'
                          : 'bg-panel text-muted hover:text-text'
                      "
                      type="button"
                      @click="activeSessionTab = 'trades'"
                    >
                      Trades
                    </button>
                  </div>

                  <div
                      ref="sessionLogRef"
                      class="min-h-0 flex-1 overflow-x-hidden overflow-y-auto pr-1 text-xs scrollbar-hidden"
                      @scroll="handleSessionLogScroll"
                    >
                    <div
                      v-if="activeSessionTab === 'logs' && sessionDetail"
                      class="mb-2 flex items-center justify-between text-[10px] text-muted"
                    >
                      <span>
                        Page {{ sessionLogPage }} · {{ sessionDetail.logs.length }} entries
                      </span>
                      <div class="flex items-center gap-2">
                        <button
                          class="rounded-md border border-border bg-panel px-2 py-1 text-[10px] text-muted hover:text-text disabled:opacity-50"
                          type="button"
                          :disabled="sessionDetailLoading || sessionLogPage === 1"
                          @click="changeSessionLogPage(sessionLogPage - 1)"
                        >
                          Prev
                        </button>
                        <button
                          class="rounded-md border border-border bg-panel px-2 py-1 text-[10px] text-muted hover:text-text disabled:opacity-50"
                          type="button"
                          :disabled="sessionDetailLoading || !sessionLogHasMore"
                          @click="changeSessionLogPage(sessionLogPage + 1)"
                        >
                          Next
                        </button>
                      </div>
                    </div>
                    <div v-if="sessionDetailLoading" class="text-xs text-muted">
                      Loading details...
                    </div>
                    <div v-else-if="sessionError" class="text-xs text-negative">
                      {{ sessionError }}
                    </div>
                    <div v-else-if="!sessionDetail" class="text-xs text-muted">
                      Select a session to see details.
                    </div>
                    <div v-else-if="activeSessionTab === 'logs'" class="space-y-2">
                      <div
                        v-for="(log, idx) in sessionDetail.logs"
                        :key="log.id || `${log.created_at}-${idx}`"
                        class="min-w-0 overflow-hidden rounded-md border border-border bg-panel/60 px-3 py-2"
                      >
                        <div class="flex flex-wrap items-center gap-2 text-[10px] uppercase tracking-wide text-muted">
                          <span>{{ formatTimestamp(log.created_at) }}</span>
                          <span class="rounded-full border border-border px-2 py-0.5">
                            {{ (log.log_type || "system").toUpperCase() }}
                          </span>
                          <span v-if="log.cycle_number" class="text-[10px] text-muted">
                            #{{ log.cycle_number }}
                          </span>
                        </div>
                        <div class="mt-1 pr-1 text-xs">
                          <div class="whitespace-pre-wrap break-all" :class="logMessageClass(log)">
                            {{ logMessage(log) }}
                          </div>
                          <pre
                            v-if="isPromptLog(log)"
                            class="mt-2 max-h-48 max-w-full overflow-y-auto rounded-md border border-border bg-surface/60 p-3 font-mono text-[11px] leading-relaxed text-text scrollbar-hidden [tab-size:2] whitespace-pre-wrap break-all"
                          >{{ promptText(log) }}</pre>
                          <pre
                            v-if="isLlmResponseLog(log)"
                            class="mt-2 max-h-48 max-w-full overflow-y-auto rounded-md border border-border bg-surface/60 p-3 font-mono text-[11px] leading-relaxed text-text scrollbar-hidden [tab-size:2] whitespace-pre-wrap break-all"
                          >{{ llmResponseText(log) }}</pre>
                          <pre
                            v-if="isLlmParseLog(log)"
                            class="mt-2 max-h-48 max-w-full overflow-y-auto rounded-md border border-border bg-surface/60 p-3 font-mono text-[11px] leading-relaxed text-text scrollbar-hidden [tab-size:2] whitespace-pre-wrap break-all"
                          >{{ llmParseText(log) }}</pre>
                          <pre
                            v-if="isDetailLog(log)"
                            class="mt-2 max-h-48 max-w-full overflow-y-auto rounded-md border border-border bg-surface/60 p-3 font-mono text-[11px] leading-relaxed text-text scrollbar-hidden [tab-size:2] whitespace-pre-wrap break-all"
                          >{{ detailText(log) }}</pre>
                        </div>
                      </div>
                      <div
                        v-if="sessionDetail.logs.length > 0"
                        class="mt-2 flex items-center justify-between text-[10px] text-muted"
                      >
                        <span>
                          Page {{ sessionLogPage }} · {{ sessionDetail.logs.length }} entries
                        </span>
                        <div class="flex items-center gap-2">
                          <button
                            class="rounded-md border border-border bg-panel px-2 py-1 text-[10px] text-muted hover:text-text disabled:opacity-50"
                            type="button"
                            :disabled="sessionDetailLoading || sessionLogPage === 1"
                            @click="changeSessionLogPage(sessionLogPage - 1)"
                          >
                            Prev
                          </button>
                          <button
                            class="rounded-md border border-border bg-panel px-2 py-1 text-[10px] text-muted hover:text-text disabled:opacity-50"
                            type="button"
                            :disabled="sessionDetailLoading || !sessionLogHasMore"
                            @click="changeSessionLogPage(sessionLogPage + 1)"
                          >
                            Next
                          </button>
                        </div>
                      </div>
                    </div>
                    <div v-else class="space-y-2">
                      <div
                        v-for="trade in sessionDetail.trades"
                        :key="tradeKey(trade)"
                        class="rounded-md border border-border bg-panel/60 px-3 py-2"
                      >
                        <div class="flex items-center justify-between text-xs">
                          <span class="font-display text-sm text-text">{{ trade.symbol }}</span>
                          <span class="text-[10px] uppercase tracking-wide" :class="tradeToneClass(trade)">
                            {{ tradeLabel(trade) }}
                          </span>
                        </div>
                        <div class="mt-2 grid grid-cols-2 gap-2 text-[11px] text-muted">
                          <div>
                            <div class="text-[10px] uppercase tracking-wide text-muted">Size USD</div>
                            <div class="font-mono text-text">{{ formatUsd(trade.size_usd) }}</div>
                          </div>
                          <div>
                            <div class="text-[10px] uppercase tracking-wide text-muted">Entry</div>
                            <div class="font-mono text-text">{{ formatNumber(trade.entry_price) }}</div>
                          </div>
                          <div>
                            <div class="text-[10px] uppercase tracking-wide text-muted">Exit</div>
                            <div class="font-mono text-text">{{ formatNumber(trade.exit_price) }}</div>
                          </div>
                          <div>
                            <div class="text-[10px] uppercase tracking-wide text-muted">PnL</div>
                            <div class="font-mono" :class="pnlClass(trade.pnl)">
                              {{ formatUsd(trade.pnl) }}
                            </div>
                          </div>
                        </div>
                        <div class="mt-2 text-[10px] text-muted">
                          {{ formatTimestamp(trade.created_at) }}
                        </div>
                      </div>
                      <div v-if="sessionDetail.trades.length === 0" class="text-xs text-muted">
                        No trades for this session.
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </DialogPanel>
          </TransitionChild>
        </div>
      </Dialog>
    </TransitionRoot>

    <TransitionRoot :show="showLiveModeConfirm" as="template">
      <Dialog class="relative z-50" @close="closeLiveModeConfirm">
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
            <DialogPanel class="w-full max-w-lg rounded-lg border border-border bg-surface p-6 shadow-panel">
              <div class="flex items-start justify-between gap-4">
                <div>
                  <DialogTitle class="font-display text-base text-white">
                    Switch to Live Execution
                  </DialogTitle>
                  <p class="mt-2 text-xs text-muted">
                    Live mode sends real orders to your connected exchange account. This can result in
                    real losses. Double-check your exchange selection, balances, and risk limits.
                  </p>
                </div>
                <button
                  class="rounded-md border border-border bg-panel px-2 py-1 text-xs text-muted"
                  type="button"
                  @click="closeLiveModeConfirm"
                >
                  Close
                </button>
              </div>

              <div class="mt-4 rounded-md border border-warning/40 bg-warning/10 p-3 text-[11px] text-warning">
                Live execution is irreversible for the current cycle once started. Verify testnet is
                disabled and guardrails are configured.
              </div>

              <label class="mt-4 flex items-start gap-2 text-xs text-muted">
                <input v-model="liveModeConfirmed" type="checkbox" />
                <span>I understand the risks and want to enable live execution.</span>
              </label>

              <div class="mt-5 flex items-center justify-end gap-2">
                <button
                  class="rounded-md border border-border bg-panel px-3 py-2 text-xs text-muted hover:text-text"
                  type="button"
                  @click="closeLiveModeConfirm"
                >
                  Cancel
                </button>
                <button
                  class="rounded-md border border-warning/40 bg-warning/15 px-3 py-2 text-xs text-warning hover:text-warning/80 disabled:opacity-50"
                  type="button"
                  :disabled="!liveModeConfirmed"
                  @click="confirmLiveMode"
                >
                  Enable Live
                </button>
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
import { Dialog, DialogPanel, DialogTitle, TransitionChild, TransitionRoot } from "@headlessui/vue";
import BaseBadge from "@/components/BaseBadge.vue";
import BaseCard from "@/components/BaseCard.vue";
import BaseEmptyState from "@/components/BaseEmptyState.vue";
import AutomationEquityChart from "@/components/AutomationEquityChart.vue";
import TradingViewWidget from "@/components/TradingViewWidget.vue";
import { stageMessage, useAutomationStore } from "@/stores/automationStore";
import { useRiskManagementStore } from "@/stores/riskManagementStore";
import type { AutomationLog, AutomationPosition, AutomationTrade } from "@/types/automation";
import {
  readModelCache,
  writeModelCache,
  readProvidersCache,
  writeProvidersCache,
  readPromptConfigCache,
  writePromptConfigCache,
} from "@/services/settingsCache";

defineOptions({ name: "AutomationView" });

const store = useAutomationStore();
const riskStore = useRiskManagementStore();
const leftPanelRef = ref<HTMLElement | null>(null);
const leftPanelScrollTop = ref(0);
const promptRateTick = ref(0);
let promptRateTimer: number | null = null;

const startPromptRateTicker = () => {
  if (promptRateTimer) return;
  promptRateTimer = window.setInterval(() => {
    promptRateTick.value += 1;
  }, 30000);
};

const stopPromptRateTicker = () => {
  if (promptRateTimer) {
    clearInterval(promptRateTimer);
    promptRateTimer = null;
  }
};

const promptRateLabel = computed(() => {
  promptRateTick.value;
  const startedAt = store.promptSession.startedAt;
  if (!store.status.isRunning || !startedAt) return "Prompts/h: --";
  const startMs = Date.parse(startedAt);
  if (Number.isNaN(startMs)) return "Prompts/h: --";
  const elapsedMs = Date.now() - startMs;
  if (elapsedMs <= 0) return "Prompts/h: --";
  const rate = store.promptSession.promptCount / (elapsedMs / 3600000);
  const formatted = rate >= 10 ? rate.toFixed(0) : rate.toFixed(1);
  return `Prompts/h: ${formatted}`;
});

const riskExposurePct = computed(() => riskStore.summary?.config?.exposure_pct ?? null);
const riskExposureUsd = computed(() => riskStore.summary?.exposure_usd ?? null);
const riskExposureLabel = computed(() => {
  if (riskExposurePct.value === null || riskExposurePct.value === undefined) return "--";
  return `${riskExposurePct.value.toFixed(1)}%`;
});

type AutomationConfig = {
  execution_mode: string;
  provider: string;
  model: string;
  reasoning_effort: string;
  ema_interval_seconds: number;
  quant_interval_seconds: number;
  pending_entry_timeout_seconds: number;
  max_positions: number;
  auto_add_enabled: boolean;
  auto_add_trigger_atr_multiple: number;
  auto_add_tranche_margin_pct: number;
  auto_add_max_tranches: number;
  include_entry_timing_15m_chart: boolean;
  use_all_monitored_interval_charts: boolean;
  reverse_order_enabled: boolean;
  vegas_prompt_configs?: Record<string, number> | null;
};

type AutomationConfigPayload = {
  execution_mode?: string;
  provider?: string | null;
  model?: string | null;
  reasoning_effort?: string | null;
  ema_interval_seconds?: number;
  quant_interval_seconds?: number;
  pending_entry_timeout_seconds?: number;
  max_positions?: number;
  auto_add_enabled?: boolean;
  auto_add_trigger_atr_multiple?: number;
  auto_add_tranche_margin_pct?: number;
  auto_add_max_tranches?: number;
  include_entry_timing_15m_chart?: boolean;
  use_all_monitored_interval_charts?: boolean;
  reverse_order_enabled?: boolean;
  vegas_prompt_configs?: Record<string, number> | null;
};

type PendingEntryView = {
  id: string;
  symbol: string;
  side: string;
  limit_price: number;
  current_mark?: number | null;
  filled_pct: number;
  filled_quantity?: number | null;
  intended_quantity?: number | null;
  placed_at?: string | null;
  expires_at?: string | null;
  status: string;
  exchange_order_id: string;
};

type TradeGuardLeverageTier = {
  leverage: number;
  symbols: string[];
};

type TradeGuardPositionTierRange = {
  tier: number;
  min_pct: number;
  max_pct: number;
};

type TradeGuardConfigForm = {
  min_confidence: number;
  min_position_size: number;
  sl_min_roe_pct: number;
  sl_max_roe_pct: number;
  tp_min_roe_pct: number;
  tp_max_roe_pct: number;
  dust_threshold_usd: number;
  default_leverage: number;
  leverage_tiers: TradeGuardLeverageTier[];
  position_tier_ranges: TradeGuardPositionTierRange[];
};

type TradeGuardConfigPayload = {
  min_confidence: number;
  min_position_size: number;
  sl_min_roe: number;
  sl_max_roe: number;
  tp_min_roe: number;
  tp_max_roe: number;
  dust_threshold_usd: number;
  default_leverage: number;
  leverage_tiers: TradeGuardLeverageTier[];
  position_tier_ranges: TradeGuardPositionTierRange[];
};

const automationConfigStorageKey = "td_automation_config";

const readAutomationConfigStorage = (): Partial<AutomationConfig> | null => {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(automationConfigStorageKey);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return null;
    return parsed as Partial<AutomationConfig>;
  } catch {
    return null;
  }
};

const writeAutomationConfigStorage = (config: AutomationConfig) => {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(automationConfigStorageKey, JSON.stringify(config));
  } catch {
    // Ignore storage errors
  }
};

const automationConfigDefaults: AutomationConfig = {
  execution_mode: "dry_run",
  provider: "",
  model: "",
  reasoning_effort: "",
  ema_interval_seconds: 60,
  quant_interval_seconds: 60,
  pending_entry_timeout_seconds: 900,
  max_positions: 3,
  auto_add_enabled: false,
  auto_add_trigger_atr_multiple: 1,
  auto_add_tranche_margin_pct: 0.8,
  auto_add_max_tranches: 3,
  include_entry_timing_15m_chart: false,
  use_all_monitored_interval_charts: false,
  reverse_order_enabled: false,
  vegas_prompt_configs: {},
};

const normalizeReasoningEffort = (value: unknown) => {
  if (typeof value !== "string") return "";
  const normalized = value.trim().toLowerCase();
  return ["minimal", "low", "medium", "high", "xhigh"].includes(normalized) ? normalized : "";
};

const tradeGuardConfigDefaults: TradeGuardConfigForm = {
  min_confidence: 60,
  min_position_size: 10,
  sl_min_roe_pct: 3,
  sl_max_roe_pct: 5,
  tp_min_roe_pct: 5,
  tp_max_roe_pct: 20,
  dust_threshold_usd: 10,
  default_leverage: 1,
  leverage_tiers: [
    { leverage: 5, symbols: ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE"] },
    { leverage: 3, symbols: ["SUI", "FARTCOIN", "LTC", "BCH", "XRP"] },
  ],
  position_tier_ranges: [
    { tier: 1, min_pct: 70, max_pct: 100 },
    { tier: 2, min_pct: 35, max_pct: 70 },
    { tier: 3, min_pct: 15, max_pct: 35 },
  ],
};

const storedAutomationConfig = readAutomationConfigStorage();
let cachedAutomationConfig: AutomationConfig | null = storedAutomationConfig
  ? { ...automationConfigDefaults, ...storedAutomationConfig }
  : null;
if (
  cachedAutomationConfig &&
  cachedAutomationConfig.provider.trim().toLowerCase() === "codex"
)
{
  cachedAutomationConfig.reasoning_effort =
    normalizeReasoningEffort(cachedAutomationConfig.reasoning_effort) || "medium";
}

type ProviderOption = {
  name: string;
  configured?: boolean;
  settings?: { display_name?: string | null } | null;
  default_model?: string | null;
  models?: string[];
};

type ModelOption = {
  id?: string;
  name?: string;
} | string;

type EquityPoint = { time: number | string; value: number };

type PromptConfigOption = { id: number; name: string };

type TradingApiStatus = {
  state: "loading" | "active" | "missing" | "error";
  label: string;
  detail?: string;
  isTestnet?: boolean;
};

type CircuitBreakerConfig = {
  max_daily_loss_usd: number;
  max_daily_loss_pct: number;
  max_consecutive_losses: number;
  cooldown_minutes: number;
  max_total_exposure_pct: number;
  enable_pct_limits: boolean;
};

type CircuitBreakerState = {
  daily_loss_usd: number;
  consecutive_losses: number;
  cooldown_until?: string | null;
};

type SessionItem = {
  id: string;
  started_at?: string | null;
  ended_at?: string | null;
  execution_mode?: string;
  provider?: string | null;
  model?: string | null;
  total_cycles?: number;
  total_trades?: number;
  total_pnl?: number;
  prompt_count?: number;
  prompt_rate_per_hour?: number | null;
  duration_seconds?: number | null;
  new_resonance_prompt_version?: number | null;
  position_management_prompt_version?: number | null;
};

type SessionDetail = {
  session: SessionItem;
  logs: AutomationLog[];
  trades: AutomationTrade[];
};

const automationConfig = ref<AutomationConfig>({ ...automationConfigDefaults });
const tradeGuardConfig = ref<TradeGuardConfigForm>({ ...tradeGuardConfigDefaults });
const pendingEntries = ref<PendingEntryView[]>([]);
const cancelingPendingEntryId = ref<string | null>(null);

if (cachedAutomationConfig) {
  automationConfig.value = {
    ...automationConfig.value,
    ...cachedAutomationConfig,
    execution_mode: cachedAutomationConfig.execution_mode || automationConfig.value.execution_mode,
  };
}

const executionModeSelection = ref(automationConfig.value.execution_mode);

const providers = ref<ProviderOption[]>(readProvidersCache() ?? []);
const models = ref<ModelOption[]>([]);
const promptConfigs = ref<PromptConfigOption[]>(readPromptConfigCache() ?? []);
const configError = ref("");
const isStarting = ref(false);
const isStopping = ref(false);
const logFilter = ref("all");
const activeTab = ref<"positions" | "pending_entries" | "trades">("positions");
const activeSessionTab = ref<"logs" | "trades">("logs");
const equitySeries = ref<EquityPoint[]>([]);
const activeChart = ref<"equity" | "position">("equity");
const positionChartInterval = ref("15m");
const selectedPositionSymbol = ref<string | null>(null);
const closingPositionSymbol = ref<string | null>(null);
const positionGraceDeadline = ref<number | null>(null);
const dailyPnl = ref(0);
const dailyTradeCount = ref(0);
const tradingApiStatus = ref<TradingApiStatus>({
  state: "loading",
  label: "Checking...",
  detail: "",
  isTestnet: false,
});
const circuitBreakerConfig = ref<CircuitBreakerConfig>({
  max_daily_loss_usd: 0,
  max_daily_loss_pct: 0,
  max_consecutive_losses: 3,
  cooldown_minutes: 60,
  max_total_exposure_pct: 0,
  enable_pct_limits: false,
});
const circuitBreakerState = ref<CircuitBreakerState>({
  daily_loss_usd: 0,
  consecutive_losses: 0,
  cooldown_until: null,
});
const showSessionModal = ref(false);
const sessions = ref<SessionItem[]>([]);
const selectedSessionId = ref<string | null>(null);
const sessionDetail = ref<SessionDetail | null>(null);
const sessionsLoading = ref(false);
const sessionDetailLoading = ref(false);
const sessionError = ref("");
const sessionPage = ref(1);
const sessionPageSize = ref(20);
const sessionTotal = ref(0);
const sessionLogPage = ref(1);
const sessionLogPageSize = 500;
let positionPollTimer: ReturnType<typeof setInterval> | null = null;
let positionGraceTimer: ReturnType<typeof setTimeout> | null = null;
let promptConfigRefreshTimer: number | null = null;
const automationLogRef = ref<HTMLElement | null>(null);
const automationLogAutoScroll = ref(true);
const sessionLogRef = ref<HTMLElement | null>(null);
const sessionLogAutoScroll = ref(true);
const showLiveModeConfirm = ref(false);
const liveModeConfirmed = ref(false);
const pendingExecutionMode = ref<string | null>(null);
const exportingSessionId = ref<string | null>(null);
const exportMenuSessionId = ref<string | null>(null);

type SessionExportMode = "llm" | "llm_trades" | "prompt_llm" | "raw";

const executionModes = [
  { label: "Prompt Test", value: "prompt_test" },
  { label: "Dry Run", value: "dry_run" },
  { label: "Live", value: "production" },
];

const codexReasoningOptions = [
  { value: "minimal", label: "Minimal" },
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
  { value: "xhigh", label: "XHigh" },
];

const POSITION_GRACE_MS = 30000;

const vegasPromptMappings = [
  { key: "new_resonance", label: "New Resonance" },
  { key: "resonance_increase", label: "Resonance Increase" },
  { key: "structure_shift", label: "Structure Shift" },
  { key: "position_management", label: "Position Management" },
  { key: "bb_exit_warning", label: "BB Exit Warning" },
  { key: "bb_rejection_entry", label: "BB Rejection Entry" },
];

const executionModeLabel = computed(() => {
  const mode = automationConfig.value.execution_mode || store.status.executionMode;
  if (mode === "production") return "Live";
  if (mode === "prompt_test") return "Prompt Test";
  return "Dry Run";
});

watch(
  () => automationConfig.value.execution_mode,
  (value) => {
    executionModeSelection.value = value || "dry_run";
  },
);

const missingProviderModel = computed(
  () => !automationConfig.value.provider || !automationConfig.value.model,
);

const showCodexReasoningEffort = computed(
  () => automationConfig.value.provider.trim().toLowerCase() === "codex",
);

const positionSymbols = computed(() =>
  store.positions.map((position) => position.symbol).filter(Boolean),
);

const pendingEntryTimeoutMinutes = computed(() =>
  Math.round((automationConfig.value.pending_entry_timeout_seconds || 900) / 60),
);

const autoAddTrancheMarginPctDisplay = computed(() =>
  Math.round((automationConfig.value.auto_add_tranche_margin_pct || 0) * 100),
);

const closeExportMenu = (event: MouseEvent) => {
  const target = event.target as HTMLElement | null;
  if (target && target.closest("[data-export-menu]")) return;
  exportMenuSessionId.value = null;
};

const positionChartAvailable = computed(
  () => store.positions.length > 0 || positionGraceDeadline.value !== null,
);

const sessionPageRange = computed(() => {
  if (sessionTotal.value <= 0) return "0 sessions";
  const start = (sessionPage.value - 1) * sessionPageSize.value + 1;
  const end = Math.min(sessionTotal.value, sessionPage.value * sessionPageSize.value);
  return `${start}-${end} of ${sessionTotal.value}`;
});

const hasMoreSessions = computed(
  () => sessionPage.value * sessionPageSize.value < sessionTotal.value,
);

const sessionLogHasMore = computed(() => {
  if (!sessionDetail.value) return false;
  return sessionDetail.value.logs.length >= sessionLogPageSize;
});

type PaginationItem =
  | { type: "page"; value: number; key: string }
  | { type: "ellipsis"; key: string };

const sessionPageItems = computed<PaginationItem[]>(() => {
  const totalPages = Math.max(1, Math.ceil(sessionTotal.value / sessionPageSize.value));
  const current = Math.min(Math.max(1, sessionPage.value), totalPages);
  const items: PaginationItem[] = [];
  const pushPage = (value: number) => {
    items.push({ type: "page", value, key: `p-${value}` });
  };
  const pushEllipsis = (key: string) => {
    items.push({ type: "ellipsis", key });
  };

  if (totalPages <= 7) {
    for (let page = 1; page <= totalPages; page += 1) {
      pushPage(page);
    }
    return items;
  }

  pushPage(1);
  const left = Math.max(2, current - 1);
  const right = Math.min(totalPages - 1, current + 1);

  if (left > 2) {
    pushEllipsis("left");
  }

  for (let page = left; page <= right; page += 1) {
    pushPage(page);
  }

  if (right < totalPages - 1) {
    pushEllipsis("right");
  }

  pushPage(totalPages);
  return items;
});

const equityStatusLabel = computed(() =>
  equitySeries.value.length ? `${equitySeries.value.length} pts` : "No data",
);

const positionChartStatusLabel = computed(() => {
  if (!positionChartAvailable.value) return "No positions";
  if (!selectedPositionSymbol.value) return "Select ticker";
  return "Live";
});

const positionChartSubtitle = computed(() => {
  if (!positionChartAvailable.value) return "No open positions";
  if (!selectedPositionSymbol.value) return "Select a position to view";
  const interval = positionChartInterval.value || "15m";
  return `${selectedPositionSymbol.value} · ${interval} · futures`;
});

const tradingStatusDotClass = computed(() => {
  switch (tradingApiStatus.value.state) {
    case "active":
      return "bg-accent";
    case "missing":
      return "bg-negative";
    case "error":
      return "bg-negative";
    default:
      return "bg-muted";
  }
});

const circuitBreakerStatusLabel = computed(() =>
  store.status.circuitBreakerTriggered ? "Triggered" : "Active",
);

const circuitBreakerStatusClass = computed(() =>
  store.status.circuitBreakerTriggered ? "text-negative" : "text-positive",
);

const filteredLogs = computed(() => {
  if (logFilter.value === "all") return store.logs;
  const key = logFilter.value.toLowerCase();
  return store.logs.filter((log) => (log.log_type || "").toLowerCase() === key);
});

const clearPositionGrace = () => {
  if (positionGraceTimer) {
    clearTimeout(positionGraceTimer);
    positionGraceTimer = null;
  }
  positionGraceDeadline.value = null;
};

const schedulePositionGrace = () => {
  if (positionGraceTimer) return;
  positionGraceDeadline.value = Date.now() + POSITION_GRACE_MS;
  positionGraceTimer = window.setTimeout(() => {
    positionGraceDeadline.value = null;
    positionGraceTimer = null;
    if (store.positions.length === 0) {
      if (activeChart.value === "position") {
        activeChart.value = "equity";
      }
      selectedPositionSymbol.value = null;
    }
  }, POSITION_GRACE_MS);
};

const setActiveChart = (view: "equity" | "position") => {
  if (view === "position" && !positionChartAvailable.value) return;
  activeChart.value = view;
};

const selectPositionSymbol = (symbol: string) => {
  if (!symbol) return;
  selectedPositionSymbol.value = symbol;
  if (positionChartAvailable.value) {
    activeChart.value = "position";
  }
};

watch(
  () => filteredLogs.value.length,
  async () => {
    if (!automationLogAutoScroll.value) return;
    await nextTick();
    if (automationLogRef.value) {
      automationLogRef.value.scrollTop = 0;
    }
  },
);

watch(
  () => positionSymbols.value,
  (symbols, prevSymbols) => {
    const prevCount = prevSymbols?.length ?? 0;
    if (symbols.length > 0) {
      clearPositionGrace();
      if (!selectedPositionSymbol.value || !symbols.includes(selectedPositionSymbol.value)) {
        selectedPositionSymbol.value = symbols[0] || null;
      }
      return;
    }
    if (prevCount > 0) {
      schedulePositionGrace();
    }
  },
  { immediate: true },
);

watch(
  () =>
    activeSessionTab.value === "logs" ? sessionDetail.value?.logs.length ?? 0 : 0,
  async () => {
    if (!sessionLogAutoScroll.value || activeSessionTab.value !== "logs") return;
    await nextTick();
    if (sessionLogRef.value) {
      sessionLogRef.value.scrollTop = 0;
    }
  },
);

watch(
  () => activeSessionTab.value,
  async (tab) => {
    if (tab !== "logs") return;
    if (!sessionLogAutoScroll.value) return;
    await nextTick();
    if (sessionLogRef.value) {
      sessionLogRef.value.scrollTop = 0;
    }
  },
);

const providerLabel = (provider: ProviderOption) => {
  const name = provider.settings?.display_name || provider.name;
  if (!provider.configured) return `${name} (not configured)`;
  return name;
};

const normalizeFuturesSymbol = (raw?: string | null) => {
  const value = (raw || "").toUpperCase();
  const cleaned = value.replace(/[^A-Z0-9]/g, "");
  const withoutPerp = cleaned.replace(/PERP/g, "");
  const baseAsset = withoutPerp.replace(/USDT/g, "");
  const asset = baseAsset || "BTC";
  return `${asset}USDT`;
};

const toTradingViewInterval = (interval: string) => {
  const normalized = interval.trim().toLowerCase();
  if (normalized.endsWith("m")) return normalized.replace("m", "");
  if (normalized.endsWith("h")) {
    const hours = Number(normalized.replace("h", ""));
    if (!Number.isNaN(hours)) return String(hours * 60);
  }
  if (normalized.endsWith("d")) return "D";
  if (normalized.endsWith("w")) return "W";
  if (normalized.endsWith("mo")) return "M";
  return normalized || "15";
};

const tradingViewSymbol = computed(() => {
  if (!selectedPositionSymbol.value) return null;
  const base = normalizeFuturesSymbol(selectedPositionSymbol.value);
  return `BINANCE:${base}.P`;
});

const tradingViewInterval = computed(() =>
  toTradingViewInterval(positionChartInterval.value || "15m"),
);

const modelKey = (model: ModelOption) => {
  if (typeof model === "string") return model;
  return String(model.id ?? model.name ?? "model");
};
const modelValue = (model: ModelOption) => {
  if (typeof model === "string") return model;
  return String(model.id ?? model.name ?? "");
};
const modelLabel = (model: ModelOption) => {
  if (typeof model === "string") return model;
  return String(model.name ?? model.id ?? "");
};

const availableModels = computed<ModelOption[]>(() => {
  const providerEntry = providers.value.find((item) => item.name === automationConfig.value.provider);
  const result: ModelOption[] = [];
  const seen = new Set<string>();
  const append = (model: ModelOption | null | undefined) => {
    if (model === null || model === undefined) return;
    const value = modelValue(model);
    if (!value || seen.has(value)) return;
    seen.add(value);
    result.push(model);
  };

  if (automationConfig.value.model) {
    append(automationConfig.value.model);
  }
  (providerEntry?.models || []).forEach((model) => {
    append(model);
  });
  models.value.forEach((model) => {
    append(model);
  });
  return result;
});

const formatTimestamp = (value?: string | null) => {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "--";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
};

const formatDateTime = (value?: string | null) => {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "--";
  return date.toLocaleString([], {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
};

const formatDuration = (start?: string | null, end?: string | null) => {
  if (!start) return "--";
  const startDate = new Date(start);
  if (Number.isNaN(startDate.getTime())) return "--";
  const endDate = end ? new Date(end) : new Date();
  if (Number.isNaN(endDate.getTime())) return "--";
  const diffMs = Math.max(0, endDate.getTime() - startDate.getTime());
  const totalMinutes = Math.floor(diffMs / 60000);
  const days = Math.floor(totalMinutes / 1440);
  const hours = Math.floor((totalMinutes % 1440) / 60);
  const minutes = totalMinutes % 60;
  const parts = [];
  if (days > 0) parts.push(`${days}d`);
  if (hours > 0 || days > 0) parts.push(`${hours}h`);
  parts.push(`${minutes}m`);
  return parts.join(" ");
};

const formatRelativeDuration = (target?: string | null) => {
  if (!target) return "--";
  const date = new Date(target);
  if (Number.isNaN(date.getTime())) return "--";
  const diffMs = date.getTime() - Date.now();
  const totalSeconds = Math.max(0, Math.floor(Math.abs(diffMs) / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  if (hours > 0) return `${hours}h ${remainingMinutes}m`;
  if (minutes > 0) return `${minutes}m`;
  return `${totalSeconds}s`;
};

const formatUsd = (value?: number | null) => {
  if (value === null || value === undefined || Number.isNaN(value)) return "--";
  return `$${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
};

const formatUsdCompact = (value?: number | null) => {
  if (value === null || value === undefined || Number.isNaN(value)) return "--";
  return `$${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
};

const formatUsdPrecise = (value?: number | null) => {
  if (value === null || value === undefined || Number.isNaN(value)) return "--";
  return `$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
};

const formatUsdSigned = (value?: number | null) => {
  if (value === null || value === undefined || Number.isNaN(value)) return "--";
  const sign = value >= 0 ? "+" : "-";
  return `${sign}$${Math.abs(value).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
};

const formatPercent = (value?: number | null) => {
  if (value === null || value === undefined || Number.isNaN(value)) return "--";
  const sign = value >= 0 ? "+" : "-";
  return `${sign}${Math.abs(value).toFixed(1)}%`;
};

const formatRoePercent = (value?: number | null) => {
  if (value === null || value === undefined || Number.isNaN(value)) return "--";
  const pct = value * 100;
  const sign = pct >= 0 ? "+" : "-";
  return `${sign}${Math.abs(pct).toFixed(2)}%`;
};

const formatNumber = (value?: number | null) => {
  if (value === null || value === undefined || Number.isNaN(value)) return "--";
  return value.toLocaleString(undefined, { maximumFractionDigits: 4 });
};

const formatRate = (value?: number | null) => {
  if (value === null || value === undefined || Number.isNaN(value)) return "--";
  return value >= 10 ? value.toFixed(0) : value.toFixed(1);
};

const formatPromptVersion = (value?: number | null) => {
  if (!value) return "--";
  const match = promptConfigs.value.find((config) => config.id === value);
  return match ? `${match.name} (#${value})` : `#${value}`;
};

const formatSessionPromptSummary = (session: SessionItem) =>
  `NR: ${formatPromptVersion(session.new_resonance_prompt_version)} · PM: ${formatPromptVersion(
    session.position_management_prompt_version,
  )}`;

const pnlClass = (value?: number | null) => {
  if (value === null || value === undefined || Number.isNaN(value)) return "text-muted";
  if (value > 0) return "text-positive";
  if (value < 0) return "text-negative";
  return "text-muted";
};

const positionDirection = (position: AutomationPosition) =>
  (position.direction || position.side || "--").toString().toUpperCase();

const positionLeverage = (position: AutomationPosition) => Number(position.leverage || 1);

const positionSizeUsd = (position: AutomationPosition) =>
  Math.abs(position.size || 0) * (position.mark_price || 0);

const positionMarginUsd = (position: AutomationPosition) => {
  if (position.margin !== null && position.margin !== undefined && position.margin > 0) {
    return position.margin;
  }
  const sizeUsd = positionSizeUsd(position);
  if (!sizeUsd) return null;
  const leverage = positionLeverage(position) || 1;
  return leverage > 0 ? sizeUsd / leverage : sizeUsd;
};

const positionLiqPrice = (position: AutomationPosition) => {
  if (!position.liquidation_price || position.liquidation_price <= 0) return "--";
  return formatNumber(position.liquidation_price);
};

const positionRoe = (position: AutomationPosition) => {
  const pnl = position.unrealized_pnl || 0;
  const margin = positionMarginUsd(position);
  if (!margin || margin <= 0) return 0;
  return (pnl / margin) * 100;
};

const positionSymbolClass = (position: AutomationPosition) => {
  const isSelected = selectedPositionSymbol.value === position.symbol;
  const base = "rounded-sm px-1 transition-colors duration-200 ease-out";
  return isSelected
    ? `${base} bg-accent/10 text-accent`
    : `${base} text-text hover:text-accent`;
};

const positionToneClass = (position: AutomationPosition) => {
  const direction = positionDirection(position);
  if (direction === "LONG") return "text-positive";
  if (direction === "SHORT") return "text-negative";
  return "text-muted";
};

const autoAddStatusClass = (status?: string | null) => {
  const key = (status || "").toUpperCase();
  if (key === "ACTIVE") return "border-positive/40 bg-positive/10 text-positive";
  if (key === "ADDING") return "border-accent/40 bg-accent/10 text-accent";
  if (key === "PROTECTION_PENDING" || key === "WAITING_PROTECTION") {
    return "border-warning/40 bg-warning/10 text-warning";
  }
  if (key === "COMPLETED" || key === "CLOSED") return "border-border bg-panel text-muted";
  if (key === "DETACHED" || key === "ERROR") return "border-negative/40 bg-negative/10 text-negative";
  return "border-border bg-panel text-muted";
};

const positionStopLabel = (position: AutomationPosition) =>
  position.stop_loss !== null && position.stop_loss !== undefined
    ? formatNumber(position.stop_loss)
    : "--";

const positionTakeProfitLabel = (position: AutomationPosition) =>
  position.take_profit !== null && position.take_profit !== undefined
    ? formatNumber(position.take_profit)
    : "--";

const positionOpenedLabel = (position: AutomationPosition) => formatDateTime(position.opened_at);

const positionAutoAddProgress = (position: AutomationPosition) => {
  const autoAdd = position.auto_add;
  if (!autoAdd) return "Not managed";
  return `${autoAdd.filled_add_count}/${autoAdd.max_tranches} resolved`;
};

const autoAddTrancheLabel = (index: number) => `Tranche ${index}`;

const pendingEntryToneClass = (entry: PendingEntryView) => {
  const side = (entry.side || "").toUpperCase();
  if (side === "LONG") return "text-positive";
  if (side === "SHORT") return "text-negative";
  return "text-muted";
};

const pendingEntryAgeLabel = (entry: PendingEntryView) =>
  formatDuration(entry.placed_at, new Date().toISOString());

const pendingEntryExpiresInLabel = (entry: PendingEntryView) =>
  formatRelativeDuration(entry.expires_at);

const pendingEntryFilledLabel = (entry: PendingEntryView) =>
  `${Number(entry.filled_pct || 0).toFixed(1)}%`;

const modeTagClass = (mode?: string | null) => {
  const key = (mode || "").toLowerCase();
  if (key === "prompt_test") return "border-accent/40 bg-accent/15 text-accent";
  if (key === "production") return "border-positive/40 bg-positive/15 text-positive";
  if (key === "dry_run") return "border-warning/40 bg-warning/15 text-warning";
  return "border-border/70 bg-panel/70 text-muted";
};

const positionKey = (position: AutomationPosition) =>
  position.id || `${position.symbol}-${position.direction || position.side || "na"}`;

const tradeLabel = (trade: AutomationTrade) =>
  (trade.action || trade.direction || "--").toString().replace(/_/g, " ").toUpperCase();

const tradeToneClass = (trade: AutomationTrade) => {
  const direction = (trade.direction || "").toString().toUpperCase();
  if (direction === "LONG") return "text-positive";
  if (direction === "SHORT") return "text-negative";
  return "text-muted";
};

const tradeKey = (trade: AutomationTrade) =>
  trade.id || `${trade.symbol}-${trade.created_at || trade.action || "trade"}`;

const logMessageClass = (log: AutomationLog) => {
  const key = logTypeKey(log);
  return {
    "text-scanner": key === "scanner",
    "text-state": key === "state",
    "text-prompt": key === "prompt",
    "text-llm": key === "llm",
    "text-parser": key === "parser",
    "text-guard": key === "guard",
    "text-circuit": key === "circuit",
    "text-execution": key === "execution",
    "text-muted": key === "system",
  };
};

const logTypeKey = (log: AutomationLog) => (log.log_type || "system").toLowerCase();

const isPromptLog = (log: AutomationLog) => {
  const prompt = log.data?.prompt_text;
  return typeof prompt === "string" && prompt.trim().length > 0;
};

const promptText = (log: AutomationLog) => {
  const prompt = log.data?.prompt_text;
  if (typeof prompt !== "string") return "";
  return prompt.trim();
};

const isLlmResponseLog = (log: AutomationLog) => {
  if ((log.log_type || "").toLowerCase() !== "llm") return false;
  const response = log.data?.llm_response;
  return typeof response === "string" && response.trim().length > 0;
};

const llmResponseText = (log: AutomationLog) => {
  const response = log.data?.llm_response;
  if (typeof response !== "string") return "";
  return response.trim();
};

const isLlmParseLog = (log: AutomationLog) => {
  const key = (log.log_type || "").toLowerCase();
  if (key !== "llm" && key !== "parser") return false;
  const parseResult = log.data?.parse_result;
  return Boolean(parseResult && typeof parseResult === "object");
};

const llmParseText = (log: AutomationLog) => {
  const parseResult = log.data?.parse_result;
  if (!parseResult || typeof parseResult !== "object") return "";
  try {
    return JSON.stringify(parseResult, null, 2);
  } catch {
    return String(parseResult);
  }
};

const isDetailLog = (log: AutomationLog) => {
  const details = log.data?.details;
  return Boolean(details && typeof details === "object" && Object.keys(details).length > 0);
};

const detailText = (log: AutomationLog) => {
  const details = log.data?.details;
  if (!details || typeof details !== "object") return "";
  try {
    return JSON.stringify(details, null, 2);
  } catch {
    return String(details);
  }
};

const logMessage = (log: AutomationLog) => {
  const data = log.data;
  if (!data) return "No details";
  if (!data.message && typeof data.event_type === "string") {
    const rebuilt = stageMessage(data.event_type, data);
    if (rebuilt) return rebuilt;
  }
  if (typeof data.message === "string") {
    if (isLlmResponseLog(log)) {
      const symbol = typeof data.symbol === "string" ? data.symbol : null;
      return symbol ? `LLM response captured · ${symbol}` : "LLM response captured.";
    }
    const line = data.message.split("\n")[0];
    return line || data.message;
  }
  if (typeof data.event_type === "string") return data.event_type;
  try {
    return JSON.stringify(data);
  } catch {
    return String(data);
  }
};

const handleAutomationLogScroll = () => {
  if (!automationLogRef.value) return;
  automationLogAutoScroll.value = automationLogRef.value.scrollTop <= 0;
};

const handleSessionLogScroll = () => {
  if (!sessionLogRef.value || activeSessionTab.value !== "logs") return;
  sessionLogAutoScroll.value = sessionLogRef.value.scrollTop <= 0;
};

const positionsMarginExposure = computed(() =>
  store.positions.reduce((sum, position) => sum + (positionMarginUsd(position) || 0), 0),
);

const positionsExposure = computed(() =>
  store.positions.reduce((sum, position) => sum + positionSizeUsd(position), 0),
);

const positionsUpnl = computed(() =>
  store.positions.reduce((sum, position) => sum + (position.unrealized_pnl || 0), 0),
);

const updateConfig = (updates: Partial<AutomationConfig>) => {
  automationConfig.value = { ...automationConfig.value, ...updates };
  cachedAutomationConfig = { ...automationConfig.value };
  writeAutomationConfigStorage(automationConfig.value);
};

const buildAutomationConfigPayload = () => ({
  execution_mode: automationConfig.value.execution_mode,
  ema_interval_seconds: automationConfig.value.ema_interval_seconds,
  quant_interval_seconds: automationConfig.value.quant_interval_seconds,
  pending_entry_timeout_seconds: automationConfig.value.pending_entry_timeout_seconds,
  max_positions: automationConfig.value.max_positions,
  auto_add_enabled: automationConfig.value.auto_add_enabled,
  auto_add_trigger_atr_multiple: automationConfig.value.auto_add_trigger_atr_multiple,
  auto_add_tranche_margin_pct: automationConfig.value.auto_add_tranche_margin_pct,
  auto_add_max_tranches: automationConfig.value.auto_add_max_tranches,
  provider: automationConfig.value.provider || null,
  model: automationConfig.value.model || null,
  reasoning_effort: automationConfig.value.reasoning_effort || null,
  include_entry_timing_15m_chart: automationConfig.value.include_entry_timing_15m_chart,
  use_all_monitored_interval_charts: automationConfig.value.use_all_monitored_interval_charts,
  reverse_order_enabled: automationConfig.value.reverse_order_enabled,
  vegas_prompt_configs: automationConfig.value.vegas_prompt_configs || null,
});

const automationConfigPayloadSignature = (payload: AutomationConfigPayload) => JSON.stringify(payload);

let automationConfigPersistInFlight = false;
let automationConfigPersistQueued = false;

const normalizePromptConfigs = (value: unknown) => {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, number>;
  }
  return null;
};

const applyAutomationConfigPayload = (payload: AutomationConfigPayload) => {
  const updates: Partial<AutomationConfig> = {};
  if (typeof payload.execution_mode === "string") {
    updates.execution_mode = payload.execution_mode;
  }
  if (typeof payload.ema_interval_seconds === "number") {
    updates.ema_interval_seconds = payload.ema_interval_seconds;
  }
  if (typeof payload.quant_interval_seconds === "number") {
    updates.quant_interval_seconds = payload.quant_interval_seconds;
  }
  if (typeof payload.pending_entry_timeout_seconds === "number") {
    updates.pending_entry_timeout_seconds = payload.pending_entry_timeout_seconds;
  }
  if (typeof payload.max_positions === "number") {
    updates.max_positions = payload.max_positions;
  }
  if (typeof payload.auto_add_enabled === "boolean") {
    updates.auto_add_enabled = payload.auto_add_enabled;
  }
  if (typeof payload.auto_add_trigger_atr_multiple === "number") {
    updates.auto_add_trigger_atr_multiple = payload.auto_add_trigger_atr_multiple;
  }
  if (typeof payload.auto_add_tranche_margin_pct === "number") {
    updates.auto_add_tranche_margin_pct = payload.auto_add_tranche_margin_pct;
  }
  if (typeof payload.auto_add_max_tranches === "number") {
    updates.auto_add_max_tranches = payload.auto_add_max_tranches;
  }
  if (typeof payload.include_entry_timing_15m_chart === "boolean") {
    updates.include_entry_timing_15m_chart = payload.include_entry_timing_15m_chart;
  }
  if (typeof payload.use_all_monitored_interval_charts === "boolean") {
    updates.use_all_monitored_interval_charts = payload.use_all_monitored_interval_charts;
  }
  if (typeof payload.reverse_order_enabled === "boolean") {
    updates.reverse_order_enabled = payload.reverse_order_enabled;
  }
  if ("provider" in payload) {
    updates.provider = payload.provider ? String(payload.provider) : "";
  }
  if ("model" in payload) {
    updates.model = payload.model ? String(payload.model) : "";
  }
  if ("reasoning_effort" in payload) {
    updates.reasoning_effort = normalizeReasoningEffort(payload.reasoning_effort);
  }
  if ("vegas_prompt_configs" in payload) {
    updates.vegas_prompt_configs = normalizePromptConfigs(payload.vegas_prompt_configs) || null;
  }
  const provider = updates.provider ?? automationConfig.value.provider;
  const reasoning = updates.reasoning_effort ?? automationConfig.value.reasoning_effort;
  if ((provider || "").trim().toLowerCase() === "codex" && !reasoning) {
    updates.reasoning_effort = "medium";
  }
  if (Object.keys(updates).length > 0) {
    updateConfig(updates);
  }
};

const persistAutomationConfig = async () => {
  if (automationConfigPersistInFlight) {
    automationConfigPersistQueued = true;
    return;
  }

  automationConfigPersistInFlight = true;
  const payload = buildAutomationConfigPayload();
  const payloadSignature = automationConfigPayloadSignature(payload);

  try {
    const response = await fetch("/api/v1/automation/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    const hasNewerLocalChanges =
      automationConfigPersistQueued ||
      automationConfigPayloadSignature(buildAutomationConfigPayload()) !== payloadSignature;
    if (!hasNewerLocalChanges && response.ok && data?.data) {
      applyAutomationConfigPayload(data.data as AutomationConfigPayload);
    }
  } catch {
    // Ignore persistence errors.
  } finally {
    automationConfigPersistInFlight = false;
    if (automationConfigPersistQueued) {
      automationConfigPersistQueued = false;
      void persistAutomationConfig();
    }
  }
};

const updateConfigPersisted = (updates: Partial<AutomationConfig>) => {
  updateConfig(updates);
  void persistAutomationConfig();
};

const toPercent = (value: unknown, fallback: number) => {
  if (typeof value !== "number" || Number.isNaN(value)) return fallback;
  return Number((value * 100).toFixed(2));
};

const fromPercent = (value: unknown, fallback: number) => {
  if (typeof value !== "number" || Number.isNaN(value)) return fallback;
  return value / 100;
};

const normalizeSymbols = (symbols: unknown): string[] => {
  if (!Array.isArray(symbols)) return [];
  return symbols
    .map((symbol) => String(symbol).trim().toUpperCase())
    .filter((symbol) => symbol.length > 0);
};

const symbolsLabel = (symbols: string[]) => symbols.join(", ");

const sortTradeGuardConfig = () => {
  tradeGuardConfig.value = {
    ...tradeGuardConfig.value,
    leverage_tiers: [...tradeGuardConfig.value.leverage_tiers].sort(
      (left, right) => right.leverage - left.leverage,
    ),
    position_tier_ranges: [...tradeGuardConfig.value.position_tier_ranges].sort(
      (left, right) => left.tier - right.tier,
    ),
  };
};

const updateTradeGuardConfig = (updates: Partial<TradeGuardConfigForm>) => {
  tradeGuardConfig.value = { ...tradeGuardConfig.value, ...updates };
};

const buildTradeGuardPayload = (): TradeGuardConfigPayload => ({
  min_confidence: tradeGuardConfig.value.min_confidence,
  min_position_size: tradeGuardConfig.value.min_position_size,
  sl_min_roe: fromPercent(tradeGuardConfig.value.sl_min_roe_pct, 0.03),
  sl_max_roe: fromPercent(tradeGuardConfig.value.sl_max_roe_pct, 0.05),
  tp_min_roe: fromPercent(tradeGuardConfig.value.tp_min_roe_pct, 0.05),
  tp_max_roe: fromPercent(tradeGuardConfig.value.tp_max_roe_pct, 0.2),
  dust_threshold_usd: tradeGuardConfig.value.dust_threshold_usd,
  default_leverage: Number(tradeGuardConfig.value.default_leverage) || 1,
  leverage_tiers: tradeGuardConfig.value.leverage_tiers.map((tier) => ({
    leverage: Number(tier.leverage) || 1,
    symbols: normalizeSymbols(tier.symbols),
  })),
  position_tier_ranges: tradeGuardConfig.value.position_tier_ranges.map((range) => ({
    tier: Number(range.tier) || 1,
    min_pct: fromPercent(range.min_pct, 0),
    max_pct: fromPercent(range.max_pct, 0),
  })),
});

const applyTradeGuardConfigPayload = (payload: TradeGuardConfigPayload) => {
  const leverage_tiers = Array.isArray(payload.leverage_tiers)
    ? payload.leverage_tiers.map((tier) => ({
        leverage: Number(tier.leverage) || 1,
        symbols: normalizeSymbols(tier.symbols),
      }))
    : tradeGuardConfigDefaults.leverage_tiers;

  const position_tier_ranges = Array.isArray(payload.position_tier_ranges)
    ? payload.position_tier_ranges.map((range) => ({
        tier: Number(range.tier) || 1,
        min_pct: toPercent(range.min_pct, 0),
        max_pct: toPercent(range.max_pct, 0),
      }))
    : tradeGuardConfigDefaults.position_tier_ranges;

  const minConfidence = Number.isFinite(payload.min_confidence)
    ? payload.min_confidence
    : tradeGuardConfigDefaults.min_confidence;
  const minPositionSize = Number.isFinite(payload.min_position_size)
    ? payload.min_position_size
    : tradeGuardConfigDefaults.min_position_size;
  const dustThreshold = Number.isFinite(payload.dust_threshold_usd)
    ? payload.dust_threshold_usd
    : tradeGuardConfigDefaults.dust_threshold_usd;
  const parsedDefaultLev = Number.isFinite(payload.default_leverage)
    ? payload.default_leverage
    : tradeGuardConfigDefaults.default_leverage;
  const defaultLeverage = Math.min(5, Math.max(1, parsedDefaultLev));

  tradeGuardConfig.value = {
    min_confidence: minConfidence,
    min_position_size: minPositionSize,
    sl_min_roe_pct: toPercent(payload.sl_min_roe, tradeGuardConfigDefaults.sl_min_roe_pct),
    sl_max_roe_pct: toPercent(payload.sl_max_roe, tradeGuardConfigDefaults.sl_max_roe_pct),
    tp_min_roe_pct: toPercent(payload.tp_min_roe, tradeGuardConfigDefaults.tp_min_roe_pct),
    tp_max_roe_pct: toPercent(payload.tp_max_roe, tradeGuardConfigDefaults.tp_max_roe_pct),
    dust_threshold_usd: dustThreshold,
    default_leverage: defaultLeverage,
    leverage_tiers,
    position_tier_ranges,
  };
  sortTradeGuardConfig();
};

const persistTradeGuardConfig = async () => {
  try {
    const response = await fetch("/api/v1/trade-guard/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildTradeGuardPayload()),
    });
    const data = await response.json();
    if (response.ok && data?.data) {
      applyTradeGuardConfigPayload(data.data as TradeGuardConfigPayload);
    }
  } catch {
    // Ignore persistence errors.
  }
};

const updateTradeGuardConfigPersisted = (updates: Partial<TradeGuardConfigForm>) => {
  updateTradeGuardConfig(updates);
  void persistTradeGuardConfig();
};

const handleTierRangesChanged = () => {
  sortTradeGuardConfig();
  void persistTradeGuardConfig();
};

const addPositionTierRange = () => {
  const ranges = tradeGuardConfig.value.position_tier_ranges;
  const nextTier = ranges.length > 0 ? Math.max(...ranges.map((range) => range.tier)) + 1 : 1;
  tradeGuardConfig.value.position_tier_ranges = [
    ...ranges,
    { tier: nextTier, min_pct: 10, max_pct: 20 },
  ];
  handleTierRangesChanged();
};

const removePositionTierRange = (index: number) => {
  tradeGuardConfig.value.position_tier_ranges = tradeGuardConfig.value.position_tier_ranges.filter(
    (_, idx) => idx !== index,
  );
  handleTierRangesChanged();
};

const handleLeverageTiersChanged = () => {
  sortTradeGuardConfig();
  void persistTradeGuardConfig();
};

const addLeverageTier = () => {
  tradeGuardConfig.value.leverage_tiers = [
    ...tradeGuardConfig.value.leverage_tiers,
    { leverage: 1, symbols: [] },
  ];
  handleLeverageTiersChanged();
};

const removeLeverageTier = (index: number) => {
  tradeGuardConfig.value.leverage_tiers = tradeGuardConfig.value.leverage_tiers.filter(
    (_, idx) => idx !== index,
  );
  handleLeverageTiersChanged();
};

const updateLeverageSymbols = (index: number, event: Event) => {
  const value = (event.target as HTMLInputElement).value;
  const symbols = value
    .split(/[,\s]+/)
    .map((symbol) => symbol.trim().toUpperCase())
    .filter((symbol) => symbol.length > 0);
  if (!tradeGuardConfig.value.leverage_tiers[index]) return;
  tradeGuardConfig.value.leverage_tiers[index].symbols = symbols;
  handleLeverageTiersChanged();
};

const updateCircuitBreaker = (updates: Partial<CircuitBreakerConfig>) => {
  circuitBreakerConfig.value = { ...circuitBreakerConfig.value, ...updates };
};

const setExecutionMode = (mode: string) => {
  if (automationConfig.value.execution_mode === mode) return;
  if (mode === "production") {
    pendingExecutionMode.value = mode;
    liveModeConfirmed.value = false;
    showLiveModeConfirm.value = true;
    executionModeSelection.value = automationConfig.value.execution_mode;
    return;
  }
  updateConfigPersisted({ execution_mode: mode });
};

const handleProviderChange = async (event: Event) => {
  const provider = (event.target as HTMLSelectElement).value;
  if (automationConfig.value.provider === provider) return;
  models.value = [];
  automationConfig.value.model = "";
  const nextUpdates: Partial<AutomationConfig> = { provider, model: "" };
  if (provider.trim().toLowerCase() === "codex" && !automationConfig.value.reasoning_effort) {
    nextUpdates.reasoning_effort = "medium";
  }
  updateConfigPersisted(nextUpdates);
  await loadModels(provider);
};

const handleModelChange = (event: Event) => {
  const model = (event.target as HTMLSelectElement).value;
  if (automationConfig.value.model === model) return;
  updateConfigPersisted({ model });
};

const handleReasoningEffortChange = (event: Event) => {
  const reasoning_effort = normalizeReasoningEffort((event.target as HTMLSelectElement).value);
  if (automationConfig.value.reasoning_effort === reasoning_effort) return;
  updateConfigPersisted({ reasoning_effort });
};

const vegasPromptValue = (key: string) => {
  const configs = automationConfig.value.vegas_prompt_configs;
  if (!configs) return "";
  const value = configs[key];
  if (!value) return "";
  return String(value);
};

const handleVegasPromptChange = (key: string, event: Event) => {
  const value = (event.target as HTMLSelectElement).value;
  const parsed = value ? Number(value) : null;
  const nextConfigs = { ...(automationConfig.value.vegas_prompt_configs || {}) };
  if (parsed && Number.isFinite(parsed)) {
    nextConfigs[key] = parsed;
  } else {
    delete nextConfigs[key];
  }
  updateConfigPersisted({
    vegas_prompt_configs: Object.keys(nextConfigs).length > 0 ? nextConfigs : null,
  });
};

const handleToggle = async () => {
  if (store.status.isRunning) {
    await stopAutomation();
  } else {
    await startAutomation();
  }
};

const startAutomation = async () => {
  if (!automationConfig.value.provider || !automationConfig.value.model) {
    configError.value = "Select a provider and model before starting.";
    return;
  }
  isStarting.value = true;
  configError.value = "";
  try {
    await persistAutomationConfig();
    const response = await fetch("/api/v1/automation/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        execution_mode: automationConfig.value.execution_mode,
        provider: automationConfig.value.provider,
        model: automationConfig.value.model,
        reasoning_effort: automationConfig.value.reasoning_effort || null,
        ema_interval_seconds: automationConfig.value.ema_interval_seconds,
        quant_interval_seconds: automationConfig.value.quant_interval_seconds,
        pending_entry_timeout_seconds: automationConfig.value.pending_entry_timeout_seconds,
        max_positions: automationConfig.value.max_positions,
        auto_add_enabled: automationConfig.value.auto_add_enabled,
        auto_add_trigger_atr_multiple: automationConfig.value.auto_add_trigger_atr_multiple,
        auto_add_tranche_margin_pct: automationConfig.value.auto_add_tranche_margin_pct,
        auto_add_max_tranches: automationConfig.value.auto_add_max_tranches,
        include_entry_timing_15m_chart: automationConfig.value.include_entry_timing_15m_chart,
        use_all_monitored_interval_charts:
          automationConfig.value.use_all_monitored_interval_charts,
        reverse_order_enabled: automationConfig.value.reverse_order_enabled,
        vegas_prompt_configs: automationConfig.value.vegas_prompt_configs || null,
      }),
    });
    const data = await response.json();
    if (!response.ok || !data?.data) {
      throw new Error(data?.error || "Failed to start automation.");
    }
    store.applyState(data.data);
    store.status.isRunning = true;
  } catch (error) {
    configError.value = error instanceof Error ? error.message : "Failed to start automation.";
  } finally {
    isStarting.value = false;
  }
};

const stopAutomation = async () => {
  isStopping.value = true;
  configError.value = "";
  try {
    const response = await fetch("/api/v1/automation/stop", { method: "POST" });
    const data = await response.json();
    if (!response.ok || !data?.data) {
      throw new Error(data?.error || "Failed to stop automation.");
    }
    store.applyState(data.data);
    store.status.isRunning = false;
  } catch (error) {
    configError.value = error instanceof Error ? error.message : "Failed to stop automation.";
  } finally {
    isStopping.value = false;
  }
};

const handleEmergencyStop = async () => {
  const confirmed = window.confirm("Emergency stop will halt automation. Continue?");
  if (!confirmed) return;
  await stopAutomation();
};

const handleClosePosition = async (position: AutomationPosition) => {
  const symbol = position?.symbol;
  if (!symbol) return;
  const confirmed = window.confirm(`Close ${symbol} at market price?`);
  if (!confirmed) return;

  closingPositionSymbol.value = symbol;
  try {
    const response = await fetch("/api/v1/automation/positions/close", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol }),
    });
    const data = await response.json().catch(() => null);
    if (!response.ok || data?.data?.success === false) {
      throw new Error(data?.data?.error || data?.error || "Failed to close position.");
    }
    await store.refreshPositions();
  } catch (error) {
    console.error(error);
  } finally {
    if (closingPositionSymbol.value === symbol) {
      closingPositionSymbol.value = null;
    }
  }
};

const loadAutomationState = async () => {
  try {
    const response = await fetch("/api/v1/automation/state");
    const data = await response.json();
    if (data?.data) {
      const state = data.data;
      store.applyState(state);
      if (state.is_running) {
        applyAutomationConfigPayload(state as AutomationConfigPayload);
      }
    }
  } catch {
    // Ignore load errors
  }
};

const loadAutomationConfig = async () => {
  try {
    const response = await fetch("/api/v1/automation/config");
    const data = await response.json();
    if (data?.data) {
      applyAutomationConfigPayload(data.data as AutomationConfigPayload);
    }
  } catch {
    // Ignore load errors
  }
};

const loadTradeGuardConfig = async () => {
  try {
    const response = await fetch("/api/v1/trade-guard/config");
    const data = await response.json();
    if (data?.data) {
      applyTradeGuardConfigPayload(data.data as TradeGuardConfigPayload);
    }
  } catch {
    // Ignore load errors
  }
};

const loadProviders = async () => {
  try {
    const cached = readProvidersCache();
    if (cached && cached.length > 0 && providers.value.length === 0) {
      providers.value = cached;
    }
    const response = await fetch("/api/v1/ai/providers");
    const data = await response.json();
    if (data?.data) {
      providers.value = data.data;
      writeProvidersCache(data.data);
    }
  } catch {
    // Ignore load errors
  }
};

const loadModels = async (provider: string) => {
  if (!provider) {
    models.value = [];
    return;
  }
  const normalized = provider.toLowerCase();
  if (normalized !== "codex") {
    const cached = readModelCache(provider);
    if (cached && cached.length > 0) {
      models.value = cached;
      return;
    }
  }
  const providerEntry = providers.value.find((item) => item.name === provider);
  if (providerEntry?.models && providerEntry.models.length > 0) {
    models.value = [...providerEntry.models];
  }
  try {
    const response = await fetch(`/api/v1/ai/providers/${provider}/models`);
    const data = await response.json();
    if (data?.data?.models) {
      models.value = data.data.models;
      writeModelCache(provider, data.data.models);
    }
  } catch {
    models.value = [];
  }
};

const loadPromptConfigs = async () => {
  try {
    const cached = readPromptConfigCache();
    if (cached && cached.length > 0 && promptConfigs.value.length === 0) {
      promptConfigs.value = cached;
    }
    const response = await fetch("/api/v1/agent/templates");
    const data = await response.json();
    if (Array.isArray(data?.data)) {
      const mapped = data.data.map((config: PromptConfigOption) => ({
        id: config.id,
        name: config.name,
      }));
      promptConfigs.value = mapped;
      writePromptConfigCache(mapped);
    }
  } catch {
    // Ignore load errors
  }
};

const loadMonitoredIntervals = async () => {
  try {
    const response = await fetch("/api/v1/market/monitored-intervals");
    const data = await response.json();
    if (Array.isArray(data?.data) && data.data.length > 0) {
      if (!data.data.includes(positionChartInterval.value)) {
        positionChartInterval.value = data.data[0];
      }
    }
  } catch {
    // Ignore load errors
  }
};

const loadLogs = async () => {
  // Logs are streamed via realtime; keep existing entries when navigating.
};

const loadPositions = async () => {
  try {
    const response = await fetch("/api/v1/automation/positions");
    const data = await response.json();
    if (data?.data?.positions) {
      store.positions = data.data.positions;
    }
  } catch {
    // Ignore load errors
  }
};

const loadPendingEntries = async () => {
  try {
    const response = await fetch("/api/v1/automation/pending-entries");
    const data = await response.json();
    if (Array.isArray(data?.data?.entries)) {
      pendingEntries.value = data.data.entries as PendingEntryView[];
    }
  } catch {
    // Ignore load errors
  }
};

const handleCancelPendingEntry = async (entry: PendingEntryView) => {
  if (!entry?.id) return;
  const confirmed = window.confirm(`Cancel pending ${entry.symbol} limit entry?`);
  if (!confirmed) return;
  cancelingPendingEntryId.value = entry.id;
  try {
    await fetch(`/api/v1/automation/pending-entries/${entry.id}/cancel`, {
      method: "POST",
    });
    await Promise.all([loadPendingEntries(), store.refreshPositions()]);
  } catch {
    // Ignore cancel errors.
  } finally {
    if (cancelingPendingEntryId.value === entry.id) {
      cancelingPendingEntryId.value = null;
    }
  }
};

const loadTrades = async () => {
  store.trades = [];
};

const loadTradingApiStatus = async () => {
  tradingApiStatus.value = {
    state: "loading",
    label: "Checking...",
    detail: "",
    isTestnet: false,
  };

  try {
    const exchangeResponse = await fetch("/api/v1/portfolio/exchanges/active");
    if (exchangeResponse.ok) {
      const exchangeData = await exchangeResponse.json();
      if (exchangeData?.data) {
        const exchange = exchangeData.data;
        const exchangeNames: Record<string, string> = {
          hyperliquid: "Hyperliquid",
          binance: "Binance",
          okx: "OKX",
        };
        const label = exchangeNames[exchange.exchange] || exchange.exchange || "Exchange";
        tradingApiStatus.value = {
          state: "active",
          label,
          detail: exchange.name || "Active account",
          isTestnet: Boolean(exchange.is_testnet),
        };
        return;
      }
    }

    tradingApiStatus.value = {
      state: "missing",
      label: "Not configured",
      detail: "No exchange account selected",
      isTestnet: false,
    };
  } catch {
    tradingApiStatus.value = {
      state: "error",
      label: "Status unavailable",
      detail: "Unable to load trading API status",
      isTestnet: false,
    };
  }
};

const loadCircuitBreaker = async () => {
  // Placeholder: circuit breaker config is not wired to the new backend yet.
};

const loadSessions = async () => {
  sessionsLoading.value = true;
  sessionError.value = "";
  sessions.value = [];
  sessionDetail.value = null;
  try {
    const offset = (sessionPage.value - 1) * sessionPageSize.value;
    const response = await fetch(
      `/api/v1/automation/sessions?limit=${sessionPageSize.value}&offset=${offset}`,
    );
    const data = await response.json();
    if (!response.ok || !data?.data?.sessions) {
      throw new Error(data?.detail || data?.error || "Failed to load sessions.");
    }
    sessions.value = data.data.sessions as SessionItem[];
    sessionTotal.value = Number(data.data.total) || 0;
  } catch (error) {
    sessionError.value = error instanceof Error ? error.message : "Failed to load sessions.";
    sessionTotal.value = 0;
  } finally {
    sessionsLoading.value = false;
  }
};

const loadSessionDetail = async (sessionId: string, page = 1) => {
  if (!sessionId) return;
  const isSameSession = selectedSessionId.value === sessionId;
  selectedSessionId.value = sessionId;
  sessionDetailLoading.value = true;
  sessionError.value = "";
  if (!isSameSession) {
    sessionDetail.value = null;
  }
  sessionLogPage.value = Math.max(1, page);
  const logOffset = (sessionLogPage.value - 1) * sessionLogPageSize;
  try {
    const response = await fetch(
      `/api/v1/automation/sessions/${sessionId}?log_limit=${sessionLogPageSize}&log_offset=${logOffset}`,
    );
    const data = await response.json();
    if (!response.ok || !data?.data) {
      throw new Error(data?.detail || data?.error || "Failed to load session detail.");
    }
    sessionDetail.value = data.data as SessionDetail;
  } catch (error) {
    sessionError.value = error instanceof Error ? error.message : "Failed to load session detail.";
  } finally {
    sessionDetailLoading.value = false;
  }
};

const openSessionModal = async () => {
  showSessionModal.value = true;
  activeSessionTab.value = "logs";
  selectedSessionId.value = null;
  sessionDetail.value = null;
  sessionPage.value = 1;
  sessionLogPage.value = 1;
  await loadSessions();
};

const changeSessionPage = async (nextPage: number) => {
  if (nextPage < 1) return;
  sessionPage.value = nextPage;
  await loadSessions();
};

const changeSessionLogPage = async (nextPage: number) => {
  if (!selectedSessionId.value) return;
  if (nextPage < 1) return;
  await loadSessionDetail(selectedSessionId.value, nextPage);
};

const handleDeleteSession = async (sessionId: string) => {
  if (!sessionId) return;
  const confirmed = window.confirm("Delete this session record? This cannot be undone.");
  if (!confirmed) return;
  try {
    const response = await fetch(`/api/v1/automation/sessions/${sessionId}`, {
      method: "DELETE",
    });
    const data = await response.json();
    if (!response.ok || !data?.data?.deleted) {
      throw new Error(data?.detail || data?.error || "Failed to delete session.");
    }
    sessions.value = sessions.value.filter((session) => session.id !== sessionId);
    sessionTotal.value = Math.max(0, sessionTotal.value - 1);
    if (selectedSessionId.value === sessionId) {
      selectedSessionId.value = null;
      sessionDetail.value = null;
    }
    if (sessions.value.length === 0 && sessionPage.value > 1) {
      sessionPage.value = sessionPage.value - 1;
      await loadSessions();
    }
  } catch (error) {
    sessionError.value = error instanceof Error ? error.message : "Failed to delete session.";
  }
};

const toggleExportMenu = (sessionId: string) => {
  exportMenuSessionId.value = exportMenuSessionId.value === sessionId ? null : sessionId;
};

const handleExportSession = async (session: SessionItem, mode: SessionExportMode) => {
  if (!session?.id) return;
  exportMenuSessionId.value = null;
  exportingSessionId.value = session.id;
  try {
    const detail = await _getSessionDetailForExport(session.id);
    if (!detail) {
      throw new Error("Session logs unavailable.");
    }
    const payload =
      mode === "raw"
        ? _buildRawExport(detail)
        : mode === "prompt_llm"
          ? _buildPromptLlmExport(detail)
          : _buildLlmExport(detail, mode === "llm_trades");
    const fileName = _buildSessionExportName(detail.session, mode);
    _downloadJson(payload, fileName);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Failed to export session logs.";
    window.alert(message);
  } finally {
    exportingSessionId.value = null;
  }
};

const _getSessionDetailForExport = async (sessionId: string): Promise<SessionDetail | null> => {
  const response = await fetch(`/api/v1/automation/sessions/${sessionId}/export`);
  const data = await response.json().catch(() => null);
  if (!response.ok || !data?.data) {
    return null;
  }
  const payload = data.data as {
    session: SessionItem;
    logs: AutomationLog[];
    trades: AutomationTrade[];
  };
  return {
    session: payload.session,
    logs: payload.logs,
    trades: payload.trades,
  };
};

const _buildSessionExportName = (session: SessionItem, mode: SessionExportMode) => {
  const safeId = (session.id || "session").replace(/[^a-zA-Z0-9_-]+/g, "-");
  const modeLabel =
    mode === "raw" ? "raw" : mode === "llm_trades" ? "llm-trades" : mode === "prompt_llm" ? "prompt-llm" : "llm";
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  return `${safeId}-${modeLabel}-${stamp}.json`;
};

const _downloadJson = (payload: unknown, fileName: string) => {
  const text = JSON.stringify(payload, null, 2);
  const blob = new Blob([text], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
};

const _buildRawExport = (detail: SessionDetail) => ({
  exported_at: new Date().toISOString(),
  session: detail.session,
  logs: detail.logs,
});

const _buildLlmExport = (detail: SessionDetail, includeTrades: boolean) => {
  const responses = _extractLlmResponses(detail.logs);
  const payload: Record<string, unknown> = {
    exported_at: new Date().toISOString(),
    session: _sessionSummary(detail.session),
    responses,
  };
  if (includeTrades) {
    payload.trades = _simplifyTrades(detail.trades);
  }
  return payload;
};

const _buildPromptLlmExport = (detail: SessionDetail) => {
  const responses = _extractLlmResponses(detail.logs, true);
  return {
    exported_at: new Date().toISOString(),
    session: _sessionSummary(detail.session),
    responses,
  };
};

const _sessionSummary = (session: SessionItem) => ({
  id: session.id,
  started_at: session.started_at ?? null,
  ended_at: session.ended_at ?? null,
  execution_mode: session.execution_mode ?? null,
  provider: session.provider ?? null,
  model: session.model ?? null,
});

const _extractLlmResponses = (logs: AutomationLog[], includePrompt = false) => {
  const contextByRequest = _buildPromptContext(logs);
  const promptByRequest = includePrompt ? _buildPromptTextMap(logs) : {};
  return logs
    .filter((log) => isLlmResponseLog(log))
    .map((log) => {
      const data = log.data || {};
      const requestId = typeof data.request_id === "string" ? data.request_id : null;
      const context = requestId ? contextByRequest[requestId] : null;
      const promptText = requestId ? promptByRequest[requestId] : null;
      const tickers = _mergeStringArrays(
        context?.tickers,
        _extractSymbols(data),
        _normalizeStringArray(data.symbol || data.ticker),
      );
      const intervals = _mergeStringArrays(
        context?.intervals,
        _normalizeStringArray(data.interval || data.intervals),
      );

      const entry: Record<string, unknown> = {
        timestamp: log.created_at,
        cycle_number: log.cycle_number ?? null,
        request_id: requestId,
        tickers,
        intervals,
        llm_response: typeof data.llm_response === "string" ? data.llm_response.trim() : "",
      };
      if (includePrompt) {
        entry.prompt_text = promptText || "";
      }
      return entry;
    })
    .filter((entry) => entry.llm_response);
};

const _buildPromptContext = (logs: AutomationLog[]) => {
  const context: Record<string, { tickers?: string[]; intervals?: string[] }> = {};
  logs.forEach((log) => {
    const data = log.data;
    if (!data || typeof data !== "object") return;
    const requestId = typeof data.request_id === "string" ? data.request_id : null;
    if (!requestId) return;
    const tickers = _normalizeStringArray(data.tickers);
    const intervals = _normalizeStringArray(data.intervals);
    if (tickers.length || intervals.length) {
      context[requestId] = {
        tickers: tickers.length ? tickers : context[requestId]?.tickers,
        intervals: intervals.length ? intervals : context[requestId]?.intervals,
      };
    }
  });
  return context;
};

const _buildPromptTextMap = (logs: AutomationLog[]) => {
  const promptMap: Record<string, string> = {};
  logs.forEach((log) => {
    const data = log.data;
    if (!data || typeof data !== "object") return;
    const requestId = typeof data.request_id === "string" ? data.request_id : null;
    if (!requestId) return;
    const prompt = data.prompt_text;
    if (typeof prompt === "string" && prompt.trim()) {
      promptMap[requestId] = prompt.trim();
    }
  });
  return promptMap;
};

const _extractSymbols = (data: Record<string, unknown>) => {
  const ideas = Array.isArray(data.execution_ideas) ? data.execution_ideas : [];
  const symbols = ideas
    .map((idea) => (idea && typeof idea === "object" ? (idea as Record<string, unknown>).symbol : null))
    .filter((symbol) => typeof symbol === "string") as string[];
  return _uniqueStrings(symbols);
};

const _simplifyTrades = (trades: AutomationTrade[]) =>
  trades.map((trade) => ({
    symbol: trade.symbol,
    action: trade.action || trade.direction || null,
    size_usd: trade.size_usd ?? null,
    entry_price: trade.entry_price ?? null,
    exit_price: trade.exit_price ?? null,
    pnl: trade.pnl ?? null,
    status: trade.status ?? null,
    created_at: trade.created_at ?? null,
  }));

const _normalizeStringArray = (value: unknown) => {
  if (Array.isArray(value)) {
    return _uniqueStrings(value.map((item) => String(item)));
  }
  if (typeof value === "string") {
    const trimmed = value.trim();
    return trimmed ? [trimmed] : [];
  }
  return [];
};

const _mergeStringArrays = (...groups: Array<string[] | undefined>) => {
  const merged: string[] = [];
  groups.forEach((group) => {
    if (!group) return;
    merged.push(...group);
  });
  return _uniqueStrings(merged);
};

const _uniqueStrings = (values: string[]) => {
  const seen = new Set<string>();
  const output: string[] = [];
  values.forEach((value) => {
    const trimmed = value.trim();
    if (!trimmed || seen.has(trimmed)) return;
    seen.add(trimmed);
    output.push(trimmed);
  });
  return output;
};

const closeSessionModal = () => {
  showSessionModal.value = false;
  sessionError.value = "";
};

const closeLiveModeConfirm = () => {
  showLiveModeConfirm.value = false;
  liveModeConfirmed.value = false;
  pendingExecutionMode.value = null;
  executionModeSelection.value = automationConfig.value.execution_mode;
};

const confirmLiveMode = () => {
  if (!pendingExecutionMode.value) {
    closeLiveModeConfirm();
    return;
  }
  updateConfigPersisted({ execution_mode: pendingExecutionMode.value });
  closeLiveModeConfirm();
};

const loadEquityHistory = async () => {
  equitySeries.value = [];
};

const loadDailyPnl = async () => {
  try {
    const response = await fetch("/api/v1/portfolio/daily-pnl");
    const data = await response.json();
    const payload = data?.data;
    if (payload) {
      dailyPnl.value = Number(payload.realized_pnl) || 0;
      dailyTradeCount.value = Number(payload.trade_count) || 0;
    }
  } catch {
    // Ignore load errors
  }
};

const startPositionPolling = () => {
  if (positionPollTimer) return;
  positionPollTimer = setInterval(() => {
    store.refreshPositions();
    loadPendingEntries();
    loadDailyPnl();
  }, 10000);
};

const stopPositionPolling = () => {
  if (positionPollTimer) {
    clearInterval(positionPollTimer);
    positionPollTimer = null;
  }
};

const startPromptConfigRefresh = () => {
  if (promptConfigRefreshTimer) return;
  promptConfigRefreshTimer = window.setInterval(() => {
    loadPromptConfigs();
  }, 60000);
};

const stopPromptConfigRefresh = () => {
  if (promptConfigRefreshTimer) {
    clearInterval(promptConfigRefreshTimer);
    promptConfigRefreshTimer = null;
  }
};

onMounted(async () => {
  window.addEventListener("click", closeExportMenu);
  await loadAutomationConfig();
  await loadTradeGuardConfig();
  await loadAutomationState();
  await riskStore.loadSummary();
  await Promise.all([loadProviders(), loadPromptConfigs()]);

  const provider = automationConfig.value.provider;
  if (provider) {
    await loadModels(provider);
  }

  await Promise.all([
    loadLogs(),
    loadPositions(),
    loadPendingEntries(),
    loadTrades(),
    loadEquityHistory(),
    loadTradingApiStatus(),
    loadCircuitBreaker(),
    loadMonitoredIntervals(),
    loadDailyPnl(),
  ]);

  startPositionPolling();
  startPromptRateTicker();
  startPromptConfigRefresh();
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
  window.removeEventListener("click", closeExportMenu);
  stopPositionPolling();
  stopPromptRateTicker();
  stopPromptConfigRefresh();
  if (positionGraceTimer) {
    clearTimeout(positionGraceTimer);
    positionGraceTimer = null;
  }
});
</script>
