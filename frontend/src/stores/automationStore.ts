import { defineStore } from "pinia";
import type {
  AutomationLog,
  AutomationPosition,
  AutomationSession,
  AutomationStatePayload,
  AutomationTrade,
} from "@/types/automation";
import { createAutomationSocket } from "@/services/socketAutomation";

const socketClient = createAutomationSocket();
let socketExchangeId = "";

const MAX_LOG_ENTRIES = 200;
const AUTOMATION_TOPICS = ["automation.*", "trade.*", "scanner.*"];

type RealtimeEnvelope<T = unknown> = {
  v?: number;
  type?: string;
  topic?: string;
  payload?: T;
  ts?: string;
  request_id?: string;
  trace_id?: string;
};

type DisconnectReason = "stopped" | "purged";

const resolveLogType = (topic?: string) => {
  if (!topic) return "system";
  if (topic === "scanner.ema.state") return "state";
  if (topic.startsWith("scanner.")) return "scanner";
  if (topic.startsWith("automation.prompt")) return "prompt";
  if (topic.startsWith("automation.parser")) return "parser";
  if (topic.startsWith("automation.llm")) return "llm";
  if (topic.startsWith("automation.guard")) return "guard";
  if (topic.startsWith("automation.circuit")) return "circuit";
  if (topic.startsWith("trade.")) return "execution";
  if (topic.startsWith("automation.order")) return "execution";
  return "system";
};

const extractSymbol = (payload: Record<string, unknown>) => {
  const ticker = payload.ticker;
  if (typeof ticker === "string" && ticker) return ticker;
  const tickers = payload.tickers;
  if (Array.isArray(tickers) && tickers.length > 0) {
    const value = tickers[0];
    if (typeof value === "string" && value) return value;
  }
  const executionIdeas = payload.execution_ideas;
  if (Array.isArray(executionIdeas) && executionIdeas.length > 0) {
    const first = executionIdeas[0];
    if (first && typeof first === "object") {
      const symbol = (first as Record<string, unknown>).symbol;
      if (typeof symbol === "string" && symbol) return symbol;
    }
  }
  const idea = payload.execution_idea as Record<string, unknown> | undefined;
  if (idea && typeof idea.symbol === "string" && idea.symbol) return idea.symbol;
  const finalOrder = payload.final_order as Record<string, unknown> | undefined;
  if (finalOrder && typeof finalOrder.symbol === "string" && finalOrder.symbol) return finalOrder.symbol;
  const parseResult = payload.parse_result as Record<string, unknown> | undefined;
  if (parseResult) {
    const ideas = parseResult.ideas;
    if (Array.isArray(ideas) && ideas.length > 0) {
      const first = ideas[0];
      if (first && typeof first === "object") {
        const symbol = (first as Record<string, unknown>).symbol;
        if (typeof symbol === "string" && symbol) return symbol;
      }
    }
  }
  const result = payload.result as Record<string, unknown> | undefined;
  if (result && typeof result.symbol === "string" && result.symbol) return result.symbol;
  return null;
};

const normalizeActionLabel = (action?: string | null) => {
  if (!action) return null;
  return action
    .toString()
    .replace(/_/g, " ")
    .toLowerCase();
};

const formatNumber = (value: unknown, decimals = 2) => {
  if (typeof value !== "number" || Number.isNaN(value)) return null;
  return value % 1 === 0 ? value.toFixed(0) : value.toFixed(decimals);
};

const buildOrderSummary = (payload: Record<string, unknown>) => {
  const source =
    (payload.final_order as Record<string, unknown> | undefined) ||
    (payload.execution_idea as Record<string, unknown> | undefined) ||
    {};
  const action = normalizeActionLabel(source.action as string | undefined);
  const symbol = (source.symbol as string | undefined) || extractSymbol(payload);
  const size = formatNumber(source.position_size_usd ?? source.size_usd);
  const leverage = formatNumber(source.leverage, 0);
  const tp = formatNumber(source.take_profit ?? source.new_take_profit);
  const sl = formatNumber(source.stop_loss ?? source.new_stop_loss);
  const margin =
    size && leverage && Number(leverage) > 0
      ? formatNumber(Number(size) / Number(leverage))
      : null;

  const parts = [
    action ? `side: ${action}` : null,
    symbol ? `ticker ${symbol}` : null,
    tp ? `tp:${tp}` : null,
    sl ? `sl:${sl}` : null,
    size ? `size:${size}` : null,
    margin ? `margin:${margin}` : null,
    leverage ? `leverage:${leverage}x` : null,
  ]
    .filter(Boolean)
    .join(", ");
  return parts || null;
};

