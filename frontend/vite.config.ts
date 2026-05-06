import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // 동일 접두사 `/api` 로 백엔드 연결(CORS 불필요) — 저장소 기본 리슨 18000
      "/api": {
        target: "http://127.0.0.1:18000",
        changeOrigin: true,
      },
    },
  },
});
