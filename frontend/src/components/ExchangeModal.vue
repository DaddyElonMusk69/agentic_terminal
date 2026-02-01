<template>
  <TransitionRoot :show="open" as="template">
    <Dialog class="relative z-50" @close="$emit('close')">
      <TransitionChild
        as="template"
        enter="ease-out duration-200"
        enter-from="opacity-0"
        enter-to="opacity-100"
        leave="ease-in duration-150"
        leave-from="opacity-100"
        leave-to="opacity-0"
      >
        <div class="fixed inset-0 bg-black/50" />
      </TransitionChild>

      <div class="fixed inset-0 flex items-center justify-center p-4">
        <TransitionChild
          as="template"
          enter="ease-out duration-200"
          enter-from="opacity-0 translate-y-4"
          enter-to="opacity-100 translate-y-0"
          leave="ease-in duration-150"
          leave-from="opacity-100 translate-y-0"
          leave-to="opacity-0 translate-y-4"
        >
          <DialogPanel
            class="w-full max-w-5xl overflow-hidden rounded-lg border border-border bg-surface shadow-panel"
          >
            <div class="flex flex-wrap items-start justify-between gap-3 border-b border-border px-5 py-4">
              <div>
                <DialogTitle class="font-display text-base text-white">Exchange Command Center</DialogTitle>
                <p class="mt-1 text-xs text-muted">
                  Connect, validate, and activate the exchange account used for trading.
                </p>
              </div>
              <div class="flex items-center gap-2">
                <button
                  class="rounded-md border border-border bg-panel px-3 py-1.5 text-xs text-muted hover:text-text"
                  type="button"
                  :disabled="isBusy"
                  @click="refreshExchanges"
                >
                  {{ exchangeStore.isLoading ? "Refreshing..." : "Refresh" }}
                </button>
                <button
                  class="rounded-md border border-border bg-panel px-3 py-1.5 text-xs text-muted hover:text-text"
                  type="button"
                  @click="$emit('close')"
                >
                  Close
                </button>
              </div>
            </div>

            <div class="flex max-h-[78vh] flex-col gap-4 overflow-y-auto p-5 scrollbar-hidden">
              <div
                v-if="notice.message"
                class="rounded-md border px-3 py-2 text-xs"
                :class="noticeClasses"
              >
                {{ notice.message }}
              </div>

              <div class="grid gap-4 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
                <section class="space-y-4">
                  <div class="rounded-md border border-border bg-panel/50 p-4">
                    <div class="flex items-start justify-between gap-3">
                      <div>
                        <div class="text-[11px] uppercase tracking-wide text-muted">
                          Active Exchange
                        </div>
                        <div v-if="activeAccount" class="mt-2">
                          <div class="flex items-center gap-3">
                            <ExchangeBadge :exchange="activeAccount.exchange" size="lg" />
                            <div>
                              <div class="font-display text-sm text-text">
                                {{ activeAccount.name }}
                              </div>
                              <div class="text-xs text-muted">
                                {{ exchangeLabel(activeAccount.exchange) }}
                              </div>
                            </div>
                          </div>
                          <div class="mt-3 flex flex-wrap items-center gap-2 text-[11px]">
                            <span
                              class="rounded-full border px-2 py-0.5 uppercase tracking-wide"
                              :class="
                                activeAccount.is_testnet
                                  ? 'border-warning/40 bg-warning/10 text-warning'
                                  : 'border-positive/40 bg-positive/10 text-positive'
                              "
                            >
                              {{ activeAccount.is_testnet ? "Testnet" : "Mainnet" }}
                            </span>
                            <span
                              class="rounded-full border px-2 py-0.5 uppercase tracking-wide"
                              :class="
                                validationTone(activeAccount)
                              "
                            >
                              {{ validationLabel(activeAccount) }}
                            </span>
                            <span class="text-[11px] text-muted">
                              Last check: {{ formatTimestamp(activeAccount.validation?.last_validated_at) }}
                            </span>
                          </div>
                        </div>
                        <div v-else class="mt-2 text-xs text-muted">
                          No active exchange connected. Trading is disabled until one is activated.
                        </div>
                      </div>
                      <div v-if="activeAccount" class="flex flex-col items-end gap-2 text-xs">
                        <button
                          v-if="!confirmDeactivate"
                          class="rounded-md border border-border bg-panel px-3 py-1 text-xs text-muted hover:text-text"
                          type="button"
                          :disabled="isBusy"
                          @click="confirmDeactivate = true"
                        >
                          Deactivate
                        </button>
                        <div v-else class="flex flex-wrap items-center gap-2">
                          <button
                            class="rounded-md border border-negative/40 bg-negative/10 px-3 py-1 text-xs text-negative"
                            type="button"
                            :disabled="isBusy"
                            @click="handleDeactivate"
                          >
                            Confirm
                          </button>
                          <button
                            class="rounded-md border border-border bg-panel px-3 py-1 text-xs text-muted hover:text-text"
                            type="button"
                            :disabled="isBusy"
                            @click="confirmDeactivate = false"
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    </div>
                    <p class="mt-3 text-[11px] text-muted">
                      Switching the active exchange refreshes account data across scanners, automation,
                      and analytics.
                    </p>
                  </div>

                  <div class="rounded-md border border-border bg-panel/30 p-4">
                    <div class="flex items-center justify-between">
                      <div class="text-[11px] uppercase tracking-wide text-muted">
                        Connected Accounts
                      </div>
                      <span class="text-[11px] text-muted">
                        {{ exchangeStore.accounts.length }} total
                      </span>
                    </div>

                    <div
                      v-if="exchangeStore.isLoading && exchangeStore.accounts.length === 0"
                      class="mt-3 rounded-md border border-border bg-panel/40 px-3 py-4 text-center text-xs text-muted"
                    >
                      Loading exchange accounts...
                    </div>
                    <div
                      v-else-if="exchangeStore.accounts.length === 0"
                      class="mt-3 rounded-md border border-dashed border-border bg-panel/40 px-3 py-6 text-center text-xs text-muted"
                    >
                      No exchange accounts connected yet.
                    </div>
                    <div
                      v-else
                      class="mt-3 max-h-[42vh] space-y-3 overflow-y-auto pr-1 scrollbar-hidden"
                    >
                      <div
                        v-for="account in exchangeStore.accounts"
                        :key="account.id"
                        class="rounded-md border px-3 py-3"
                        :class="
                          account.is_active
                            ? 'border-accent/60 bg-accent/5'
                            : 'border-border bg-panel/40'
                        "
                      >
                        <div class="flex flex-wrap items-start justify-between gap-3">
                          <div>
                            <div class="flex items-center gap-3">
                              <ExchangeBadge :exchange="account.exchange" size="md" />
                              <div>
                                <div class="font-display text-sm text-text">
                                  {{ account.name }}
                                </div>
                                <div class="text-xs text-muted">
                                  {{ exchangeLabel(account.exchange) }}
                                  <span v-if="account.wallet_address">
                                    - {{ formatWallet(account.wallet_address) }}
                                  </span>
                                </div>
                              </div>
                            </div>
                            <div class="mt-2 flex flex-wrap items-center gap-2 text-[11px]">
                              <span
                                class="rounded-full border px-2 py-0.5 uppercase tracking-wide"
                                :class="
                                  account.is_testnet
                                    ? 'border-warning/40 bg-warning/10 text-warning'
                                    : 'border-positive/40 bg-positive/10 text-positive'
                                "
                              >
                                {{ account.is_testnet ? "Testnet" : "Mainnet" }}
                              </span>
                              <span
                                class="rounded-full border px-2 py-0.5 uppercase tracking-wide"
                                :class="
                                  validationTone(account)
                                "
                              >
                                {{ validationLabel(account) }}
                              </span>
                              <span class="text-[11px] text-muted">
                                Last check: {{ formatTimestamp(account.validation?.last_validated_at) }}
                              </span>
                            </div>
                            <div class="mt-2 flex flex-wrap items-center gap-2 text-[11px]">
                              <span
                                v-for="badge in credentialBadges(account)"
                                :key="badge.label"
                                class="rounded-full border px-2 py-0.5"
                                :class="
                                  badge.ok
                                    ? 'border-text/30 bg-text/10 text-text'
                                    : 'border-border bg-panel text-muted'
                                "
                              >
                                {{ badge.label }}
                              </span>
                            </div>
                          </div>
                          <div class="flex flex-col gap-2 text-xs">
                            <button
                              v-if="!account.is_active"
                              class="rounded-md border border-border bg-panel px-3 py-1 text-xs text-muted hover:text-text"
                              type="button"
                              :disabled="isBusy"
                              @click="handleActivate(account.id)"
                            >
                              {{ activatingId === account.id ? "Activating..." : "Activate" }}
                            </button>
                            <span
                              v-else
                              class="rounded-md border border-accent/40 bg-accent/10 px-3 py-1 text-center text-[11px] uppercase tracking-wide text-accent"
                            >
                              Active
                            </span>
                            <button
                              class="rounded-md border border-border bg-panel px-3 py-1 text-xs text-muted hover:text-text"
                              type="button"
                              :disabled="isBusy"
                              @click="handleValidate(account.id)"
                            >
                              {{ validatingId === account.id ? "Testing..." : "Validate" }}
                            </button>
                            <div v-if="confirmDeleteId === account.id" class="flex flex-wrap gap-2">
                              <button
                                class="rounded-md border border-negative/40 bg-negative/10 px-3 py-1 text-xs text-negative"
                                type="button"
                                :disabled="isBusy"
                                @click="handleDelete(account.id)"
                              >
                                Confirm
                              </button>
                              <button
                                class="rounded-md border border-border bg-panel px-3 py-1 text-xs text-muted hover:text-text"
                                type="button"
                                :disabled="isBusy"
                                @click="confirmDeleteId = null"
                              >
                                Cancel
                              </button>
                            </div>
                            <button
                              v-else
                              class="rounded-md border border-border bg-panel px-3 py-1 text-xs text-muted hover:text-text"
                              type="button"
                              :disabled="isBusy"
                              @click="confirmDeleteId = account.id"
                            >
                              Delete
                            </button>
                          </div>
                        </div>
                      </div>
                    </div>
                    <p v-if="exchangeStore.error" class="mt-3 text-xs text-negative">
                      {{ exchangeStore.error }}
                    </p>
                  </div>
                </section>

                <section class="space-y-4">
                  <div class="rounded-md border border-border bg-panel/50 p-4">
                    <div class="flex items-center justify-between">
                      <div class="text-[11px] uppercase tracking-wide text-muted">
                        Add New Exchange
                      </div>
                      <span class="text-[11px] text-muted">Credentials are stored server-side</span>
                    </div>

                    <div class="mt-3 grid gap-3">
                      <div class="space-y-2">
                        <div class="text-[11px] uppercase tracking-wide text-muted">Exchange Type</div>
                        <div class="grid grid-cols-3 gap-2">
                          <button
                            v-for="option in exchangeOptions"
                            :key="option.id"
                            class="flex flex-col items-start gap-1 rounded-md border px-3 py-2 text-left text-xs transition"
                            :class="
                              form.exchange === option.id
                                ? 'border-accent/60 bg-panel text-text'
                                : 'border-border bg-panel/40 text-muted hover:text-text'
                            "
                            type="button"
                            @click="setExchangeType(option.id)"
                          >
                            <span class="text-[11px] uppercase tracking-wide text-muted">
                              {{ option.short }}
                            </span>
                            <span class="font-display text-sm text-text">{{ option.label }}</span>
                            <span class="text-[11px] text-muted">{{ option.hint }}</span>
                          </button>
                        </div>
                      </div>

                      <label class="text-[11px] text-muted">
                        Account Name
                        <input
                          v-model="form.name"
                          class="mt-2 w-full rounded-md border border-border bg-panel px-3 py-2 text-xs text-text"
                          type="text"
                          maxlength="100"
                          placeholder="e.g. Primary Trading"
                          autocomplete="off"
                        />
                      </label>

                      <label class="flex items-center gap-2 text-xs text-muted">
                        <input v-model="form.is_testnet" type="checkbox" />
                        Use Testnet (recommended for initial setup)
                      </label>

                      <div v-if="form.exchange === 'hyperliquid'" class="grid gap-3">
                        <label class="text-[11px] text-muted">
                          Wallet Address
                          <input
                            v-model="form.wallet_address"
                            class="mt-2 w-full rounded-md border border-border bg-panel px-3 py-2 text-xs text-text"
                            type="text"
                            placeholder="0x..."
                            autocomplete="off"
                          />
                        </label>
                        <label class="text-[11px] text-muted">
                          Agent Private Key
                          <input
                            v-model="form.agent_key"
                            class="mt-2 w-full rounded-md border border-border bg-panel px-3 py-2 text-xs text-text"
                            type="password"
                            placeholder="Agent wallet private key"
                            autocomplete="off"
                          />
                        </label>
                        <p class="text-[11px] text-muted">
                          Create a dedicated agent key in Hyperliquid Settings to isolate trade access.
                        </p>
                      </div>

                      <div v-else class="grid gap-3">
                        <label class="text-[11px] text-muted">
                          API Key
                          <input
                            v-model="form.api_key"
                            class="mt-2 w-full rounded-md border border-border bg-panel px-3 py-2 text-xs text-text"
                            type="password"
                            placeholder="API key"
                            autocomplete="off"
                          />
                        </label>
                        <label class="text-[11px] text-muted">
                          API Secret
                          <input
                            v-model="form.api_secret"
                            class="mt-2 w-full rounded-md border border-border bg-panel px-3 py-2 text-xs text-text"
                            type="password"
                            placeholder="API secret"
                            autocomplete="off"
                          />
                        </label>
                        <label v-if="form.exchange === 'okx'" class="text-[11px] text-muted">
                          Passphrase
                          <input
                            v-model="form.passphrase"
                            class="mt-2 w-full rounded-md border border-border bg-panel px-3 py-2 text-xs text-text"
                            type="password"
                            placeholder="API passphrase"
                            autocomplete="off"
                          />
                        </label>
                      </div>

                      <div class="flex flex-wrap items-center gap-2">
                        <button
                          class="rounded-md border border-accent/60 bg-accent/10 px-3 py-2 text-xs text-text"
                          type="button"
                          :disabled="isBusy"
                          @click="handleAdd"
                        >
                          {{ isAdding ? "Saving..." : "Add Exchange" }}
                        </button>
                        <button
                          class="rounded-md border border-border bg-panel px-3 py-2 text-xs text-muted hover:text-text"
                          type="button"
                          :disabled="isBusy"
                          @click="resetForm"
                        >
                          Reset
                        </button>
                      </div>
                      <p v-if="formError" class="text-xs text-negative">{{ formError }}</p>
                    </div>
                  </div>

                  <div class="rounded-md border border-border bg-panel/30 p-4 text-[11px] text-muted">
                    <div class="flex items-start gap-2">
                      <svg
                        class="mt-0.5 h-4 w-4 text-accent"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        stroke-width="1.6"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                        aria-hidden="true"
                      >
                        <path d="M6 11V7a6 6 0 0112 0v4" />
                        <rect x="4" y="11" width="16" height="9" rx="2" />
                        <path d="M10 16h4" />
                      </svg>
                      <div class="space-y-1">
                        <div class="text-xs font-semibold text-text">Security & Access</div>
                        <div>
                          Credentials are encrypted server-side and never displayed again after saving.
                        </div>
                        <div>Use read-only keys or testnet credentials when validating new setups.</div>
                        <div>Validation runs a read-only account check and never places orders.</div>
                      </div>
                    </div>
                  </div>
                </section>
              </div>
            </div>
          </DialogPanel>
        </TransitionChild>
      </div>
    </Dialog>
  </TransitionRoot>
