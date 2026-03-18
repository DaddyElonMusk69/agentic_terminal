import { defineStore } from "pinia";
import type {
  AgentContext,
  ContextBuilderConfig,
  ContextBuilderDraft,
  ContextPromptResponse,
  PromptTemplatePayload,
} from "@/types/agent";
import { readMarketCache } from "@/services/settingsCache";

type ApiErrorDetail = {
  message?: string;
  code?: string;
  details?: Record<string, unknown>;
};

type ApiEnvelope<T> = {
  data?: T;
  error?: ApiErrorDetail;
  meta?: { request_id?: string };
};

const DEFAULT_CONTEXT_INTRO = `You are the Senior Risk Manager at a high-frequency crypto fund. Your job is to review signals from the Quantitative Engine and issue an execution mandate.

Context is King: If BTC is crashing, do not approve a Long on an Altcoin, even if the signal is good.

Specifics: Give exact numbers for Position Size ($), Entry, and Stop Loss.

Make sure to always have the goal in mind when analyzing the signals, especially when there are conflicting signals for the same asset on different intervals.`;

const DEFAULT_CONTEXT_REQUIREMENTS = `Return a strictly structured Markdown response. Do not use conversational filler (e.g., "Here is my analysis..."). Start directly with the bullet points.

Structure Template:

- Market State:

[Summary of Position]: ""

[Trend Context]: "1H/4H structure is [Up/Down] (Slope: +X%) etc.."

- Critical Divergence:

- Risk & Execution:

Verdict: [HOLD / REDUCE / CLOSE / OPEN NEW].

Action Plan: ""

Reasoning: ""

- New Opportunities:

"Scanning [Watchlist Assets]... [Asset] shows [Signal Type] (Score: X). [Meets/Fails] criteria because [Reason]."

Style Rules:

Be Brutally Concise: Use professional trading terminology. No fluff.

Data First: Back every claim with a number from the JSON packet (e.g., "OI dropped -1.5%", not "OI dropped a lot").`;

const DEFAULT_VEGAS_INTERVALS = ["30m", "1h", "2h", "4h", "8h", "12h"];

const buildDefaultIntervalConfig = () => {
  const cached = readMarketCache();
  const cachedIntervals = Array.isArray(cached?.intervals)
    ? cached.intervals.filter((item) => typeof item === "string" && item.trim())
    : [];
  const intervals = Array.from(new Set([...DEFAULT_VEGAS_INTERVALS, ...cachedIntervals]));
  const output: Record<string, number> = {};
  intervals.forEach((interval) => {
    output[interval] = 50;
  });
  return output;
};

const DEFAULT_VEGAS_INTERVAL_CONFIGS = buildDefaultIntervalConfig();

const DEFAULT_DATA_SELECTIONS = [
  "portfolio_overview",
  "trade_mandate",
  "account_state",
  "recent_completed_trades",
  "chart_snapshots",
  "open_positions",
  "quantitative_signals",
  "what_not_to_do_list",
  "llm_considerations",
];

const QUANT_DEFAULT_FIELDS = [
  "price_current",
  "oi_current",
  "cvd_current",
  "cvd_deltas",
  "price_slope",
  "price_slope_z",
  "oi_slope",
  "oi_slope_z",
  "cvd_slope",
  "cvd_slope_z",
  "funding_rate",
  "order_book",
  "vwap",
  "atr",
  "netflow",
  "anomalies",
];

const QUANT_FIELD_MAP: Record<string, string[]> = {
  ticker: ["symbol"],
  interval: ["timeframe"],
  timestamp: ["timestamp"],
  price_current: ["price_current"],
  price_slope: ["price_slope"],
  price_slope_z: ["price_slope_z"],
  oi_current: ["oi_current"],
  oi_slope: ["oi_slope"],
  oi_slope_z: ["oi_slope_z"],
  cvd_current: ["cvd_current"],
  cvd_slope: ["cvd_slope"],
  cvd_slope_z: ["cvd_slope_z"],
  cvd_delta: ["cvd_deltas"],
  net_depth_usd: ["order_book"],
  imbalance_pct: ["order_book"],
  obi_ratio: ["order_book"],
  vwap: ["vwap"],
  vwap_distance: ["vwap"],
  atr: ["atr"],
  atr_slope_pct: ["atr"],
  atr_z_score: ["atr"],
  funding_rate: ["funding_rate"],
  funding_mark_price: ["funding_rate"],
  total_netflow: ["netflow"],
  institution_netflow: ["netflow"],
  retail_netflow: ["netflow"],
  flow_regime: ["netflow"],
  dominant_flow: ["netflow"],
  anomalies: ["anomalies"],
};

