<template>
  <div class="flex min-h-0 flex-1 flex-col gap-4">
    <BaseCard>
      <div class="flex items-center justify-between">
        <div>
          <div class="text-xs uppercase tracking-wide text-muted">Telegram Notifications</div>
          <p class="mt-1 text-xs text-muted">Send alerts to users and groups.</p>
        </div>
        <label class="relative inline-flex cursor-pointer items-center">
          <input
            v-model="enabled"
            class="peer sr-only"
            type="checkbox"
            :disabled="isSaving"
          />
          <span
            class="h-5 w-10 rounded-full border border-border bg-panel transition peer-checked:bg-accent"
          ></span>
          <span
            class="absolute left-0.5 top-0.5 h-4 w-4 rounded-full bg-text transition peer-checked:translate-x-5"
          ></span>
        </label>
      </div>

      <div class="mt-4 space-y-4">
        <div>
          <div class="text-xs uppercase tracking-wide text-muted">Bot Token</div>
          <div class="mt-2 flex flex-wrap items-center gap-2">
            <input
              v-model="botTokenInput"
              class="min-w-[220px] flex-1 rounded-md border border-border bg-panel px-3 py-2 text-xs text-text"
              :type="showToken ? 'text' : 'password'"
              :placeholder="botTokenSet ? 'Configured' : 'Enter bot token'"
              autocomplete="off"
            />
            <button
              class="rounded-md border border-border bg-panel px-3 py-2 text-xs text-muted hover:text-text"
              type="button"
              @click="showToken = !showToken"
            >
              {{ showToken ? "Hide" : "Show" }}
            </button>
            <BaseBadge v-if="botTokenSet">Configured</BaseBadge>
          </div>
          <p class="mt-2 text-[11px] text-muted">Leave blank to keep the existing token.</p>
        </div>

        <div>
          <div class="text-xs uppercase tracking-wide text-muted">Recipients</div>
          <div class="mt-2 space-y-2">
            <div
              v-for="(recipient, index) in recipients"
              :key="recipient.chat_id"
              class="flex flex-wrap items-center gap-2 rounded-md border border-border bg-panel/50 p-2"
            >
              <label class="flex items-center gap-2 text-xs text-muted">
                <input v-model="recipient.enabled" type="checkbox" />
                Enabled
              </label>
              <div class="min-w-[140px] flex-1 text-xs text-text">
                <div class="font-medium">{{ recipient.name || 'Unnamed' }}</div>
                <div class="text-[11px] text-muted">{{ recipient.chat_id }}</div>
              </div>
              <select
                v-model="recipient.language"
                class="rounded-md border border-border bg-panel px-2 py-1 text-[11px] text-text"
              >
                <option v-for="(label, code) in supportedLanguages" :key="code" :value="code">
                  {{ label }}
                </option>
              </select>
              <button
                class="rounded-md border border-border bg-panel px-2 py-1 text-[11px] text-muted hover:text-negative"
                type="button"
                @click="removeRecipient(index)"
              >
                Remove
              </button>
            </div>
            <div v-if="recipients.length === 0" class="text-xs text-muted">
              No recipients configured.
            </div>
          </div>

          <div class="mt-3 grid gap-2 md:grid-cols-[1fr_1fr_auto]">
            <input
              v-model="newRecipientName"
              class="rounded-md border border-border bg-panel px-3 py-2 text-xs text-text"
              type="text"
              placeholder="Name"
            />
            <input
              v-model="newRecipientId"
              class="rounded-md border border-border bg-panel px-3 py-2 text-xs text-text"
              type="text"
              placeholder="Chat ID"
            />
            <button
              class="rounded-md border border-border bg-accent px-3 py-2 text-xs font-medium text-base"
              type="button"
              @click="addRecipient"
            >
              Add
            </button>
          </div>
          <p class="mt-2 text-[11px] text-muted">
            Use userinfobot on Telegram to retrieve user or group IDs.
          </p>
        </div>

        <div>
          <div class="text-xs uppercase tracking-wide text-muted">Notification Types</div>
          <div class="mt-2 grid gap-2 sm:grid-cols-2">
            <label class="flex items-center gap-2 text-xs text-muted">
              <input v-model="notifications.llm_considerations" type="checkbox" />
              AI Watchlist
            </label>
            <label class="flex items-center gap-2 text-xs text-muted">
              <input v-model="notifications.ema_automation" type="checkbox" />
              EMA Entry Alerts
            </label>
          </div>
        </div>

        <div class="flex flex-wrap items-center gap-2">
          <button
            class="rounded-md border border-border bg-panel px-3 py-2 text-xs text-muted hover:text-text"
            type="button"
            :disabled="isTesting"
            @click="testConnection"
          >
            {{ isTesting ? "Testing..." : "Test Connection" }}
          </button>
          <button
            class="rounded-md border border-border bg-accent px-3 py-2 text-xs font-medium text-base"
            type="button"
            :disabled="isSaving"
            @click="saveConfig"
          >
            {{ isSaving ? "Saving..." : "Save Configuration" }}
          </button>
          <span v-if="statusMessage" class="text-xs" :class="statusToneClass">
            {{ statusMessage }}
          </span>
        </div>
      </div>
    </BaseCard>

    <BaseCard>
      <div class="flex items-start justify-between gap-3">
        <div>
          <div class="text-xs uppercase tracking-wide text-muted">Chart Snapshot Hosting</div>
          <p class="mt-1 text-xs text-muted">
            Select where chart snapshots are hosted.
          </p>
        </div>
        <BaseBadge>{{ imageHostConfigured ? "Configured" : "Missing" }}</BaseBadge>
      </div>

      <div class="mt-4 space-y-3">
        <label class="text-[11px] text-muted">
          Provider
          <div class="mt-2 flex flex-wrap items-center gap-2">
            <select
              v-model="imageHostProvider"
              class="rounded-md border border-border bg-panel px-3 py-2 text-xs text-text"
            >
              <option v-for="option in imageHostOptions" :key="option.value" :value="option.value">
                {{ option.label }}
              </option>
            </select>
          </div>
          <p class="mt-2 text-[11px] text-muted">
            Filesystem keeps snapshots on the backend server.
          </p>
        </label>

        <label v-if="requiresImageHostKey" class="text-[11px] text-muted">
          API Key
          <div class="mt-2 flex flex-wrap items-center gap-2">
            <input
              v-model="imageHostKeyInput"
              class="min-w-[220px] flex-1 rounded-md border border-border bg-panel px-3 py-2 text-xs text-text"
              :type="showImgKey ? 'text' : 'password'"
              :placeholder="imageHostKeyPresent ? 'Configured' : 'Enter API key'"
              autocomplete="off"
            />
            <button
              class="rounded-md border border-border bg-panel px-3 py-2 text-xs text-muted hover:text-text"
              type="button"
              @click="showImgKey = !showImgKey"
            >
              {{ showImgKey ? "Hide" : "Show" }}
            </button>
          </div>
        </label>

        <div class="flex flex-wrap items-center gap-2">
          <button
            class="rounded-md border border-border bg-accent px-3 py-2 text-xs font-medium text-base"
            type="button"
            :disabled="isSavingImgKey"
            @click="saveImageHostConfig"
          >
            {{ isSavingImgKey ? "Saving..." : "Save Hosting" }}
          </button>
          <span v-if="imageHostStatusMessage" class="text-xs" :class="imageHostStatusToneClass">
            {{ imageHostStatusMessage }}
          </span>
        </div>
      </div>
    </BaseCard>

    <div v-if="error" class="text-xs text-negative">
      {{ error }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import BaseBadge from "@/components/BaseBadge.vue";
import BaseCard from "@/components/BaseCard.vue";

type Recipient = {
  chat_id: string;
  name: string;
  enabled: boolean;
  language: string;
};

type NotificationsConfig = {
  llm_considerations: boolean;
  ema_automation: boolean;
};

const enabled = ref(false);
const botTokenSet = ref(false);
const botTokenInput = ref("");
const showToken = ref(false);
const recipients = ref<Recipient[]>([]);
const supportedLanguages = ref<Record<string, string>>({});
const notifications = reactive<NotificationsConfig>({
  llm_considerations: false,
  ema_automation: true,
});
const newRecipientName = ref("");
const newRecipientId = ref("");
const statusMessage = ref("");
const statusTone = ref<"info" | "success" | "error">("info");
const error = ref("");
const isSaving = ref(false);
const isTesting = ref(false);
const fallbackChatId = ref("");
const imageHostProvider = ref("filesystem");
const imageHostKeyInput = ref("");
const imageHostKeyPresent = ref(false);
const showImgKey = ref(false);
const isSavingImgKey = ref(false);
const imageHostStatusMessage = ref("");
const imageHostStatusTone = ref<"info" | "success" | "error">("info");

const imageHostOptions = [
  { value: "filesystem", label: "Filesystem (local)" },
  { value: "imgbb", label: "ImgBB" },
  { value: "freeimage", label: "freeimage.host" },
];

const statusToneClass = computed(() => {
  if (statusTone.value === "success") return "text-positive";
  if (statusTone.value === "error") return "text-negative";
  return "text-muted";
});

const imageHostStatusToneClass = computed(() => {
  if (imageHostStatusTone.value === "success") return "text-positive";
  if (imageHostStatusTone.value === "error") return "text-negative";
  return "text-muted";
});

const requiresImageHostKey = computed(
  () => imageHostProvider.value !== "filesystem",
);

const imageHostConfigured = computed(() => {
  if (imageHostProvider.value === "filesystem") return true;
  return imageHostKeyPresent.value;
});

const setStatus = (message: string, tone: "info" | "success" | "error" = "info") => {
  statusMessage.value = message;
  statusTone.value = tone;
  window.setTimeout(() => {
    if (statusMessage.value === message) statusMessage.value = "";
  }, 5000);
};

const setImageHostStatus = (message: string, tone: "info" | "success" | "error" = "info") => {
  imageHostStatusMessage.value = message;
  imageHostStatusTone.value = tone;
  window.setTimeout(() => {
    if (imageHostStatusMessage.value === message) imageHostStatusMessage.value = "";
  }, 4000);
};

const loadConfig = async () => {
  error.value = "";
  try {
    const response = await fetch("/api/v1/integrations/telegram");
    const data = await response.json();
    if (!response.ok || !data?.data) {
      throw new Error(data?.error?.message || "Failed to load Telegram config.");
    }
    const config = data.data || {};
    enabled.value = Boolean(config.enabled);
    botTokenSet.value = Boolean(config.bot_token_set);
    fallbackChatId.value = config.chat_id || "";
    recipients.value = Array.isArray(config.recipients)
      ? config.recipients.map((recipient: Recipient) => ({
          chat_id: recipient.chat_id,
          name: recipient.name || `User ${String(recipient.chat_id).slice(-4)}`,
          enabled: recipient.enabled !== false,
          language: recipient.language || "en",
        }))
      : [];
    supportedLanguages.value = config.supported_languages || { en: "English" };
    const nextNotifications = config.notifications || {};
    notifications.llm_considerations = Boolean(nextNotifications.llm_considerations);
    notifications.ema_automation = nextNotifications.ema_automation !== false;
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Failed to load Telegram config.";
  }
};

const addRecipient = () => {
  const name = newRecipientName.value.trim();
  const chatId = newRecipientId.value.trim();
  if (!chatId) {
    setStatus("Chat ID is required.", "error");
    return;
  }
  if (recipients.value.some((item) => item.chat_id === chatId)) {
    setStatus("Recipient already exists.", "error");
    return;
  }
  recipients.value.push({
    chat_id: chatId,
    name: name || `User ${chatId.slice(-4)}`,
    enabled: true,
    language: "en",
  });
  newRecipientName.value = "";
  newRecipientId.value = "";
};

const removeRecipient = (index: number) => {
  recipients.value.splice(index, 1);
};

const testConnection = async () => {
  isTesting.value = true;
  try {
    const testRecipient = recipients.value.find((item) => item.enabled)?.chat_id || fallbackChatId.value;
    const response = await fetch("/api/v1/integrations/telegram/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        bot_token: botTokenInput.value.trim() || undefined,
        chat_id: testRecipient || undefined,
        send_test_message: true,
      }),
    });
    const data = await response.json();
    if (!response.ok || !data?.data?.sent) {
      throw new Error(data?.error?.message || "Test failed.");
    }
    setStatus("Telegram connection verified.", "success");
  } catch (err) {
    setStatus(err instanceof Error ? err.message : "Test failed.", "error");
  } finally {
    isTesting.value = false;
  }
};

