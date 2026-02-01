<template>
  <div
    class="flex h-9 items-center gap-3 border-b border-border bg-gradient-to-r from-surface/90 via-panel to-surface/90 px-3 text-[10px] text-text/90"
  >
    <div class="flex min-w-0 flex-[0_0_36%] items-center gap-2">
      <span class="font-mono text-[9px] uppercase tracking-[0.35em] text-muted">Markets</span>
      <div class="tape-mask min-w-0 flex-1">
        <div class="tape-track ticker-track">
          <div
            v-for="(item, index) in tickerLoop"
            :key="`ticker-${item.symbol}-${index}`"
            class="ticker-item"
          >
            <span class="ticker-symbol">{{ item.symbol }}</span>
            <span class="ticker-price">{{ formatPrice(item.price) }}</span>
            <span
              class="ticker-change"
              :class="item.changePercent >= 0 ? 'text-positive' : 'text-negative'"
            >
              {{ formatChange(item.changePercent) }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <div class="h-4 w-px bg-border/60"></div>

    <div class="flex min-w-0 flex-1 items-center gap-2">
      <span class="font-mono text-[9px] uppercase tracking-[0.35em] text-muted">News</span>
      <div class="tape-mask min-w-0 flex-1">
        <div class="tape-track news-track">
          <div
            v-for="(item, index) in newsLoop"
            :key="`news-${index}-${item.headline}`"
            class="news-item"
          >
            <span class="news-time">{{ item.time }}</span>
            <span class="news-source" :style="{ borderColor: item.color, color: item.color }">
              {{ item.source }}
            </span>
            <span class="news-headline">{{ item.headline }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import type { NewsItem, PriceItem } from "@/types/banner";

type TapeTickerItem = {
  symbol: string;
  price: number;
  changePercent: number;
};

type TapeNewsItem = {
  source: string;
  headline: string;
  time: string;
  category: "crypto" | "stocks";
  color: string;
};

type MarketDataItem = {
  symbol?: string;
  name?: string;
  price?: number | string;
  change_percent?: number | string;
  markPx?: string;
  prevDayPx?: string;
  priceChangePercent?: string;
};

const props = defineProps<{ priceTape?: PriceItem[]; newsTape?: NewsItem[] }>();

const tickerItems = ref<TapeTickerItem[]>([]);
const newsItems = ref<TapeNewsItem[]>([]);
const hasFetchedAssets = ref(false);
const lastAssets = ref<string[]>([]);
let tickerInterval: ReturnType<typeof setInterval> | null = null;
let newsInterval: ReturnType<typeof setInterval> | null = null;

const NEWS_FEEDS = [
  {
    name: "CoinDesk",
    category: "crypto",
    url: "https://www.coindesk.com/arc/outboundfeeds/rss/",
    color: "#f7931a",
  },
  {
    name: "CoinTelegraph",
    category: "crypto",
    url: "https://cointelegraph.com/rss",
    color: "#00cbff",
  },
];

const RSS_PROXY = "https://api.rss2json.com/v1/api.json?rss_url=";

const FALLBACK_NEWS: TapeNewsItem[] = [
  {
    source: "MarketWire",
    category: "stocks",
    headline: "Rates steady as traders watch macro prints",
    time: "12m",
    color: "#9ca3af",
  },
  {
    source: "CoinDesk",
    category: "crypto",
    headline: "Bitcoin holds range as flows stabilize",
    time: "24m",
    color: "#f7931a",
  },
  {
    source: "Reuters",
    category: "stocks",
    headline: "Tech leads futures higher into the close",
    time: "38m",
    color: "#9ca3af",
  },
];

const mapPropsToTickers = (items: PriceItem[] = []): TapeTickerItem[] =>
  items.map((item) => ({
    symbol: item.label,
    price: parseNumber(item.value),
    changePercent: parseChange(item.change),
  }));

const mapPropsToNews = (items: NewsItem[] = []): TapeNewsItem[] =>
  items.map((item) => ({
    source: "Wire",
    category: "stocks",
    headline: item.text,
    time: "now",
    color: "#9ca3af",
  }));

const tickerLoop = computed(() => {
  if (hasFetchedAssets.value) {
    return tickerItems.value.length > 0 ? [...tickerItems.value, ...tickerItems.value] : [];
  }
  const items = mapPropsToTickers(props.priceTape ?? []);
  const fallback = items.length > 0 ? items : [
    { symbol: "BTC", price: 0, changePercent: 0 },
    { symbol: "ETH", price: 0, changePercent: 0 },
    { symbol: "SOL", price: 0, changePercent: 0 },
  ];
  return [...fallback, ...fallback];
});

const newsLoop = computed(() => {
  const items =
    newsItems.value.length > 0
      ? newsItems.value
      : mapPropsToNews(props.newsTape ?? []);
  const fallback = items.length > 0 ? items : FALLBACK_NEWS;
  return [...fallback, ...fallback];
});

const formatPrice = (value: number) => {
  if (!Number.isFinite(value)) return "--";
  const minimumFractionDigits = value >= 1 ? 2 : 4;
  const formatter = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits,
    maximumFractionDigits: minimumFractionDigits,
  });
  return formatter.format(value);
};

