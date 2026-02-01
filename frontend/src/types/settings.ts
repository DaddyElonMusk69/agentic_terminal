export type MarketSetting = {
  key: string;
  value: string;
};

export type IntegrationSetting = {
  id: string;
  name: string;
  status: "connected" | "disconnected";
};

export type ThemeKey = "terminal" | "vanilla";