const saveConfig = async () => {
  isSaving.value = true;
  try {
    const payload: Record<string, unknown> = {
      enabled: enabled.value,
      recipients: recipients.value,
      notifications: {
        signal_open: false,
        signal_change: false,
        signal_close: false,
        llm_considerations: notifications.llm_considerations,
        ema_automation: notifications.ema_automation,
      },
      chat_id: fallbackChatId.value,
    };

    if (botTokenInput.value.trim()) {
      payload.bot_token = botTokenInput.value.trim();
    }

    const response = await fetch("/api/v1/integrations/telegram", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data?.error?.message || "Failed to save Telegram config.");
    }
    if (botTokenInput.value.trim()) {
      botTokenSet.value = true;
      botTokenInput.value = "";
    }
    setStatus("Configuration saved.", "success");
  } catch (err) {
    setStatus(err instanceof Error ? err.message : "Failed to save configuration.", "error");
  } finally {
    isSaving.value = false;
  }
};

const loadImageHostConfig = async () => {
  try {
    const response = await fetch("/api/v1/integrations/image-uploader");
    const data = await response.json();
    if (!data?.data) {
      throw new Error(data?.error?.message || "Failed to load image host config.");
    }
    imageHostProvider.value = data.data.provider || "filesystem";
    imageHostKeyPresent.value = Boolean(data.data.api_key_present);
  } catch (err) {
    setImageHostStatus(
      err instanceof Error ? err.message : "Failed to load image host config.",
      "error",
    );
  }
};

const saveImageHostConfig = async () => {
  const key = imageHostKeyInput.value.trim();
  if (requiresImageHostKey.value && !key && !imageHostKeyPresent.value) {
    setImageHostStatus("API key is required.", "error");
    return;
  }
  isSavingImgKey.value = true;
  try {
    const payload: Record<string, unknown> = { provider: imageHostProvider.value };
    if (key) {
      payload.api_key = key;
    }
    const response = await fetch("/api/v1/integrations/image-uploader", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data?.error?.message || "Failed to save image host.");
    }
    imageHostProvider.value = data.data.provider || imageHostProvider.value;
    imageHostKeyPresent.value = Boolean(data.data.api_key_present);
    imageHostKeyInput.value = "";
    setImageHostStatus("Image host saved.", "success");
  } catch (err) {
    setImageHostStatus(err instanceof Error ? err.message : "Failed to save image host.", "error");
  } finally {
    isSavingImgKey.value = false;
  }
};

onMounted(() => {
  loadConfig();
  loadImageHostConfig();
});
</script>
