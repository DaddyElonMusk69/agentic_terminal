<template>
  <div class="flex min-h-0 flex-1 flex-col gap-4">
    <BaseCard>
      <div class="flex items-center justify-between">
        <div>
          <div class="text-xs uppercase tracking-wide text-muted">Risk Management</div>
          <p class="mt-1 text-xs text-muted">Goal tracking, exposure, and daily targets.</p>
        </div>
        <BaseBadge v-if="accountLabel">{{ accountLabel }}</BaseBadge>
      </div>
      <div v-if="error" class="mt-3 text-xs text-negative">
        {{ error }}
      </div>
      <div v-else-if="isLoading" class="mt-3 text-xs text-muted">Loading...</div>
      <div v-else class="mt-4 grid gap-3 md:grid-cols-3">
        <div class="rounded-md border border-border bg-panel/50 p-3">
          <div class="text-[11px] uppercase tracking-wide text-muted">Account Value</div>
          <div class="mt-2 text-lg font-semibold text-text">{{ formatCurrency(accountValue) }}</div>
        </div>
        <div class="rounded-md border border-border bg-panel/50 p-3">
          <div class="text-[11px] uppercase tracking-wide text-muted">Goal Gap</div>
          <div class="mt-2 text-lg font-semibold text-text">{{ formatCurrency(progressGapUsd) }}</div>
        </div>
        <div class="rounded-md border border-border bg-panel/50 p-3">
          <div class="text-[11px] uppercase tracking-wide text-muted">Days Left</div>
          <div class="mt-2 text-lg font-semibold text-text">
            {{ daysLeftLabel }}
          </div>
        </div>
      </div>
    </BaseCard>

    <BaseCard>
      <div class="flex items-center justify-between">
        <div>
          <div class="text-xs uppercase tracking-wide text-muted">Final Goal</div>
          <p class="mt-1 text-xs text-muted">Set the portfolio target you want to reach.</p>
        </div>
        <div class="flex items-center gap-2">
          <button
            class="rounded-md border border-border px-3 py-1 text-xs"
            :class="currency === 'USD' ? 'bg-accent text-base' : 'bg-panel text-muted'"
            type="button"
            @click="setCurrency('USD')"
          >
            USD
          </button>
          <button
            class="rounded-md border border-border px-3 py-1 text-xs"
            :class="currency === 'CNY' ? 'bg-accent text-base' : 'bg-panel text-muted'"
            type="button"
            @click="setCurrency('CNY')"
          >
            CNY
          </button>
        </div>
      </div>

      <div class="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto]">
        <label class="space-y-2 text-xs text-muted">
          Target Value
          <input
            class="w-full rounded-md border border-border bg-panel px-3 py-2 text-sm text-text"
            :value="goalInput"
            type="number"
            min="0"
            step="0.01"
            @input="handleGoalInput"
          />
        </label>
        <div class="rounded-md border border-border bg-panel/50 p-3">
          <div class="text-[11px] uppercase tracking-wide text-muted">In {{ currencyLabel }}</div>
          <div class="mt-2 text-sm text-text">
            {{ formattedGoalAlt }}
          </div>
        </div>
      </div>

      <div class="mt-4">
        <div class="flex items-center justify-between text-[11px] text-muted">
          <span>Progress</span>
          <span>{{ progressPctLabel }}</span>
        </div>
        <div class="mt-2 h-2 w-full rounded-full bg-border/60">
          <div
            class="h-2 rounded-full bg-accent"
            :style="{ width: progressWidth }"
          ></div>
        </div>
      </div>
    </BaseCard>

    <BaseCard>
      <div class="text-xs uppercase tracking-wide text-muted">Account Exposure</div>
      <p class="mt-1 text-xs text-muted">Share of account value allocated to trading.</p>
      <div class="mt-4 space-y-3">
        <div class="flex items-center justify-between">
          <span class="text-sm text-text">{{ exposurePct.toFixed(0) }}%</span>
          <span class="text-sm text-text">{{ formatCurrency(exposureUsd) }}</span>
        </div>
        <input
          v-model.number="exposurePct"
          class="w-full"
          type="range"
          min="1"
          max="100"
          step="1"
        />
      </div>
    </BaseCard>

    <BaseCard>
      <div class="text-xs uppercase tracking-wide text-muted">Goal Deadline</div>
      <p class="mt-1 text-xs text-muted">Pick a date to target the final goal.</p>
      <div class="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <label class="space-y-2 text-xs text-muted">
          Achieve goal by
          <input
            v-model="goalDeadline"
            class="w-full rounded-md border border-border bg-panel px-3 py-2 text-sm text-text"
            type="date"
          />
        </label>
        <div class="rounded-md border border-border bg-panel/50 p-3">
          <div class="text-[11px] uppercase tracking-wide text-muted">Daily Target</div>
          <div class="mt-2 text-sm text-text">
            {{ dailyTargetLabel }}
          </div>
          <div class="mt-1 text-[11px] text-muted">
            {{ dailyTargetPctLabel }}
          </div>
        </div>
      </div>
    </BaseCard>

    <div class="flex flex-wrap items-center gap-2">
      <button
        class="rounded-md border border-border bg-accent px-3 py-2 text-xs font-medium text-base"
        type="button"
        :disabled="isSaving"
        @click="saveConfig"
      >
        {{ isSaving ? "Saving..." : "Save" }}
      </button>
      <button
        class="rounded-md border border-border bg-panel px-3 py-2 text-xs text-muted hover:text-text"
        type="button"
        :disabled="isLoading"
        @click="loadSummary(true)"
      >
        Refresh
      </button>
      <span v-if="saveMessage" class="text-xs text-muted">{{ saveMessage }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import BaseBadge from "@/components/BaseBadge.vue";
import BaseCard from "@/components/BaseCard.vue";
import { useExchangeStore } from "@/stores/exchangeStore";
import { useRiskManagementStore } from "@/stores/riskManagementStore";

const exchangeStore = useExchangeStore();
const riskStore = useRiskManagementStore();

type RiskSummary = {
  config: {
    final_goal_usd: number;
    exposure_pct: number;
    goal_deadline: string | null;
  };
  account_value: number | null;
  goal_cny: number;
  fx_rate_cny: number;
  exposure_usd: number | null;
  progress_pct: number | null;
  progress_gap_usd: number | null;
  days_left: number | null;
  daily_target_pct: number | null;
  daily_target_usd: number | null;
};

const saveMessage = ref("");
const summary = computed(() => riskStore.summary);
const isLoading = computed(() => riskStore.isLoading);
const isSaving = computed(() => riskStore.isSaving);
const error = computed(() => riskStore.error);

const currency = ref<"USD" | "CNY">("USD");
const goalInput = ref("0");
const exposurePct = ref(20);
const goalDeadline = ref("");

const accountValue = computed(() => summary.value?.account_value ?? null);
const fxRate = computed(() => summary.value?.fx_rate_cny ?? 7.2);
const goalUsd = computed(() => {
  const numeric = parseNumber(goalInput.value);
  if (!Number.isFinite(numeric)) return 0;
  return currency.value === "CNY" ? numeric / fxRate.value : numeric;
});

const progressGapUsd = computed(() => {
  if (accountValue.value === null || goalUsd.value <= 0) return null;
  return Math.max(goalUsd.value - accountValue.value, 0);
});

const progressPct = computed(() => {
  if (accountValue.value === null || goalUsd.value <= 0) return null;
  return (accountValue.value / goalUsd.value) * 100;
});

const exposureUsd = computed(() => {
  if (accountValue.value === null) return null;
  return accountValue.value * (exposurePct.value / 100);
});

const daysLeft = computed(() => {
  if (!goalDeadline.value) return null;
  const deadline = new Date(goalDeadline.value);
  if (Number.isNaN(deadline.getTime())) return null;
  const today = new Date();
  const start = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const end = new Date(deadline.getFullYear(), deadline.getMonth(), deadline.getDate());
  const diff = Math.ceil((end.getTime() - start.getTime()) / (24 * 60 * 60 * 1000));
  return Math.max(diff, 0);
});

const daysLeftLabel = computed(() => {
  if (daysLeft.value === null) return "--";
  return `${daysLeft.value} days`;
});

const progressWidth = computed(() => {
  const value = progressPct.value ?? 0;
  const clamped = Math.max(0, Math.min(100, value));
  return `${clamped.toFixed(1)}%`;
});

const progressPctLabel = computed(() => {
  if (progressPct.value === null || progressPct.value === undefined) return "--";
  return `${progressPct.value.toFixed(2)}%`;
});

const dailyTarget = computed(() => {
  if (accountValue.value === null || goalUsd.value <= 0 || !daysLeft.value || daysLeft.value <= 0) {
    return null;
  }
  if (goalUsd.value <= accountValue.value) {
    return { usd: 0, pct: 0 };
  }
  const rate = Math.pow(goalUsd.value / accountValue.value, 1 / daysLeft.value) - 1;
  return { usd: accountValue.value * rate, pct: rate * 100 };
});

const dailyTargetLabel = computed(() => {
  if (!dailyTarget.value) return "--";
  return formatCurrency(dailyTarget.value.usd);
});

const dailyTargetPctLabel = computed(() => {
  if (!dailyTarget.value) return "Set a deadline to calculate.";
  return `${dailyTarget.value.pct.toFixed(2)}% daily`;
});

const currencyLabel = computed(() => (currency.value === "USD" ? "CNY" : "USD"));

const formattedGoalAlt = computed(() => {
  const goalUsd = parseNumber(goalInput.value);
  if (!Number.isFinite(goalUsd)) return "--";
  if (currency.value === "USD") {
    return formatCurrency(goalUsd * fxRate.value, "CNY");
  }
  return formatCurrency(goalUsd / fxRate.value, "USD");
});

const accountLabel = computed(() => {
  const account = exchangeStore.activeAccount;
  if (!account) return "";
  return `${account.exchange.toUpperCase()} · ${account.name}`;
});

const setCurrency = (value: "USD" | "CNY") => {
  currency.value = value;
  syncGoalInput();
};

const parseNumber = (value: string) => {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : NaN;
};

const syncGoalInput = () => {
  const goalUsd = summary.value?.config.final_goal_usd ?? 0;
  const display = currency.value === "CNY" ? goalUsd * fxRate.value : goalUsd;
  goalInput.value = Number.isFinite(display) ? display.toFixed(2) : "0";
};

const handleGoalInput = (event: Event) => {
  const value = (event.target as HTMLInputElement).value;
  goalInput.value = value;
};

const applySummary = () => {
  if (!summary.value) return;
  exposurePct.value = summary.value.config.exposure_pct;
  goalDeadline.value = summary.value.config.goal_deadline || "";
  syncGoalInput();
};

const loadSummary = async (force = false) => {
  await riskStore.loadSummary(force);
  applySummary();
};

const saveConfig = async () => {
  if (!summary.value) return;
  saveMessage.value = "";
  try {
    const payload = {
      final_goal_usd: goalUsd.value || 0,
      exposure_pct: exposurePct.value,
      goal_deadline: goalDeadline.value || null,
    };
    const ok = await riskStore.saveConfig(payload);
    if (ok) {
      saveMessage.value = "Saved.";
      applySummary();
    }
  } catch {
    // errors are surfaced via store.error
  }
};

const formatCurrency = (value: number | null, currencyCode: "USD" | "CNY" = "USD") => {
  if (value === null || value === undefined || Number.isNaN(value)) return "--";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currencyCode,
    maximumFractionDigits: 2,
  }).format(value);
};

onMounted(() => {
  void exchangeStore.loadExchanges();
  loadSummary();
});
</script>
