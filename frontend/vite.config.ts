import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
      "/stel": { target: "http://localhost:8000", changeOrigin: true },
      "/stel-cdn": { target: "http://localhost:8000", changeOrigin: true },
      "/stel-data": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
});
