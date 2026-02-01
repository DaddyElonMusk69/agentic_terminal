import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      "@": "/src",
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": "http://127.0.0.1:8001",
      "/socket.io": {
        target: "http://127.0.0.1:8001",
        ws: true,
      },
      "/realtime": {
        target: "http://127.0.0.1:8001",
        ws: true,
      },
    },
  },
  build: {
    outDir: "dist",
  },
});
