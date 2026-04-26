/// <reference types="vitest" />
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";

// Q5 — Vitest for unit/integration. Per-path hard coverage gate:
//   services/api/ ≥ 90%   (the contract layer; silent breakage = bugs)
//   hooks/        ≥ 85%   (the orchestrators)
// Other paths report coverage but don't gate.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    // Q5: e2e tests live under frontend/e2e/ and are run by Playwright.
    // Vitest must not pick them up.
    exclude: [
      "node_modules/**",
      "dist/**",
      "e2e/**",
      ".idea",
      ".git",
      ".cache",
    ],
    coverage: {
      provider: "v8",
      reporter: ["text", "json", "html"],
      // Locked Q5 path-targeted thresholds. Files outside these globs
      // still report coverage but don't gate.
      thresholds: {
        "frontend/src/services/api/**": {
          branches: 0.9,
          functions: 0.9,
          lines: 0.9,
          statements: 0.9,
        },
        "frontend/src/hooks/**": {
          branches: 0.85,
          functions: 0.85,
          lines: 0.85,
          statements: 0.85,
        },
      },
    },
  },
});
