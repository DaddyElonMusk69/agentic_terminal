import { defineStore } from "pinia";
import type { IntegrationSetting, MarketSetting, ThemeKey } from "@/types/settings";

const themeStorageKey = "trading_dashboard_theme";
const themeOptions: ThemeKey[] = ["terminal", "vanilla"];

const applyTheme = (theme: ThemeKey) => {
  if (typeof document === "undefined") return;
  document.documentElement.dataset.theme = theme;
};

export const useSettingsStore = defineStore("settings", {
  state: () => ({
    market: [] as MarketSetting[],
    dynamicAssets: [] as string[],
    integrations: [] as IntegrationSetting[],
    cacheEnabled: true,
    theme: "terminal" as ThemeKey,
  }),
  actions: {
    initializeTheme() {
      if (typeof localStorage === "undefined") {
        applyTheme(this.theme);
        return;
      }
      const stored = localStorage.getItem(themeStorageKey);
      const nextTheme = themeOptions.includes(stored as ThemeKey)
        ? (stored as ThemeKey)
        : "terminal";
      this.theme = nextTheme;
      applyTheme(nextTheme);
    },
    setTheme(theme: ThemeKey) {
      if (!themeOptions.includes(theme)) return;
      this.theme = theme;
      if (typeof localStorage !== "undefined") {
        localStorage.setItem(themeStorageKey, theme);
      }
      applyTheme(theme);
    },
    setMarket(settings: MarketSetting[]) {
      this.market = settings;
    },
    setDynamicAssets(assets: string[]) {
      this.dynamicAssets = assets;
    },
    setIntegrations(items: IntegrationSetting[]) {
      this.integrations = items;
    },
    setCacheEnabled(value: boolean) {
      this.cacheEnabled = value;
    },
  },
});