const VEGAS_EMA_COLOR_MAP: Record<number, string> = {
  36: "#FFFFFF",
  44: "#FFFFFF",
  144: "#FFD54F",
  169: "#FFD54F",
  576: "#42A5F5",
  676: "#42A5F5",
};
const DEFAULT_EMA_COLOR = "#FFFFFF";

const buildVegasEmaConfig = (draft: ContextBuilderDraft) => {
  const lengths: number[] = [];
  if (draft.vegas_show_fast_tunnel) lengths.push(36, 44);
  if (draft.vegas_show_medium_tunnel) lengths.push(144, 169);
  if (draft.vegas_show_slow_tunnel) lengths.push(576, 676);
  const colors = lengths.map((length) => VEGAS_EMA_COLOR_MAP[length] || DEFAULT_EMA_COLOR);
  return { lengths, colors };
};

const buildVegasIntervalConfigs = (value: unknown): Record<string, number> => {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return { ...DEFAULT_VEGAS_INTERVAL_CONFIGS };
  }
  const parsed: Record<string, number> = {};
  for (const [interval, raw] of Object.entries(value as Record<string, unknown>)) {
    const numeric = typeof raw === "number" ? raw : Number(raw);
    if (Number.isFinite(numeric)) {
      parsed[interval] = numeric;
    }
  }
  if (Object.keys(parsed).length === 0) {
    return { ...DEFAULT_VEGAS_INTERVAL_CONFIGS };
  }
  return { ...DEFAULT_VEGAS_INTERVAL_CONFIGS, ...parsed };
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

const toRecord = (value: unknown): Record<string, unknown> => {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return {};
  }
  return value as Record<string, unknown>;
};

const readNumber = (value: unknown, fallback: number): number => {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
};

const readBoolean = (value: unknown, fallback: boolean): boolean => {
  return typeof value === "boolean" ? value : fallback;
};

const readStringArray = (value: unknown, fallback: string[]): string[] => {
  if (!Array.isArray(value)) return fallback;
  const items = value.filter((item) => typeof item === "string") as string[];
  return items.length ? items : fallback;
};

const readFieldSelections = (value: unknown): Record<string, string[]> => {
  const record = toRecord(value);
  const output: Record<string, string[]> = {};
  Object.entries(record).forEach(([key, entry]) => {
    if (!Array.isArray(entry)) return;
    const values = entry.filter((item) => typeof item === "string") as string[];
    if (values.length) output[key] = values;
  });
  return output;
};

const buildOverlayDefaults = (draft: ContextBuilderDraft): string[] => {
  const overlays: string[] = [];
  const { lengths } = buildVegasEmaConfig(draft);
  if (lengths.length) overlays.push("ema");
  if (draft.vegas_show_bb) overlays.push("bb");
  if (draft.vegas_show_atr) overlays.push("atr");
  return overlays;
};

const buildQuantFieldsFromDraft = (draft: ContextBuilderDraft): string[] => {
  if (!draft.data_selections.includes("quantitative_signals")) {
    return [];
  }
  const selected = draft.field_selections["quantitative_signals"];
  if (!selected || selected.length === 0) {
    return [...QUANT_DEFAULT_FIELDS];
  }
  const output = new Set<string>();
  selected.forEach((field) => {
    const mapped = QUANT_FIELD_MAP[field];
    if (!mapped) return;
    mapped.forEach((item) => output.add(item));
  });
  return output.size ? Array.from(output) : [...QUANT_DEFAULT_FIELDS];
};

const mapTemplateToConfig = (template: PromptTemplatePayload): ContextBuilderConfig => {
  const defaults = toRecord(template.chart_defaults);
  return {
    id: template.id,
    name: template.name,
    intro: template.intro,
    requirements: template.response_format,
    data_selections: readStringArray(defaults.data_selections, [...DEFAULT_DATA_SELECTIONS]),
    field_selections: readFieldSelections(defaults.field_selections),
    vegas_interval_configs: buildVegasIntervalConfigs(defaults.vegas_interval_configs),
    vegas_show_fast_tunnel: readBoolean(defaults.vegas_show_fast_tunnel, true),
    vegas_show_medium_tunnel: readBoolean(defaults.vegas_show_medium_tunnel, true),
    vegas_show_slow_tunnel: readBoolean(defaults.vegas_show_slow_tunnel, true),
    vegas_show_bb: readBoolean(defaults.vegas_show_bb, true),
    vegas_show_atr: readBoolean(defaults.vegas_show_atr, true),
    vegas_bb_length: readNumber(defaults.vegas_bb_length, 20),
    vegas_bb_std: readNumber(defaults.vegas_bb_std, 2),
    is_default: template.is_default,
    created_at: template.created_at ?? null,
    updated_at: template.updated_at ?? null,
  };
};

