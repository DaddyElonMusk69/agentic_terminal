export type AgentContext = {
  id: string;
  title: string;
  content: string;
};

export type ContextBuilderConfig = {
  id: number;
  name: string;
  intro: string;
  requirements: string;
  data_selections: string[];
  field_selections: Record<string, string[]>;
  vegas_interval_configs?: Record<string, number>;
  vegas_show_fast_tunnel?: boolean;
  vegas_show_medium_tunnel?: boolean;
  vegas_show_slow_tunnel?: boolean;
  vegas_show_bb?: boolean;
  vegas_bb_length?: number;
  vegas_bb_std?: number;
  is_default?: boolean;
  created_at?: string | null;
  updated_at?: string | null;
};

export type ContextBuilderDraft = {
  intro: string;
  requirements: string;
  data_selections: string[];
  field_selections: Record<string, string[]>;
  vegas_interval_configs: Record<string, number>;
  vegas_show_fast_tunnel: boolean;
  vegas_show_medium_tunnel: boolean;
  vegas_show_slow_tunnel: boolean;
  vegas_show_bb: boolean;
  vegas_bb_length: number;
  vegas_bb_std: number;
};

export type ContextPromptResponse = {
  template_id: number;
  template_name: string;
  prompt_text: string;
  data: Record<string, unknown>;
  chart_items: Record<string, unknown>[];
  created_at: string;
};

export type PromptTemplatePayload = {
  id: number;
  name: string;
  intro: string;
  response_format: string;
  quant_fields?: string[] | null;
  chart_defaults?: Record<string, unknown> | null;
  is_default?: boolean;
  created_at?: string | null;
  updated_at?: string | null;
};
