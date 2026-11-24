/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const backend = process.env.CS_BACKEND_URL ?? "http://127.0.0.1:8420";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": backend } },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    globals: true,
    css: false,
  },
});