</template>

<script setup lang="ts">
import {
  Dialog,
  DialogPanel,
  DialogTitle,
  TransitionChild,
  TransitionRoot,
} from "@headlessui/vue";
import { computed, onBeforeUnmount, reactive, ref, watch } from "vue";
import ExchangeBadge from "@/components/ExchangeBadge.vue";
import { useExchangeStore } from "@/stores/exchangeStore";
import type { ExchangeAccount, ExchangeCreatePayload, ExchangeName } from "@/types/exchange";

const props = defineProps<{ open: boolean }>();

defineEmits<{
  (event: "close"): void;
}>();

const exchangeStore = useExchangeStore();

const form = reactive({
  exchange: "hyperliquid" as ExchangeName,
  name: "",
  is_testnet: false,
  wallet_address: "",
  agent_key: "",
  api_key: "",
  api_secret: "",
  passphrase: "",
});

const formError = ref("");
const confirmDeleteId = ref<string | null>(null);
const confirmDeactivate = ref(false);
const activatingId = ref<string | null>(null);
const validatingId = ref<string | null>(null);
const isAdding = ref(false);

const notice = ref({ message: "", type: "info" as "info" | "success" | "error" });
let noticeTimer: number | undefined;

const exchangeOptions = [
  {
    id: "hyperliquid" as ExchangeName,
    label: "Hyperliquid",
    short: "HL",
    hint: "Wallet + agent key",
  },
  {
    id: "binance" as ExchangeName,
    label: "Binance",
    short: "BN",
    hint: "API key + secret",
  },
  {
    id: "okx" as ExchangeName,
    label: "OKX",
    short: "OKX",
    hint: "API key + passphrase",
  },
];

