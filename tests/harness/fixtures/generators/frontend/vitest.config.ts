import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    coverage: {
      thresholds: {
        "frontend/src/services/api/**": { lines: 0.9, functions: 0.9, branches: 0.85, statements: 0.9 },
        "frontend/src/hooks/**": { lines: 0.85, functions: 0.85, branches: 0.8, statements: 0.85 },
      },
    },
  },
});
