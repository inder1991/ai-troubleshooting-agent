/// <reference types="vitest" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    // Q18 — `@/...` alias resolution. Mirrors tsconfig.json.compilerOptions.paths.
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    // Close-out fix: Playwright specs live under e2e/ and use the
    // Playwright test runner, not vitest. Vitest's default include
    // picks them up and fails to load ("describe is not a function"
    // against @playwright/test), so explicitly exclude them. Also
    // exclude node_modules (default, but making it explicit guards
    // against future include overrides).
    exclude: ['node_modules/**', 'dist/**', 'e2e/**', '.idea', '.git', '.cache'],
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true
      }
    }
  }
});
