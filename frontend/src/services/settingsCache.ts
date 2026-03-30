export type DynamicSources = {
  ai500: { enabled: boolean; limit: number };
  ai300: { enabled: boolean; limit: number; level?: string };
  oi_top: { enabled: boolean; limit: number; duration: string };
  oi_low: { enabled: boolean; limit: number; duration: string };
  netflow_top: { enabled: boolean; limit: number; duration: string };
  netflow_low: { enabled: boolean; limit: number; duration: string };
  futures_depth: { enabled: boolean; limit: number };
  excluded_assets: { enabled: boolean; symbols: string };
};

export type MarketCacheData = {
  assets: string[];
  manualAssets: string[];
  usStockAssets: string[];
  usStockMarketOpen: boolean;
  intervals: string[];
  dynamicEnabled: boolean;
  hasApiKey: boolean;
  isBinanceActive: boolean;
  dynamicSources: DynamicSources;
  dynamicRefreshMinutes: number;
  dynamicOiSource: string;
};

export type ProviderSettings = {
  base_url?: string;
  display_name?: string;
  protocol?: string;
};

export type ProviderInfo = {
  name: string;
  models?: string[];
  configured?: boolean;
  is_enabled?: boolean;
  default_model?: string | null;
  settings?: ProviderSettings | null;
};

export type PromptConfigCacheItem = {
  id: number;
  name: string;
};

type CacheEntry<T> = {
  timestamp: number;
  value: T;
};

const cacheTtlMs = 5 * 60 * 1000;
const modelCacheTtlMs = 24 * 60 * 60 * 1000;
const storagePrefix = "td_cache:";

let marketCache: CacheEntry<MarketCacheData> | null = null;
let providersCache: CacheEntry<ProviderInfo[]> | null = null;
let promptConfigsCache: CacheEntry<PromptConfigCacheItem[]> | null = null;
const modelCache: Record<string, CacheEntry<string[]>> = {};
type MarketCacheListener = (data: MarketCacheData) => void;
const marketListeners = new Set<MarketCacheListener>();

const isExpired = (timestamp: number, ttlMs = cacheTtlMs) => Date.now() - timestamp > ttlMs;

const modelStorageKey = (providerName: string) => `${storagePrefix}models:${providerName}`;
const promptConfigStorageKey = () => `${storagePrefix}prompt_configs`;

const readStorageEntry = <T>(key: string, ttlMs: number) => {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CacheEntry<T>;
    if (!parsed || typeof parsed.timestamp !== "number") return null;
    if (isExpired(parsed.timestamp, ttlMs)) {
      window.localStorage.removeItem(key);
      return null;
    }
    return parsed.value;
  } catch {
    return null;
  }
};

const writeStorageEntry = <T>(key: string, value: T) => {
  if (typeof window === "undefined") return;
  try {
    const payload: CacheEntry<T> = { timestamp: Date.now(), value };
    window.localStorage.setItem(key, JSON.stringify(payload));
  } catch {
    // Ignore storage errors.
  }
};

const cloneProviders = (list: ProviderInfo[]) =>
  list.map((provider) => ({
    ...provider,
    models: Array.isArray(provider.models) ? [...provider.models] : [],
    settings: provider.settings ? { ...provider.settings } : null,
  }));

const defaultDynamicSources: DynamicSources = {
  ai500: { enabled: false, limit: 10 },
  ai300: { enabled: false, limit: 20, level: "" },
  oi_top: { enabled: false, limit: 20, duration: "1h" },
  oi_low: { enabled: false, limit: 20, duration: "1h" },
  netflow_top: { enabled: false, limit: 20, duration: "1h" },
  netflow_low: { enabled: false, limit: 20, duration: "1h" },
  futures_depth: { enabled: false, limit: 60 },
  excluded_assets: { enabled: false, symbols: "" },
};

