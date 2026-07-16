import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ command }) => {
  const frontendPort = Number(process.env.POLARPRIVATE_FRONTEND_PORT || 12795);
  const backendUrl = process.env.POLARPRIVATE_BACKEND_URL || "http://127.0.0.1:12790";

  return {
    base: command === "build" ? (process.env.VITE_BASE_PATH || "/") : "/",
    plugins: [react()],
    preview: { allowedHosts: ["128gb.banteng-edmontosaurus.ts.net"] },
    server: {
      host: "127.0.0.1",
      port: frontendPort,
      strictPort: true,
      allowedHosts: true,
      proxy: {
        "/api": {
          target: backendUrl,
          changeOrigin: true,
        },
        "/proxy": {
          target: backendUrl,
          changeOrigin: true,
        },
        "/health": {
          target: backendUrl,
          changeOrigin: true,
        },
      },
    },
  };
});
