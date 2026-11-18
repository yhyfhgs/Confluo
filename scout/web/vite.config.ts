import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In development the API runs on the host (`uv run scout serve --port 8771`).
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": { target: "http://127.0.0.1:8771", changeOrigin: false } } },
  build: { outDir: "dist", sourcemap: false, chunkSizeWarningLimit: 600 },
});
