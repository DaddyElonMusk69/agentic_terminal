export type ScannerSignal = {
  id: string;
  symbol: string;
  timeframe: string;
  signal: string;
  score?: number;
};

export type ScannerVote = {
  interval: string;
  param?: number | string;
};

export type ScannerChartPoint = {
  time: number;
  value: number;
};

export type ScannerCandle = {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
};

export type ScannerChartData = {
  candles: ScannerCandle[];
  emas?: Record<string, ScannerChartPoint[]>;
  bollinger?: {
    upper?: ScannerChartPoint[];
    middle?: ScannerChartPoint[];
    lower?: ScannerChartPoint[];
  };
};

export type ScannerResult = {
  id?: number | string;
  ticker: string;
  votes?: number;
  intervals?: string[];
  ema_votes?: ScannerVote[];
  bb_votes?: ScannerVote[];
  chart_data?: Record<string, ScannerChartData>;
};

export type ScannerLog = {
  message?: string;
  type?: string;
  event?: string;
  data?: Record<string, unknown>;
  cycle_number?: number;
};

export type ScannerParameter = {
  id: string | number;
  param_type: string;
  value: number | string;
};

export type ScannerConfig = {
  parameters: ScannerParameter[];
};

export type EmaScannerLine = {
  id: number;
  length: number;
};

export type EmaScannerConfig = {
  ema_lines: EmaScannerLine[];
  tolerance_pct: number;
  available_intervals: string[];
  scan_intervals: string[];
};

export type EmaScannerRunPayload = {
  results: ScannerResult[];
};
