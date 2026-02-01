import { createRouter, createWebHistory } from "vue-router";
import EmaScannerView from "@/views/scanner/EmaScannerView.vue";
import QuantScannerView from "@/views/scanner/QuantScannerView.vue";
import AgentView from "@/views/agent/AgentView.vue";
import AutomationView from "@/views/automation/AutomationView.vue";
import SettingsView from "@/views/settings/SettingsView.vue";
import BusQueueMonitorView from "@/views/observability/BusQueueMonitorView.vue";

const routes = [
  { path: "/", redirect: "/scanner/ema" },
  { path: "/scanner/ema", name: "scanner-ema", component: EmaScannerView },
  { path: "/scanner/quant", name: "scanner-quant", component: QuantScannerView },
  { path: "/agent", name: "agent", component: AgentView },
  { path: "/automation", name: "automation", component: AutomationView },
  { path: "/observability", name: "observability", component: BusQueueMonitorView },
  { path: "/settings", name: "settings", component: SettingsView },
];

export const router = createRouter({
  history: createWebHistory(),
  routes,
});