const buildGuardDetails = (payload: Record<string, unknown>) => {
  const guard = payload.guard as Record<string, unknown> | undefined;
  if (!guard) return null;
  const modifications = Array.isArray(guard.modifications) ? guard.modifications : [];
  const failedRules = Array.isArray(guard.rule_results)
    ? guard.rule_results.filter((item: Record<string, unknown>) => item?.passed === false)
    : [];
  const errors = Array.isArray(guard.errors) ? guard.errors : [];

  const summary: Record<string, unknown> = {};
  if (errors.length) summary.errors = errors;
  if (failedRules.length) {
    summary.failed_rules = failedRules.map((rule: Record<string, unknown>) => ({
      rule_name: rule.rule_name,
      severity: rule.severity,
      category: rule.category,
      message: rule.message,
      details: rule.details,
    }));
  }
  if (modifications.length) {
    summary.modifications = modifications
      .filter((item: Record<string, unknown>) => item?.modified)
      .map((item: Record<string, unknown>) => ({
        modifier_name: item.modifier_name,
        field_name: item.field_name,
        original_value: item.original_value,
        new_value: item.new_value,
        reason: item.reason,
      }));
  }
  return Object.keys(summary).length ? summary : null;
};

const buildTradeDetails = (payload: Record<string, unknown>) => {
  const details: Record<string, unknown> = {};
  if (payload.final_order && typeof payload.final_order === "object") {
    details.final_order = payload.final_order;
  }
  if (payload.result && typeof payload.result === "object") {
    details.result = payload.result;
  }
  if (payload.error) details.error = payload.error;
  if (payload.execution_idea && typeof payload.execution_idea === "object") {
    details.execution_idea = payload.execution_idea;
  }
  return Object.keys(details).length ? details : null;
};