const buildTemplatePayload = (draft: ContextBuilderDraft, name?: string) => {
  const vegasEmaConfig = buildVegasEmaConfig(draft);
  return {
    name,
    intro: draft.intro,
    response_format: draft.requirements,
    quant_fields: buildQuantFieldsFromDraft(draft),
    chart_defaults: {
      vegas_interval_configs: draft.vegas_interval_configs,
      vegas_show_fast_tunnel: draft.vegas_show_fast_tunnel,
      vegas_show_medium_tunnel: draft.vegas_show_medium_tunnel,
      vegas_show_slow_tunnel: draft.vegas_show_slow_tunnel,
      vegas_show_bb: draft.vegas_show_bb,
      vegas_show_atr: draft.vegas_show_atr,
      vegas_bb_length: draft.vegas_bb_length,
      vegas_bb_std: draft.vegas_bb_std,
      ema_lengths: vegasEmaConfig.lengths,
      ema_colors: vegasEmaConfig.colors,
      data_selections: draft.data_selections,
      field_selections: draft.field_selections,
      overlays: buildOverlayDefaults(draft),
    },
  };
};

const buildDraftFromConfig = (config?: Partial<ContextBuilderConfig>): ContextBuilderDraft => ({
  intro: config?.intro || DEFAULT_CONTEXT_INTRO,
  requirements: config?.requirements || DEFAULT_CONTEXT_REQUIREMENTS,
  data_selections: Array.isArray(config?.data_selections)
    ? config?.data_selections
    : [...DEFAULT_DATA_SELECTIONS],
  field_selections:
    config?.field_selections && typeof config.field_selections === "object" && !Array.isArray(config.field_selections)
      ? config.field_selections
      : {},
  vegas_interval_configs: buildVegasIntervalConfigs(config?.vegas_interval_configs),
  vegas_show_fast_tunnel:
    typeof config?.vegas_show_fast_tunnel === "boolean" ? config.vegas_show_fast_tunnel : true,
  vegas_show_medium_tunnel:
    typeof config?.vegas_show_medium_tunnel === "boolean" ? config.vegas_show_medium_tunnel : true,
  vegas_show_slow_tunnel:
    typeof config?.vegas_show_slow_tunnel === "boolean" ? config.vegas_show_slow_tunnel : true,
  vegas_show_bb: typeof config?.vegas_show_bb === "boolean" ? config.vegas_show_bb : true,
  vegas_show_atr: typeof config?.vegas_show_atr === "boolean" ? config.vegas_show_atr : true,
  vegas_bb_length: typeof config?.vegas_bb_length === "number" ? config.vegas_bb_length : 20,
  vegas_bb_std: typeof config?.vegas_bb_std === "number" ? config.vegas_bb_std : 2,
});

const loadStoredConfigId = () => {
  try {
    const raw = localStorage.getItem("ai_context_builder_last_config_id");
    if (!raw) return null;
    const id = Number(raw);
    return Number.isFinite(id) ? id : null;
  } catch {
    return null;
  }
};

const storeConfigId = (id: number) => {
  try {
    localStorage.setItem("ai_context_builder_last_config_id", String(id));
  } catch {
    // Ignore storage failures
  }
};