const cloneDynamicSources = (sources: Partial<DynamicSources> | DynamicSources): DynamicSources => ({
  ai500: { ...defaultDynamicSources.ai500, ...(sources?.ai500 || {}) },
  ai300: { ...defaultDynamicSources.ai300, ...(sources?.ai300 || {}) },
  oi_top: { ...defaultDynamicSources.oi_top, ...(sources?.oi_top || {}) },
  oi_low: { ...defaultDynamicSources.oi_low, ...(sources?.oi_low || {}) },
  netflow_top: { ...defaultDynamicSources.netflow_top, ...(sources?.netflow_top || {}) },
  netflow_low: { ...defaultDynamicSources.netflow_low, ...(sources?.netflow_low || {}) },
  futures_depth: { ...defaultDynamicSources.futures_depth, ...(sources?.futures_depth || {}) },
  excluded_assets: { ...defaultDynamicSources.excluded_assets, ...(sources?.excluded_assets || {}) },
});

const cloneMarketCache = (data: MarketCacheData): MarketCacheData => ({
  assets: [...data.assets],
  manualAssets: Array.isArray(data.manualAssets) ? [...data.manualAssets] : [],
  usStockAssets: Array.isArray(data.usStockAssets) ? [...data.usStockAssets] : [],
  usStockMarketOpen: Boolean(data.usStockMarketOpen),
  intervals: [...data.intervals],
  dynamicEnabled: data.dynamicEnabled,
  hasApiKey: data.hasApiKey,
  isBinanceActive: data.isBinanceActive,
  dynamicSources: cloneDynamicSources(data.dynamicSources),
  dynamicRefreshMinutes: data.dynamicRefreshMinutes,
  dynamicOiSource: data.dynamicOiSource || "nofx",
});

export const readMarketCache = () => {
  if (!marketCache) return null;
  if (isExpired(marketCache.timestamp)) {
    marketCache = null;
    return null;
  }
  return cloneMarketCache(marketCache.value);
};

export const writeMarketCache = (data: MarketCacheData) => {
  const cloned = cloneMarketCache(data);
  marketCache = { timestamp: Date.now(), value: cloned };
  marketListeners.forEach((listener) => {
    try {
      listener(cloneMarketCache(cloned));
    } catch {
      // Ignore listener errors.
    }
  });
};

export const subscribeMarketCache = (listener: MarketCacheListener) => {
  marketListeners.add(listener);
  return () => {
    marketListeners.delete(listener);
  };
};

export const readProvidersCache = () => {
  if (!providersCache) return null;
  if (isExpired(providersCache.timestamp)) {
    providersCache = null;
    return null;
  }
  return cloneProviders(providersCache.value);
};

export const writeProvidersCache = (list: ProviderInfo[]) => {
  providersCache = { timestamp: Date.now(), value: cloneProviders(list) };
};

export const readPromptConfigCache = () => {
  if (!promptConfigsCache) {
    const stored = readStorageEntry<PromptConfigCacheItem[]>(promptConfigStorageKey(), cacheTtlMs);
    if (stored) {
      promptConfigsCache = { timestamp: Date.now(), value: [...stored] };
    }
  }
  if (!promptConfigsCache) return null;
  if (isExpired(promptConfigsCache.timestamp)) {
    promptConfigsCache = null;
    return null;
  }
  return [...promptConfigsCache.value];
};

export const writePromptConfigCache = (list: PromptConfigCacheItem[]) => {
  promptConfigsCache = { timestamp: Date.now(), value: [...list] };
  writeStorageEntry(promptConfigStorageKey(), [...list]);
};

export const readModelCache = (providerName: string) => {
  const entry = modelCache[providerName];
  if (entry && !isExpired(entry.timestamp, modelCacheTtlMs)) {
    return [...entry.value];
  }
  if (entry) {
    delete modelCache[providerName];
  }
  const stored = readStorageEntry<string[]>(modelStorageKey(providerName), modelCacheTtlMs);
  if (!stored) return null;
  modelCache[providerName] = { timestamp: Date.now(), value: [...stored] };
  return [...stored];
};

export const writeModelCache = (providerName: string, models: string[]) => {
  modelCache[providerName] = { timestamp: Date.now(), value: [...models] };
  writeStorageEntry(modelStorageKey(providerName), [...models]);
};