export const stageMessage = (topic: string, payload: unknown): string | null => {
  const data = payload && typeof payload === "object" ? (payload as Record<string, unknown>) : {};
  const formatValue = (value: unknown) => {
    if (value === null || value === undefined) return "--";
    if (typeof value === "number") return value.toLocaleString(undefined, { maximumFractionDigits: 6 });
    if (typeof value === "string") return value;
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  };

  if (topic === "scanner.ema.log") {
    const detail = data.data && typeof data.data === "object" ? (data.data as Record<string, unknown>) : {};
    if (data.event === "scan_init") return "EMA scan started";
    if (data.event === "scan_config") {
      const assets =
        typeof detail.assets_count === "number" ? `${detail.assets_count} assets` : null;
      const timeframes =
        typeof detail.timeframes_count === "number" ? `${detail.timeframes_count} intervals` : null;
      const lines =
        typeof detail.ema_lines_count === "number" ? `${detail.ema_lines_count} EMA lines` : null;
      const tolerance =
        typeof detail.tolerance_pct === "number" ? `${detail.tolerance_pct}% tol` : null;
      const summary = [assets, timeframes, lines, tolerance].filter(Boolean).join(" · ");
      return summary ? `EMA config · ${summary}` : "EMA config loaded";
    }
    if (data.event === "scan_assets") {
      return null;
    }
    if (data.event === "scan_finished") {
      const signals = typeof detail.signals === "number" ? detail.signals : null;
      return signals !== null ? `EMA scan finished · ${signals} signals` : "EMA scan finished";
    }
    if (data.event === "scan_cancel_requested") {
      return "EMA scan cancel requested";
    }
    if (data.event === "scan_cancelled") {
      return "EMA scan cancelled";
    }
    if (data.event === "state_processed") {
      const signals = typeof detail.signals === "number" ? detail.signals : null;
      const events = typeof detail.events === "number" ? detail.events : null;
      const summary = [
        signals !== null ? `${signals} signals` : null,
        events !== null ? `${events} events` : null,
      ]
        .filter(Boolean)
        .join(" · ");
      return summary ? `State manager processed · ${summary}` : "State manager processed";
    }
    if (data.event === "scan_empty_config") return "EMA scan skipped · empty config";
    if (data.event === "scan_error" && typeof detail.error === "string") {
      return `EMA scan error · ${detail.error}`;
    }
    return null;
  }
  if (topic === "scanner.ema.signals") {
    const count = typeof data.count === "number" ? data.count : null;
    return count !== null ? `EMA scan complete · ${count} signals` : "EMA scan complete";
  }
  if (topic === "scanner.ema.state") return "State manager updated";

  if (topic === "scanner.quant.log") {
    if (data.type === "cycle-start") return "Quant scan started";
    if (data.type === "cycle-end") return "Quant scan complete";
    if (data.type === "info" && typeof data.message === "string") {
      if (data.message.startsWith("Quant config")) return data.message;
      if (data.message.startsWith("Results:")) return data.message;
      return null;
    }
    if (data.type === "error" && typeof data.message === "string") {
      return `Quant scan error · ${data.message}`;
    }
    return null;
  }
  if (topic === "scanner.quant.completed") {
    const count = typeof data.count === "number" ? data.count : null;
    return count !== null ? `Quant scan complete · ${count} snapshots` : "Quant scan complete";
  }

  if (topic === "automation.prompt.requested") {
    const symbol = extractSymbol(data);
    const trigger = typeof data.trigger_reason === "string" ? data.trigger_reason : null;
    const intervals = Array.isArray(data.intervals)
      ? data.intervals.filter((item) => typeof item === "string")
      : [];
    const intervalLabel =
      intervals.length > 3
        ? `${intervals.slice(0, 3).join(", ")} +${intervals.length - 3}`
        : intervals.join(", ");
    const parts = [
      symbol ? `ticker=${symbol}` : null,
      intervalLabel ? `intervals=${intervalLabel}` : null,
      trigger ? `trigger=${trigger}` : null,
    ]
      .filter(Boolean)
      .join(" · ");
    return parts ? `Prompt queued · ${parts}` : "Prompt queued";
  }
  if (topic === "automation.prompt.started") {
    const symbol = extractSymbol(data);
    const intervals = Array.isArray(data.intervals)
      ? data.intervals.filter((item) => typeof item === "string")
      : [];
    const intervalLabel =
      intervals.length > 3
        ? `${intervals.slice(0, 3).join(", ")} +${intervals.length - 3}`
        : intervals.join(", ");
    const trigger = typeof data.trigger_reason === "string" ? data.trigger_reason : null;
    const parts = [
      symbol ? `ticker=${symbol}` : null,
      intervalLabel ? `intervals=${intervalLabel}` : null,
      trigger ? `trigger=${trigger}` : null,
    ]
      .filter(Boolean)
      .join(" · ");
    return parts ? `Prompt build started · ${parts}` : "Prompt build started";
  }
  if (topic === "automation.prompt.waiting_quant") {
    const attempt = typeof data.attempt === "number" ? data.attempt : null;
    const retry = typeof data.retry_in_seconds === "number" ? data.retry_in_seconds : null;
    const detail = [
      attempt !== null ? `attempt=${attempt}` : null,
      retry !== null ? `retry=${retry}s` : null,
    ]
      .filter(Boolean)
      .join(" · ");
    return detail ? `Prompt waiting for quant · ${detail}` : "Prompt waiting for quant";
  }
  if (topic === "automation.prompt.failed") {
    const error = typeof data.error === "string" ? data.error : null;
    return error ? `Prompt failed · ${error}` : "Prompt failed";
  }
  if (topic === "automation.prompt.completed") {
    const template = typeof data.template_name === "string" ? data.template_name : null;
    const queued =
      typeof data.queued_for_llm === "boolean" ? (data.queued_for_llm ? "queued" : "skipped") : null;
    const promptChars =
      typeof data.prompt_chars === "number" ? `${data.prompt_chars} chars` : null;
    const parts = [
      template ? `template=${template}` : null,
      promptChars,
      queued ? `llm=${queued}` : null,
    ]
      .filter(Boolean)
      .join(" · ");
    return parts ? `Prompt built · ${parts}` : "Prompt built";
  }
  if (topic === "automation.llm.requested") {
    const symbol = extractSymbol(data);
    const provider = typeof data.provider === "string" ? data.provider : null;
    const protocol = typeof data.protocol === "string" ? data.protocol : null;
    const model = typeof data.model === "string" ? data.model : null;
    const promptChars =
      typeof data.prompt_chars === "number" ? `${data.prompt_chars} chars` : null;
    const parts = [
      symbol ? `ticker=${symbol}` : null,
      provider ? `provider=${provider}` : null,
      protocol ? `protocol=${protocol}` : null,
      model ? `model=${model}` : null,
      promptChars,
    ]
      .filter(Boolean)
      .join(" · ");
    return parts ? `LLM request queued · ${parts}` : "LLM request queued";
  }
  if (topic === "automation.llm.completed") {
    const symbol = extractSymbol(data);
    const protocol = typeof data.protocol === "string" ? data.protocol : null;
    const ideas = Array.isArray(data.execution_ideas) ? data.execution_ideas.length : null;
    const responseMeta =
      data.response_meta && typeof data.response_meta === "object"
        ? (data.response_meta as Record<string, unknown>)
        : null;
    const tokens =
      responseMeta && typeof responseMeta.tokens_used === "number"
        ? `${responseMeta.tokens_used} tokens`
        : null;
    const latency =
      responseMeta && typeof responseMeta.latency_ms === "number"
        ? `${responseMeta.latency_ms}ms`
        : null;
    const ideaList = Array.isArray(data.execution_ideas)
      ? data.execution_ideas
          .slice(0, 3)
          .map((idea) => {
            if (!idea || typeof idea !== "object") return null;
            const record = idea as Record<string, unknown>;
            const symbol = typeof record.symbol === "string" ? record.symbol : null;
            const action = typeof record.action === "string" ? record.action : null;
            if (!symbol && !action) return null;
            return [symbol, action].filter(Boolean).join(" ");
          })
          .filter(Boolean)
      : [];
    const ideaLabel =
      ideaList.length > 0
        ? `${ideaList.join(", ")}${ideas && ideas > ideaList.length ? " +" : ""}`
        : null;
    const parts = [
      symbol ? `ticker=${symbol}` : null,
      protocol ? `protocol=${protocol}` : null,
      ideas !== null ? `${ideas} idea(s)` : null,
      tokens,
      latency,
      ideaLabel,
    ]
      .filter(Boolean)
      .join(" · ");
    return parts ? `LLM parsed · ${parts}` : "LLM parsed";
  }
  if (topic === "automation.llm.failed") {
    const symbol = extractSymbol(data);
    const protocol = typeof data.protocol === "string" ? data.protocol : null;
    const error = typeof data.error === "string" ? data.error : null;
    const parts = [symbol, protocol ? `protocol=${protocol}` : null, error].filter(Boolean);
    return parts.length ? `LLM failed · ${parts.join(" · ")}` : "LLM failed";
  }
  if (topic === "automation.parser.completed") {
    const symbol = extractSymbol(data);
    const parseResult =
      data.parse_result && typeof data.parse_result === "object"
        ? (data.parse_result as Record<string, unknown>)
        : null;
    const success =
      parseResult && typeof parseResult.success === "boolean" ? parseResult.success : true;
    const ideas = Array.isArray(parseResult?.ideas) ? parseResult?.ideas.length : null;
    const error = typeof parseResult?.error === "string" ? parseResult?.error : null;
    if (!success) {
      if (symbol && error) return `Response parse failed · ${symbol} · ${error}`;
      if (symbol) return `Response parse failed · ${symbol}`;
      return error ? `Response parse failed · ${error}` : "Response parse failed";
    }
    if (symbol && ideas !== null) return `Response parsed · ${symbol} · ${ideas} idea(s)`;
    if (symbol) return `Response parsed · ${symbol}`;
    return ideas !== null ? `Response parsed · ${ideas} idea(s)` : "Response parsed";
  }
  if (topic === "automation.parser.failed") {
    const symbol = extractSymbol(data);
    const error = typeof data.error === "string" ? data.error : null;
    if (symbol && error) return `Response parse failed · ${symbol} · ${error}`;
    if (symbol) return `Response parse failed · ${symbol}`;
    return error ? `Response parse failed · ${error}` : "Response parse failed";
  }
  if (topic === "automation.guard.started") {
    const symbol = extractSymbol(data);
    return symbol ? `Trade guard started · ${symbol}` : "Trade guard started";
  }
  if (topic === "automation.guard.passed") {
    const symbol = extractSymbol(data);
    const mods = typeof data.modifications === "number" ? data.modifications : null;
    const warnings = Array.isArray(data.warnings) ? data.warnings.join(", ") : null;
    const details = [
      mods !== null ? `modifications=${mods}` : null,
      warnings ? `warnings=${warnings}` : null,
    ]
      .filter(Boolean)
      .join(" · ");
    if (symbol && details) return `Trade guard passed · ${symbol}\n${details}`;
    if (symbol) return `Trade guard passed · ${symbol}`;
    return details ? `Trade guard passed\n${details}` : "Trade guard passed";
  }
  if (topic === "automation.guard.rejected") {
    const symbol = extractSymbol(data);
    const errors = Array.isArray(data.errors) ? data.errors.join(", ") : null;
    if (symbol && errors) return `Trade guard rejected · ${symbol}\n${errors}`;
    if (symbol) return `Trade guard rejected · ${symbol}`;
    return errors ? `Trade guard rejected\n${errors}` : "Trade guard rejected";
  }
  if (topic === "automation.circuit.passed") {
    const symbol = extractSymbol(data);
    return symbol ? `Circuit breaker passed · ${symbol}` : "Circuit breaker passed";
  }
  if (topic === "automation.circuit.blocked") {
    const symbol = extractSymbol(data);
    const reasons = Array.isArray(data.reasons) ? data.reasons.join(", ") : null;
    if (symbol && reasons) return `Circuit breaker blocked · ${symbol}\n${reasons}`;
    if (symbol) return `Circuit breaker blocked · ${symbol}`;
    return reasons ? `Circuit breaker blocked\n${reasons}` : "Circuit breaker blocked";
  }
  if (topic === "automation.order.queued") {
    const symbol = extractSymbol(data);
    return symbol ? `Order queued · ${symbol}` : "Order queued";
  }
  if (topic === "automation.order.modified") {
    const mods = Array.isArray(data.modifications) ? data.modifications : [];
    const parts = mods
      .map((entry) => {
        if (!entry || typeof entry !== "object") return "";
        const record = entry as Record<string, unknown>;
        const field = typeof record.field_name === "string" && record.field_name ? record.field_name : "order";
        const original = formatValue(record.original_value);
        const next = formatValue(record.new_value);
        const reason =
          typeof record.reason === "string" && record.reason ? ` (${record.reason})` : "";
        return `${field} ${original} → ${next}${reason}`;
      })
      .filter(Boolean);
    if (parts.length === 0) return "Guard modified order";
    return `Guard modified · ${parts.join(", ")}`;
  }
  if (topic === "automation.order.dropped") {
    const reason = typeof data.error === "string" ? data.error : null;
    if (reason && reason.startsWith("execution_mode:")) {
      const mode = reason.split(":")[1] || "unknown";
      const label = mode.replace(/_/g, " ");
      return `Execution skipped · ${label}`;
    }
    return reason ? `Order dropped · ${reason}` : "Order dropped";
  }
  if (topic === "automation.pipeline.started") {
    const mode = typeof data.execution_mode === "string" ? data.execution_mode : null;
    const ema = typeof data.ema_interval_seconds === "number" ? `${data.ema_interval_seconds}s` : null;
    const quant =
      typeof data.quant_interval_seconds === "number" ? `${data.quant_interval_seconds}s` : null;
    const parts = [
      mode ? `mode=${mode}` : null,
      ema ? `ema=${ema}` : null,
      quant ? `quant=${quant}` : null,
    ]
      .filter(Boolean)
      .join(" · ");
    return parts ? `Pipeline online · ${parts}` : "Pipeline online";
  }
  if (topic === "automation.pipeline.stopped") {
    return "Pipeline stopped";
  }
  if (topic === "automation.pipeline.positions_unavailable") {
    const error = typeof data.error === "string" && data.error ? data.error : null;
    const message =
      typeof data.message === "string" && data.message ? data.message : "Portfolio snapshot unavailable";
    return error ? `${message} · ${error}` : message;
  }
  if (topic === "automation.session.started") {
    const mode = typeof data.execution_mode === "string" ? data.execution_mode : null;
    const ema = typeof data.ema_interval_seconds === "number" ? `${data.ema_interval_seconds}s` : null;
    const quant =
      typeof data.quant_interval_seconds === "number" ? `${data.quant_interval_seconds}s` : null;
    const provider = typeof data.provider === "string" && data.provider ? data.provider : null;
    const model = typeof data.model === "string" && data.model ? data.model : null;
    const parts = [
      mode ? `mode=${mode}` : null,
      ema ? `ema=${ema}` : null,
      quant ? `quant=${quant}` : null,
      provider ? `provider=${provider}` : null,
      model ? `model=${model}` : null,
    ]
      .filter(Boolean)
      .join(" · ");
    return parts ? `Automation started · ${parts}` : "Automation started";
  }
  if (topic === "automation.session.config") {
    const ema = typeof data.ema_interval_seconds === "number" ? `${data.ema_interval_seconds}s` : null;
    const quant =
      typeof data.quant_interval_seconds === "number" ? `${data.quant_interval_seconds}s` : null;
    const provider = typeof data.provider === "string" && data.provider ? data.provider : null;
    const model = typeof data.model === "string" && data.model ? data.model : null;
    const parts = [
      typeof data.execution_mode === "string" ? `mode=${data.execution_mode}` : null,
      ema ? `ema=${ema}` : null,
      quant ? `quant=${quant}` : null,
      provider ? `provider=${provider}` : null,
      model ? `model=${model}` : null,
    ]
      .filter(Boolean)
      .join(" · ");
    return parts ? `Automation config · ${parts}` : "Automation config";
  }
  if (topic === "automation.session.stopped") {
    return "Automation stopped";
  }
  if (topic === "automation.session.purged") {
    const count = payload && typeof payload === "object" ? (payload as Record<string, unknown>).purged : null;
    return typeof count === "number" ? `Outbox purge completed · ${count} rows` : "Outbox purge completed";
  }
  if (topic === "trade.executed") {
    const summary = buildOrderSummary(data);
    return summary ? `Trade executed · ${summary}` : "Trade executed";
  }
  if (topic === "trade.failed") {
    const error = typeof data.error === "string" ? data.error : null;
    if (error === "trade_guard_rejected") return "Trade guard rejected";
    if (error === "circuit_breaker_blocked") return "Circuit breaker blocked";
    const summary = buildOrderSummary(data);
    if (summary && error) return `Trade failed · ${summary} · ${error}`;
    if (summary) return `Trade failed · ${summary}`;
    return error ? `Trade failed · ${error}` : "Trade failed";
  }

  return null;
};

