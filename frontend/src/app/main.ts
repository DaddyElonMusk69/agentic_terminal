import { createApp } from "vue";
import App from "./App.vue";
import { router } from "./router";
import { pinia } from "./pinia";
import { useSettingsStore } from "@/stores/settingsStore";
import "@/styles/index.css";

const app = createApp(App).use(pinia).use(router);

useSettingsStore(pinia).initializeTheme();

app.mount("#app");