const activeAccount = computed(() => exchangeStore.activeAccount);
const isBusy = computed(() => exchangeStore.isLoading || exchangeStore.isSaving);
const noticeClasses = computed(() => {
  if (notice.value.type === "success") {
    return "border-positive/40 bg-positive/10 text-positive";
  }
  if (notice.value.type === "error") {
    return "border-negative/40 bg-negative/10 text-negative";
  }
  return "border-border bg-panel/40 text-muted";
});

const refreshExchanges = async () => {
  const result = await exchangeStore.loadExchanges(true);
  if (!result.success) {
    setNotice(result.error || "Failed to refresh exchanges.", "error");
  }
};

const setNotice = (message: string, type: "info" | "success" | "error" = "info") => {
  notice.value = { message, type };
  if (noticeTimer) {
    window.clearTimeout(noticeTimer);
  }
  noticeTimer = window.setTimeout(() => {
    notice.value = { message: "", type: "info" };
  }, 4200);
};

const resetForm = () => {
  form.name = "";
  form.is_testnet = false;
  form.wallet_address = "";
  form.agent_key = "";
  form.api_key = "";
  form.api_secret = "";
  form.passphrase = "";
  formError.value = "";
};

const setExchangeType = (exchangeName: ExchangeName) => {
  form.exchange = exchangeName;
  form.wallet_address = "";
  form.agent_key = "";
  form.api_key = "";
  form.api_secret = "";
  form.passphrase = "";
  formError.value = "";
};

