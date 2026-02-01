<template>
  <AppShell>
    <RouterView v-slot="{ Component }">
      <KeepAlive include="AutomationView">
        <component :is="Component" />
      </KeepAlive>
    </RouterView>
  </AppShell>
</template>

<script setup lang="ts">
import { RouterView } from "vue-router";
import AppShell from "@/layouts/AppShell.vue";
</script>
