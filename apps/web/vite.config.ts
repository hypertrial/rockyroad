import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const apiOrigin = process.env.ROCKYROAD_DEV_API_ORIGIN ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  optimizeDeps: {
    exclude: ["maplibre-gl"],
  },
  server: {
    port: 5173,
    proxy: {
      "/api": apiOrigin,
      "/maps": apiOrigin,
    },
  },
});