const handleAdd = async () => {
  formError.value = "";
  const accountName = form.name.trim();
  if (!accountName) {
    formError.value = "Account name is required.";
    return;
  }

  const payload: ExchangeCreatePayload = {
    exchange: form.exchange,
    name: accountName,
    is_testnet: form.is_testnet,
    credentials: {
      api_key: "",
      api_secret: "",
    },
  };

  if (form.exchange === "hyperliquid") {
    if (!form.wallet_address.trim()) {
      formError.value = "Wallet address is required for Hyperliquid.";
      return;
    }
    if (!form.agent_key.trim()) {
      formError.value = "Agent private key is required for Hyperliquid.";
      return;
    }
    payload.wallet_address = form.wallet_address.trim();
    // Backend requires non-empty api_key/api_secret; reuse wallet + agent key for Hyperliquid.
    payload.credentials = {
      api_key: form.wallet_address.trim(),
      api_secret: form.agent_key.trim(),
      agent_key: form.agent_key.trim(),
    };
  } else {
    if (!form.api_key.trim()) {
      formError.value = "API key is required.";
      return;
    }
    if (!form.api_secret.trim()) {
      formError.value = "API secret is required.";
      return;
    }
    payload.credentials = {
      api_key: form.api_key.trim(),
      api_secret: form.api_secret.trim(),
    };
    if (form.exchange === "okx") {
      if (!form.passphrase.trim()) {
        formError.value = "Passphrase is required for OKX.";
        return;
      }
      payload.credentials.passphrase = form.passphrase.trim();
    }
  }

  isAdding.value = true;
  const result = await exchangeStore.addExchange(payload);
  isAdding.value = false;
  if (result.success) {
    resetForm();
    setNotice(result.message || "Exchange added. Run validation to confirm access.", "success");
  } else {
    setNotice(result.error || "Failed to add exchange.", "error");
  }
};

