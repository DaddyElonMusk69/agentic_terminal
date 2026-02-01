<template>
  <span
    class="inline-flex items-center justify-center rounded-md border"
    :class="sizeClass"
    :style="badgeStyle"
    :title="label"
    aria-hidden="true"
  >
    <svg
      v-if="icon === 'binance'"
      :class="iconClass"
      viewBox="0 0 32 32"
      fill="currentColor"
      aria-hidden="true"
    >
      <polygon points="16,4 20,8 16,12 12,8" />
      <polygon points="8,12 12,16 8,20 4,16" />
      <polygon points="24,12 28,16 24,20 20,16" />
      <polygon points="16,12 20,16 16,20 12,16" />
      <polygon points="16,20 20,24 16,28 12,24" />
    </svg>
    <svg
      v-else-if="icon === 'okx'"
      :class="iconClass"
      viewBox="0 0 32 32"
      fill="currentColor"
      aria-hidden="true"
    >
      <rect x="6" y="6" width="8" height="8" rx="1.2" />
      <rect x="18" y="6" width="8" height="8" rx="1.2" />
      <rect x="6" y="18" width="8" height="8" rx="1.2" />
      <rect x="18" y="18" width="8" height="8" rx="1.2" />
    </svg>
    <svg
      v-else-if="icon === 'hyperliquid'"
      :class="iconClass"
      viewBox="0 0 32 32"
      fill="currentColor"
      aria-hidden="true"
    >
      <path d="M6 7h4v7h12V7h4v18h-4v-7H10v7H6V7z" />
    </svg>
    <span v-else class="text-[10px] font-semibold">{{ fallback }}</span>
  </span>
</template>

<script setup lang="ts">
import { computed } from "vue";

type Size = "sm" | "md" | "lg";

const props = defineProps<{ exchange?: string | null; size?: Size }>();

const icon = computed(() => {
  if (props.exchange === "binance") return "binance";
  if (props.exchange === "okx") return "okx";
  if (props.exchange === "hyperliquid") return "hyperliquid";
  return "generic";
});

const label = computed(() => {
  if (props.exchange === "binance") return "Binance";
  if (props.exchange === "okx") return "OKX";
  if (props.exchange === "hyperliquid") return "Hyperliquid";
  return "Exchange";
});

const sizeClass = computed(() => {
  if (props.size === "lg") return "h-9 w-9";
  if (props.size === "md") return "h-8 w-8";
  return "h-6 w-6";
});

const iconClass = computed(() => {
  if (props.size === "lg") return "h-6 w-6";
  if (props.size === "md") return "h-5 w-5";
  return "h-4 w-4";
});

const fallback = computed(() => {
  if (props.exchange === "binance") return "BN";
  if (props.exchange === "okx") return "OKX";
  if (props.exchange === "hyperliquid") return "HL";
  return "EX";
});

const badgeStyle = computed(() => {
  if (props.exchange === "binance") {
    return {
      color: "#F0B90B",
      backgroundColor: "rgba(240, 185, 11, 0.14)",
      borderColor: "rgba(240, 185, 11, 0.4)",
    };
  }
  if (props.exchange === "okx") {
    return {
      color: "rgb(231, 238, 247)",
      backgroundColor: "rgba(231, 238, 247, 0.08)",
      borderColor: "rgba(231, 238, 247, 0.28)",
    };
  }
  if (props.exchange === "hyperliquid") {
    return {
      color: "#22D3EE",
      backgroundColor: "rgba(34, 211, 238, 0.14)",
      borderColor: "rgba(34, 211, 238, 0.4)",
    };
  }
  return {
    color: "rgb(231, 238, 247)",
    backgroundColor: "rgba(231, 238, 247, 0.06)",
    borderColor: "rgba(231, 238, 247, 0.18)",
  };
});
</script>