const formatChange = (value: number) => {
  if (!Number.isFinite(value)) return "--";
  const sign = value >= 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
};

const parseNumber = (value?: string | number) => {
  if (value === undefined || value === null) return 0;
  if (typeof value === "number") return Number.isFinite(value) ? value : 0;
  const parsed = Number(value.replace(/,/g, ""));
  return Number.isFinite(parsed) ? parsed : 0;
};

const parseChange = (value?: string | number) => {
  if (value === undefined || value === null) return 0;
  if (typeof value === "number") return Number.isFinite(value) ? value : 0;
  const parsed = Number(String(value).replace("%", ""));
  return Number.isFinite(parsed) ? parsed : 0;
};

const buildPlaceholderTickers = (assets: string[]): TapeTickerItem[] =>
  assets.map((symbol) => ({
    symbol,
    price: Number.NaN,
    changePercent: Number.NaN,
  }));

const cleanHeadline = (title: string) => {
  const cleaned = title
    .replace(/<[^>]*>/g, "")
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'");
  return cleaned.length > 120 ? `${cleaned.slice(0, 120)}...` : cleaned;
};

const getRelativeTime = (date: Date) => {
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);

  if (diffMins < 1) return "now";
  if (diffMins < 60) return `${diffMins}m`;
  if (diffHours < 24) return `${diffHours}h`;
  return `${Math.floor(diffHours / 24)}d`;
};

const shuffle = <T,>(items: T[]) => {
  const list = [...items];
  for (let i = list.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [list[i], list[j]] = [list[j], list[i]];
  }
  return list;
};

const fetchTickerTape = async () => {
  let assets: string[] = [];
  try {
    const assetsRes = await fetch("/api/v1/market/monitored-assets");
    const assetsData = await assetsRes.json();
    assets = Array.isArray(assetsData?.data) ? assetsData.data : [];
  } catch {
    if (lastAssets.value.length > 0) {
      hasFetchedAssets.value = true;
      tickerItems.value = buildPlaceholderTickers(lastAssets.value);
    }
    return;
  }

  hasFetchedAssets.value = true;
  if (!assets.length) {
    tickerItems.value = [];
    return;
  }
  lastAssets.value = [...assets];

  try {
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), 10000);

    const marketRes = await fetch("/api/v1/market/prices", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ assets }),
      signal: controller.signal,
    });

    window.clearTimeout(timeoutId);
    let marketData: any = null;
    try {
      marketData = await marketRes.json();
    } catch {
      tickerItems.value = buildPlaceholderTickers(assets);
      return;
    }
    if (!marketRes.ok || !Array.isArray(marketData?.data)) {
      tickerItems.value = buildPlaceholderTickers(assets);
      return;
    }

    const marketMap = new Map<string, MarketDataItem>(
      marketData.data.map((item: MarketDataItem) => [item.symbol ?? item.name, item]),
    );

    tickerItems.value = assets.map((asset: string) => {
      const item = marketMap.get(asset) || marketMap.get(asset.replace("/", ""));
      if (!item) {
        return { symbol: asset, price: Number.NaN, changePercent: Number.NaN };
      }
      const price = parseNumber((item as any).price ?? (item as any).markPx ?? (item as any).value);
      const changePercentValue = Number((item as any).change_percent);
      return {
        symbol: asset,
        price: Number.isFinite(price) ? price : Number.NaN,
        changePercent: Number.isFinite(changePercentValue) ? changePercentValue : Number.NaN,
      };
    });
  } catch {
    tickerItems.value = buildPlaceholderTickers(assets);
  }
};