const handleActivate = async (id: string) => {
  activatingId.value = id;
  const result = await exchangeStore.setActiveExchange(id);
  if (result.success) {
    setNotice(result.message || "Active exchange updated.", "success");
  } else {
    setNotice(result.error || "Failed to activate exchange.", "error");
  }
  activatingId.value = null;
};

const handleDeactivate = async () => {
  confirmDeactivate.value = false;
  const result = await exchangeStore.deactivateExchange();
  if (result.success) {
    setNotice(result.message || "Exchange deactivated.", "success");
  } else {
    setNotice(result.error || "Failed to deactivate exchange.", "error");
  }
};

const handleValidate = async (id: string) => {
  validatingId.value = id;
  const result = await exchangeStore.validateExchange(id);
  if (result.success) {
    setNotice(result.message || "Validation successful.", "success");
  } else {
    setNotice(result.error || "Validation failed.", "error");
  }
  validatingId.value = null;
};

const handleDelete = async (id: string) => {
  confirmDeleteId.value = null;
  const result = await exchangeStore.deleteExchange(id);
  if (result.success) {
    setNotice(result.message || "Exchange removed.", "success");
  } else {
    setNotice(result.error || "Failed to remove exchange.", "error");
  }
};

const formatTimestamp = (value?: string | null) => {
  if (!value) return "Never";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unknown";
  return date.toLocaleString();
};

