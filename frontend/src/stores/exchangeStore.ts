import { defineStore } from "pinia";
import type { ExchangeAccount, ExchangeCreatePayload } from "@/types/exchange";

type ApiErrorDetail = {
  message?: string;
  code?: string;
  details?: Record<string, unknown>;
};

type ApiMeta = {
  request_id?: string;
};

type ApiEnvelope<T> = {
  data?: T;
  error?: ApiErrorDetail;
  meta?: ApiMeta;
};

export type ExchangeActionResult = {
  success: boolean;
  message?: string;
  error?: string;
  exchange?: ExchangeAccount | null;
};

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

const resolveError = (data: ApiEnvelope<unknown>, fallback: string) => {
  if (data.error?.message) return data.error.message;
  return fallback;
};

const coerceAccounts = (payload: unknown): ExchangeAccount[] => {
  if (!Array.isArray(payload)) return [];
  return payload.filter(Boolean) as ExchangeAccount[];
};

export const useExchangeStore = defineStore("exchange", {
  state: () => ({
    activeExchangeId: null as string | null,
    accounts: [] as ExchangeAccount[],
    isLoading: false,
    isSaving: false,
    error: "" as string,
    lastLoadedAt: 0,
  }),
  getters: {
    activeAccount: (state) =>
      state.accounts.find((account) => account.id === state.activeExchangeId) || null,
  },
  actions: {
    setAccounts(accounts: ExchangeAccount[]) {
      this.accounts = accounts;
      const active = accounts.find((account) => account.is_active);
      this.activeExchangeId = active ? active.id : null;
    },
    async loadExchanges(force = false): Promise<ExchangeActionResult> {
      if (this.isLoading) {
        return { success: false, error: "Exchange data is already loading." };
      }
      if (!force && this.lastLoadedAt && Date.now() - this.lastLoadedAt < 5000) {
        return { success: true };
      }
      this.isLoading = true;
      this.error = "";
      try {
        const response = await fetch("/api/v1/portfolio/exchanges");
        const data = await parseResponse<ExchangeAccount[]>(response);
        if (!response.ok) {
          const message = resolveError(data, "Failed to load exchanges.");
          this.error = message;
          return { success: false, error: message };
        }
        const accounts = coerceAccounts(data.data);
        this.setAccounts(accounts);
        this.lastLoadedAt = Date.now();
        return { success: true };
      } catch (error) {
        const message = error instanceof Error ? error.message : "Failed to load exchanges.";
        this.error = message;
        return { success: false, error: message };
      } finally {
        this.isLoading = false;
      }
    },
    async addExchange(payload: ExchangeCreatePayload): Promise<ExchangeActionResult> {
      if (this.isSaving) {
        return { success: false, error: "Another exchange action is in progress." };
      }
      this.isSaving = true;
      this.error = "";
      try {
        const response = await fetch("/api/v1/portfolio/exchanges", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await parseResponse<ExchangeAccount>(response);
        if (!response.ok) {
          const message = resolveError(data, "Failed to add exchange.");
          this.error = message;
          return { success: false, error: message, exchange: data.data ?? null };
        }
        if (data.data?.id) {
          this.activeExchangeId = data.data.id;
        } else {
          this.activeExchangeId = null;
        }
        await this.loadExchanges(true);
        return { success: true, exchange: data.data ?? null };
      } catch (error) {
        const message = error instanceof Error ? error.message : "Failed to add exchange.";
        this.error = message;
        return { success: false, error: message };
      } finally {
        this.isSaving = false;
      }
    },
    async setActiveExchange(id: string): Promise<ExchangeActionResult> {
      if (this.isSaving) {
        return { success: false, error: "Another exchange action is in progress." };
      }
      this.isSaving = true;
      this.error = "";
      try {
        const response = await fetch(`/api/v1/portfolio/exchanges/${id}/activate`, {
          method: "POST",
        });
        const data = await parseResponse<ExchangeAccount>(response);
        if (!response.ok) {
          const message = resolveError(data, "Failed to activate exchange.");
          this.error = message;
          return { success: false, error: message, exchange: data.data ?? null };
        }
        await this.loadExchanges(true);
        return { success: true, exchange: data.data ?? null };
      } catch (error) {
        const message = error instanceof Error ? error.message : "Failed to activate exchange.";
        this.error = message;
        return { success: false, error: message };
      } finally {
        this.isSaving = false;
      }
    },
    async deactivateExchange(): Promise<ExchangeActionResult> {
      if (this.isSaving) {
        return { success: false, error: "Another exchange action is in progress." };
      }
      this.isSaving = true;
      this.error = "";
      try {
        const response = await fetch("/api/v1/portfolio/exchanges/deactivate", {
          method: "POST",
        });
        const data = await parseResponse<{ deactivated: boolean }>(response);
        if (!response.ok) {
          const message = resolveError(data, "Failed to deactivate exchange.");
          this.error = message;
          return { success: false, error: message };
        }
        this.activeExchangeId = null;
        await this.loadExchanges(true);
        return { success: true };
      } catch (error) {
        const message = error instanceof Error ? error.message : "Failed to deactivate exchange.";
        this.error = message;
        return { success: false, error: message };
      } finally {
        this.isSaving = false;
      }
    },
    async validateExchange(id: string): Promise<ExchangeActionResult> {
      if (this.isSaving) {
        return { success: false, error: "Another exchange action is in progress." };
      }
      this.isSaving = true;
      this.error = "";
      try {
        const response = await fetch(`/api/v1/portfolio/exchanges/${id}/validate`, {
          method: "POST",
        });
        const data = await parseResponse<ExchangeAccount>(response);
        if (!response.ok) {
          const message = resolveError(data, "Validation failed.");
          await this.loadExchanges(true);
          this.error = message;
          return { success: false, error: message, exchange: data.data ?? null };
        }
        await this.loadExchanges(true);
        return { success: true, exchange: data.data ?? null };
      } catch (error) {
        const message = error instanceof Error ? error.message : "Validation failed.";
        this.error = message;
        return { success: false, error: message };
      } finally {
        this.isSaving = false;
      }
    },
    async deleteExchange(id: string): Promise<ExchangeActionResult> {
      if (this.isSaving) {
        return { success: false, error: "Another exchange action is in progress." };
      }
      this.isSaving = true;
      this.error = "";
      try {
        const response = await fetch(`/api/v1/portfolio/exchanges/${id}`, { method: "DELETE" });
        const data = await parseResponse<{ deleted: boolean }>(response);
        if (!response.ok) {
          const message = resolveError(data, "Failed to delete exchange.");
          this.error = message;
          return { success: false, error: message };
        }
        if (this.activeExchangeId === id) {
          this.activeExchangeId = null;
        }
        await this.loadExchanges(true);
        return { success: true };
      } catch (error) {
        const message = error instanceof Error ? error.message : "Failed to delete exchange.";
        this.error = message;
        return { success: false, error: message };
      } finally {
        this.isSaving = false;
      }
    },
  },
});
