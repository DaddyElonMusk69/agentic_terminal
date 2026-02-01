import { defineStore } from "pinia";

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

type ApiEnvelope<T> = {
  data?: T;
  error?: { message?: string };
};

const CACHE_TTL_MS = 60_000;

const parseResponse = async <T>(response: Response): Promise<ApiEnvelope<T>> => {
  try {
    const data = (await response.json()) as ApiEnvelope<T>;
    if (data && typeof data === "object") {
      return data;
    }
  } catch {
    // Ignore parsing errors.
  }
  return {};
};

export const useRiskManagementStore = defineStore("riskManagement", {
  state: () => ({
    summary: null as RiskSummary | null,
    lastLoadedAt: 0,
    isLoading: false,
    isSaving: false,
    error: "" as string,
  }),
  actions: {
    async loadSummary(force = false) {
      if (this.isLoading) return;
      if (!force && this.summary && Date.now() - this.lastLoadedAt < CACHE_TTL_MS) {
        return;
      }
      this.isLoading = true;
      this.error = "";
      try {
        const response = await fetch("/api/v1/risk-management/summary");
        const data = await parseResponse<RiskSummary>(response);
        if (!response.ok || !data.data) {
          throw new Error(data.error?.message || "Failed to load risk summary.");
        }
        this.summary = data.data;
        this.lastLoadedAt = Date.now();
      } catch (err) {
        this.error = err instanceof Error ? err.message : "Failed to load risk summary.";
      } finally {
        this.isLoading = false;
      }
    },
    async saveConfig(payload: {
      final_goal_usd: number;
      exposure_pct: number;
      goal_deadline: string | null;
    }) {
      if (this.isSaving) return false;
      this.isSaving = true;
      this.error = "";
      try {
        const response = await fetch("/api/v1/risk-management/config", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await parseResponse<{ final_goal_usd: number }>(response);
        if (!response.ok || !data.data) {
          throw new Error(data.error?.message || "Failed to save risk config.");
        }
        await this.loadSummary(true);
        return true;
      } catch (err) {
        this.error = err instanceof Error ? err.message : "Failed to save risk config.";
        return false;
      } finally {
        this.isSaving = false;
      }
    },
  },
});