export const useAgentStore = defineStore("agent", {
  state: () => ({
    contextConfigs: [] as ContextBuilderConfig[],
    activeConfigId: null as number | null,
    draft: buildDraftFromConfig(),
    preview: "",
    previewTimestamp: "" as string,
    isLoadingConfigs: false,
    isSavingConfig: false,
    isDeletingConfig: false,
    isBuildingPrompt: false,
    contextError: "" as string,
    contextErrorCode: "" as string,
    contextErrorDetails: null as Record<string, unknown> | null,
    history: [] as AgentContext[],
  }),
  getters: {
    activeConfig(state) {
      return state.contextConfigs.find((config) => config.id === state.activeConfigId) || null;
    },
  },
  actions: {
    setActiveConfig(configId: number | null) {
      this.activeConfigId = configId;
      const config = this.contextConfigs.find((item) => item.id === configId);
      this.draft = buildDraftFromConfig(config || undefined);
      if (configId !== null) {
        storeConfigId(configId);
      }
      this.preview = "";
      this.previewTimestamp = "";
    },
    async loadContextConfigs(preferredId?: number) {
      this.isLoadingConfigs = true;
      this.contextError = "";
      this.contextErrorCode = "";
      this.contextErrorDetails = null;
      try {
        const response = await fetch("/api/v1/agent/templates");
        const data = await parseResponse<PromptTemplatePayload[]>(response);
        if (!response.ok) {
          throw new Error(data.error?.message || "Failed to load templates.");
        }
        const templates = Array.isArray(data.data) ? data.data : [];
        this.contextConfigs = templates.map((template) => mapTemplateToConfig(template));
        const storedId = loadStoredConfigId();
        const nextId = preferredId ?? storedId;
        const hasNext = nextId !== null && this.contextConfigs.some((config) => config.id === nextId);
        if (hasNext) {
          this.setActiveConfig(nextId as number);
        } else if (this.contextConfigs.length > 0) {
          this.setActiveConfig(this.contextConfigs[0].id);
        } else {
          this.activeConfigId = null;
          this.draft = buildDraftFromConfig();
        }
      } catch (error) {
        this.contextError = error instanceof Error ? error.message : "Unable to load context configs.";
      } finally {
        this.isLoadingConfigs = false;
      }
    },
    async saveActiveConfig() {
      if (this.activeConfigId === null) return;
      this.isSavingConfig = true;
      this.contextError = "";
      this.contextErrorCode = "";
      this.contextErrorDetails = null;
      try {
        const payload = buildTemplatePayload(this.draft);
        const response = await fetch(`/api/v1/agent/templates/${this.activeConfigId}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await parseResponse<PromptTemplatePayload>(response);
        if (!response.ok || !data.data) {
          throw new Error(data.error?.message || "Save failed.");
        }
        const nextConfig = mapTemplateToConfig(data.data);
        this.contextConfigs = this.contextConfigs.map((config) =>
          config.id === nextConfig.id ? nextConfig : config,
        );
        this.draft = buildDraftFromConfig(nextConfig);
      } catch (error) {
        this.contextError = error instanceof Error ? error.message : "Unable to save configuration.";
      } finally {
        this.isSavingConfig = false;
      }
    },
    async createConfig(name: string) {
      if (!name.trim()) return;
      this.isSavingConfig = true;
      this.contextError = "";
      this.contextErrorCode = "";
      this.contextErrorDetails = null;
      try {
        const payload = {
          ...buildTemplatePayload(this.draft, name.trim()),
          ...(this.contextConfigs.length === 0 ? { is_default: true } : {}),
        };
        const response = await fetch("/api/v1/agent/templates", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await parseResponse<PromptTemplatePayload>(response);
        if (!response.ok || !data.data) {
          throw new Error(data.error?.message || "Create failed.");
        }
        await this.loadContextConfigs(data.data.id);
      } catch (error) {
        this.contextError = error instanceof Error ? error.message : "Unable to create configuration.";
      } finally {
        this.isSavingConfig = false;
      }
    },
    async deleteActiveConfig() {
      const active = this.contextConfigs.find((config) => config.id === this.activeConfigId);
      if (!active || active.is_default) return;
      this.isDeletingConfig = true;
      this.contextError = "";
      this.contextErrorCode = "";
      this.contextErrorDetails = null;
      try {
        const response = await fetch(`/api/v1/agent/templates/${active.id}`, {
          method: "DELETE",
        });
        const data = await parseResponse<{ deleted: boolean }>(response);
        if (!response.ok || !data.data?.deleted) {
          throw new Error(data.error?.message || "Delete failed.");
        }
        await this.loadContextConfigs();
      } catch (error) {
        this.contextError = error instanceof Error ? error.message : "Unable to delete configuration.";
      } finally {
        this.isDeletingConfig = false;
      }
    },
    async buildContextPrompt(ticker: string) {
      if (this.activeConfigId === null) {
        return { ok: false, errorCode: "template_required" };
      }
      this.isBuildingPrompt = true;
      this.contextError = "";
      this.contextErrorCode = "";
      this.contextErrorDetails = null;
      try {
        const payload = {
          ticker: ticker.trim(),
        };
        const response = await fetch(`/api/v1/agent/templates/${this.activeConfigId}/preview`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await parseResponse<ContextPromptResponse>(response);
        if (!response.ok || !data.data) {
          const errorCode = data.error?.code || "prompt_build_failed";
          const errorDetails = data.error?.details || null;
          this.contextError = data.error?.message || "Prompt build failed.";
          this.contextErrorCode = errorCode;
          this.contextErrorDetails = errorDetails;
          return { ok: false, errorCode, errorDetails };
        }
        this.preview = data.data.prompt_text || "";
        this.previewTimestamp = data.data.created_at || "";
        return { ok: true };
      } catch (error) {
        this.contextError = error instanceof Error ? error.message : "Unable to build context prompt.";
        this.contextErrorCode = "prompt_build_failed";
        this.contextErrorDetails = null;
        return { ok: false, errorCode: this.contextErrorCode };
      } finally {
        this.isBuildingPrompt = false;
      }
    },
    setHistory(items: AgentContext[]) {
      this.history = items;
    },
  },
});
