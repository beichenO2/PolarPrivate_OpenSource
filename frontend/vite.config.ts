import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ command }) => ({
  base: command === "build" ? (process.env.VITE_BASE_PATH || "/") : "/",
  plugins: [react()],
  preview: { allowedHosts: ["128gb.banteng-edmontosaurus.ts.net"] },
  server: {
    host: "127.0.0.1",
    port: 12795,
    strictPort: true,
    allowedHosts: true,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:12790",
        changeOrigin: true,
      },
      "/proxy": {
        target: "http://127.0.0.1:12790",
        changeOrigin: true,
      },
      "/health": {
        target: "http://127.0.0.1:12790",
        changeOrigin: true,
      },
    },
  },
}));