const buildStageLogEntry = (topic: string, payload: unknown, ts?: string): AutomationLog | null => {
  const message = stageMessage(topic, payload);
  if (!message) return null;
  const data: Record<string, unknown> = { message, event_type: topic };
  let cycleNumber: number | undefined;
  if (payload && typeof payload === "object") {
    const symbol = extractSymbol(payload as Record<string, unknown>);
    if (symbol) {
      data.symbol = symbol;
    }
    const record = payload as Record<string, unknown>;
    const rawCycle = record.cycle_number;
    if (typeof rawCycle === "number" && Number.isFinite(rawCycle)) {
      cycleNumber = rawCycle;
    }
  }

  if (topic === "automation.prompt.completed" && payload && typeof payload === "object") {
    const record = payload as Record<string, unknown>;
    if (typeof record.prompt_text === "string" && record.prompt_text.trim()) {
      data.prompt_text = record.prompt_text;
    }
    if (typeof record.template_id === "number") {
      data.template_id = record.template_id;
    }
    if (typeof record.template_name === "string") {
      data.template_name = record.template_name;
    }
  }
  if (
    (topic === "automation.llm.completed" || topic === "automation.llm.failed") &&
    payload &&
    typeof payload === "object"
  ) {
    const record = payload as Record<string, unknown>;
    if (typeof record.protocol === "string" && record.protocol.trim()) {
      data.protocol = record.protocol;
    }
    if (typeof record.provider === "string" && record.provider.trim()) {
      data.provider = record.provider;
    }
    if (typeof record.model === "string" && record.model.trim()) {
      data.model = record.model;
    }
    if (typeof record.error === "string" && record.error.trim()) {
      data.error = record.error;
    }
    const response =
      typeof record.llm_response === "string"
        ? record.llm_response
        : typeof record.raw_response === "string"
          ? record.raw_response
          : null;
    if (response && response.trim()) {
      data.llm_response = response;
    }
    if (record.response_meta && typeof record.response_meta === "object") {
      data.response_meta = record.response_meta as Record<string, unknown>;
    }
    if (record.parse_result && typeof record.parse_result === "object") {
      data.parse_result = record.parse_result as Record<string, unknown>;
    }
  }
  if (topic === "automation.llm.requested" && payload && typeof payload === "object") {
    const record = payload as Record<string, unknown>;
    if (typeof record.protocol === "string" && record.protocol.trim()) {
      data.protocol = record.protocol;
    }
    if (typeof record.provider === "string" && record.provider.trim()) {
      data.provider = record.provider;
    }
    if (typeof record.model === "string" && record.model.trim()) {
      data.model = record.model;
    }
  }
  if (
    (topic === "automation.parser.completed" || topic === "automation.parser.failed") &&
    payload &&
    typeof payload === "object"
  ) {
    const record = payload as Record<string, unknown>;
    if (record.parse_result && typeof record.parse_result === "object") {
      data.parse_result = record.parse_result as Record<string, unknown>;
    } else {
      data.parse_result = record;
    }
    if (record.response_meta && typeof record.response_meta === "object") {
      data.response_meta = record.response_meta as Record<string, unknown>;
    }
    if (typeof record.llm_response === "string" && record.llm_response.trim()) {
      data.llm_response = record.llm_response;
    }
  }
  if (
    (topic === "trade.executed" || topic === "trade.failed") &&
    payload &&
    typeof payload === "object"
  ) {
    const details = buildTradeDetails(payload as Record<string, unknown>);
    if (details) data.details = details;
  }
  if (
    (topic === "automation.guard.passed" || topic === "automation.guard.rejected") &&
    payload &&
    typeof payload === "object"
  ) {
    const details = buildGuardDetails(payload as Record<string, unknown>);
    if (details) data.details = details;
  }
  if (topic === "automation.circuit.blocked" && payload && typeof payload === "object") {
    const record = payload as Record<string, unknown>;
    if (Array.isArray(record.reasons) && record.reasons.length) {
      data.details = { reasons: record.reasons };
    }
  }

  return {
    created_at: ts || new Date().toISOString(),
    log_type: resolveLogType(topic),
    cycle_number: cycleNumber,
    data,
  };
};