const fetchNewsTape = async () => {
  try {
    const allNews: TapeNewsItem[] = [];
    for (const feed of NEWS_FEEDS) {
      try {
        const response = await fetch(RSS_PROXY + encodeURIComponent(feed.url));
        const data = await response.json();
        if (data.status === "ok" && Array.isArray(data.items)) {
          const items = data.items.slice(0, 5).map((item: { title: string; pubDate: string }) => ({
            source: feed.name,
            category: feed.category as TapeNewsItem["category"],
            headline: cleanHeadline(item.title),
            time: getRelativeTime(new Date(item.pubDate)),
            color: feed.color,
          }));
          allNews.push(...items);
        }
      } catch {
        // Ignore feed error and fall back to available feeds
      }
    }

    newsItems.value = allNews.length > 0 ? shuffle(allNews) : FALLBACK_NEWS;
  } catch {
    newsItems.value = FALLBACK_NEWS;
  }
};

onMounted(() => {
  fetchTickerTape();
  fetchNewsTape();
  tickerInterval = setInterval(fetchTickerTape, 60000);
  newsInterval = setInterval(fetchNewsTape, 5 * 60 * 1000);
});

onBeforeUnmount(() => {
  if (tickerInterval) window.clearInterval(tickerInterval);
  if (newsInterval) window.clearInterval(newsInterval);
});
</script>

<style scoped>
.tape-mask {
  mask-image: linear-gradient(to right, transparent, black 6%, black 94%, transparent);
  -webkit-mask-image: linear-gradient(to right, transparent, black 6%, black 94%, transparent);
  overflow: hidden;
}

.tape-track {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  white-space: nowrap;
  min-width: max-content;
}

.ticker-track {
  animation: ticker-scroll 32s linear infinite;
}

.news-track {
  animation: news-scroll 90s linear infinite;
}

.ticker-track:hover,
.news-track:hover {
  animation-play-state: paused;
}

.ticker-item {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding-right: 12px;
  border-right: 1px solid rgba(148, 163, 184, 0.25);
  font-variant-numeric: tabular-nums;
}

.ticker-symbol {
  font-family: var(--font-mono);
  font-weight: 600;
  letter-spacing: 0.06em;
}

.ticker-price,
.ticker-change {
  font-family: var(--font-mono);
}

.news-item {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding-right: 16px;
  border-right: 1px solid rgba(148, 163, 184, 0.2);
  color: rgba(226, 232, 240, 0.9);
}

.news-time {
  font-family: var(--font-mono);
  font-size: 0.65rem;
  color: rgba(148, 163, 184, 0.8);
}

.news-source {
  font-size: 0.6rem;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  padding: 2px 6px;
  border-radius: 999px;
  border: 1px solid;
}

.news-headline {
  max-width: 420px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@keyframes ticker-scroll {
  0% {
    transform: translateX(0);
  }
  100% {
    transform: translateX(-50%);
  }
}

@keyframes news-scroll {
  0% {
    transform: translateX(0);
  }
  100% {
    transform: translateX(-50%);
  }
}
</style>
