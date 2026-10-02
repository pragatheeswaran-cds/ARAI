/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The UI calls the API on its own origin. In development Vite forwards /api to the local API process.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": process.env.ARAI_API ?? "http://127.0.0.1:8000" } },
  test: { environment: "jsdom", globals: true, setupFiles: ["src/test-setup.ts"], css: false },
});