const validationLabel = (account: ExchangeAccount) => {
  const status = account.validation?.status;
  if (status === "valid") return "Validated";
  if (status === "invalid") return "Invalid";
  return "Unvalidated";
};

const validationTone = (account: ExchangeAccount) => {
  const status = account.validation?.status;
  if (status === "valid") return "border-positive/40 bg-positive/10 text-positive";
  if (status === "invalid") return "border-negative/40 bg-negative/10 text-negative";
  return "border-warning/40 bg-warning/10 text-warning";
};

const formatWallet = (value?: string | null) => {
  if (!value) return "";
  if (value.length <= 10) return value;
  return `${value.slice(0, 6)}...${value.slice(-4)}`;
};

const exchangeLabel = (name: ExchangeName) => {
  if (name === "hyperliquid") return "Hyperliquid";
  if (name === "binance") return "Binance";
  if (name === "okx") return "OKX";
  return name;
};

const credentialBadges = (account: ExchangeAccount) => {
  if (account.exchange === "hyperliquid") {
    return [
      { label: account.wallet_address ? "Wallet linked" : "Wallet missing", ok: Boolean(account.wallet_address) },
      {
        label: account.credentials.agent_key ? "Agent key stored" : "Agent key missing",
        ok: Boolean(account.credentials.agent_key),
      },
    ];
  }

  const badges = [
    { label: account.credentials.api_key ? "API key stored" : "API key missing", ok: account.credentials.api_key },
    {
      label: account.credentials.api_secret ? "API secret stored" : "Secret missing",
      ok: account.credentials.api_secret,
    },
  ];

  if (account.exchange === "okx") {
    badges.push({
      label: account.credentials.passphrase ? "Passphrase stored" : "Passphrase missing",
      ok: account.credentials.passphrase,
    });
  }
  return badges;
};

watch(
  () => props.open,
  (value) => {
    if (value) {
      confirmDeleteId.value = null;
      confirmDeactivate.value = false;
      void exchangeStore.loadExchanges(true);
      notice.value = { message: "", type: "info" };
      formError.value = "";
    } else {
      resetForm();
    }
  },
);

onBeforeUnmount(() => {
  if (noticeTimer) {
    window.clearTimeout(noticeTimer);
  }
});
</script>