export const useAutomationStore = defineStore("automation", {
  state: () => ({
    sessions: [] as AutomationSession[],
    positions: [] as AutomationPosition[],
    trades: [] as AutomationTrade[],
    logs: [] as AutomationLog[],
    isConnected: false,
    pendingDisconnect: null as DisconnectReason | null,
    promptSession: {
      sessionId: null as string | null,
      startedAt: null as string | null,
      promptCount: 0,
    },
    status: {
      isRunning: false,
      executionMode: "dry_run",
      currentCycle: 0,
      sessionId: null as string | null,
      circuitBreakerTriggered: false,
      circuitBreakerReason: null as string | null,
    },
  }),
  actions: {
    connectSocket(exchangeId?: string) {
      if (socketExchangeId !== (exchangeId || "")) {
        this.disconnectSocket();
      }

      const socket = socketClient.connect(exchangeId);
      socketExchangeId = exchangeId || "";

      socket.off("connect");
      socket.off("disconnect");
      socket.off("event");

      socket.on("connect", () => {
        this.isConnected = true;
        socket.emit("subscribe", { topics: AUTOMATION_TOPICS });
      });

      socket.on("disconnect", () => {
        this.isConnected = false;
      });

      socket.on("event", (envelope: RealtimeEnvelope) => {
        if (!envelope || envelope.type !== "event") return;
        const topic = envelope.topic || "";
        if (!topic) return;
        const payload = envelope.payload;
        const logEntry = buildStageLogEntry(topic, payload, envelope.ts);
        if (logEntry) {
          this.appendLog(logEntry);
        }
        if (topic === "scanner.ema.log" && payload && typeof payload === "object") {
          const record = payload as Record<string, unknown>;
          const cycleNumber = record.cycle_number;
          if (typeof cycleNumber === "number" && Number.isFinite(cycleNumber)) {
            this.status.currentCycle = cycleNumber;
          }
        }

        if (topic === "automation.session.started" && payload && typeof payload === "object") {
          const record = payload as Record<string, unknown>;
          const sessionId = typeof record.session_id === "string" ? record.session_id : null;
          const startedAt = typeof record.started_at === "string" ? record.started_at : envelope.ts || null;
          this.promptSession.sessionId = sessionId;
          this.promptSession.startedAt = startedAt;
          this.promptSession.promptCount = 0;
        }

        if (topic === "automation.session.stopped") {
          this.promptSession.sessionId = null;
          this.promptSession.startedAt = null;
          this.promptSession.promptCount = 0;
        }

        if (topic === "automation.prompt.requested" && this.promptSession.startedAt) {
          this.promptSession.promptCount += 1;
        }

        if (payload && typeof payload === "object") {
          const executionMode = (payload as Record<string, unknown>).execution_mode;
          if (typeof executionMode === "string") {
            this.status.executionMode = executionMode;
          }
        }

        if (topic === "trade.executed") {
          const record = payload as Record<string, unknown> | undefined;
          const idea = record?.execution_idea as Record<string, unknown> | undefined;
          const result = record?.result as Record<string, unknown> | undefined;
          const symbol =
            (idea?.symbol as string | undefined) ||
            (result?.symbol as string | undefined) ||
            "UNKNOWN";
          this.trades.unshift({
            symbol,
            action: (idea?.action as string | undefined) || undefined,
            entry_price: (result?.fill_price as number | undefined) || undefined,
            size_usd: (idea?.size_usd as number | undefined) || undefined,
            status: (result?.status as string | undefined) || "filled",
            created_at: envelope.ts || new Date().toISOString(),
          } as AutomationTrade);
          this.refreshPositions();
        }

        if (this.pendingDisconnect && topic === "automation.session.purged") {
          this.disconnectSocket();
          this.pendingDisconnect = null;
        }
      });
    },
    disconnectSocket() {
      socketClient.disconnect();
      socketExchangeId = "";
      this.isConnected = false;
    },
    deferDisconnect(reason: DisconnectReason = "stopped") {
      this.pendingDisconnect = reason;
    },
    async refreshPositions() {
      try {
        const response = await fetch("/api/v1/portfolio/snapshot");
        const data = await response.json();
        if (data?.data?.positions) {
          this.positions = data.data.positions;
        }
      } catch {
        // Ignore refresh errors
      }
    },
    appendLog(entry: AutomationLog) {
      this.logs.unshift(entry);
      if (this.logs.length > MAX_LOG_ENTRIES) {
        this.logs.pop();
      }
    },
    clearLogs() {
      this.logs = [];
    },
    applyState(data: AutomationStatePayload) {
      const isRunning = data.isRunning ?? data.is_running;
      if (typeof isRunning === "boolean") {
        this.status.isRunning = isRunning;
      }
      const executionMode = data.executionMode ?? data.execution_mode;
      if (executionMode) this.status.executionMode = executionMode;
      const currentCycle = data.currentCycle ?? data.current_cycle;
      if (typeof currentCycle === "number") {
        this.status.currentCycle = currentCycle;
      }
      const sessionId = data.sessionId ?? data.session_id;
      if (sessionId !== undefined) {
        this.status.sessionId = sessionId;
        if (typeof sessionId === "string" && sessionId !== this.promptSession.sessionId) {
          this.promptSession.sessionId = sessionId;
          this.promptSession.promptCount = 0;
        }
      }
      if (typeof data.started_at === "string") {
        if (data.started_at !== this.promptSession.startedAt) {
          this.promptSession.startedAt = data.started_at;
          this.promptSession.promptCount = 0;
        }
      }
      const circuitBreakerTriggered =
        data.circuitBreakerTriggered ?? data.circuit_breaker_triggered;
      if (typeof circuitBreakerTriggered === "boolean") {
        this.status.circuitBreakerTriggered = circuitBreakerTriggered;
      }
      const circuitBreakerReason = data.circuitBreakerReason ?? data.circuit_breaker_reason;
      if (circuitBreakerReason !== undefined) {
        this.status.circuitBreakerReason = circuitBreakerReason;
      }
      // Positions are sourced from portfolio snapshot.
      if (data.trades) this.trades = data.trades;
    },
  },
});
