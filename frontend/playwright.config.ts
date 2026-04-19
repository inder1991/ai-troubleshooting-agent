import { defineConfig, devices } from '@playwright/test';

/**
 * War Room test harness (PR 7)
 *
 * Extends the baseline Playwright config with multi-viewport projects
 * so visual-regression + layout specs run at 1024, 1280, 1440, 1920,
 * and 2560 — the five widths declared in the redesign invariants.
 * The original chromium project retains the default viewport for the
 * existing workflows spec.
 *
 * Visual-regression snapshots live under
 *   e2e/__screenshots__/<spec-name>/<test-name>-<project>.png
 * The compare threshold is tuned loose enough to survive antialias
 * drift across hosts but tight enough to catch layout regressions.
 */

const WARROOM_VIEWPORTS = [
  { name: 'warroom-1024', width: 1024, height: 768 },
  { name: 'warroom-1280', width: 1280, height: 800 },
  { name: 'warroom-1440', width: 1440, height: 900 },
  { name: 'warroom-1920', width: 1920, height: 1080 },
  { name: 'warroom-2560', width: 2560, height: 1440 },
];

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  expect: {
    timeout: 10_000,
    toHaveScreenshot: {
      maxDiffPixelRatio: 0.02,
      animations: 'disabled',
    },
  },
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: 'html',
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
  },
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
  projects: [
    // Original project — runs the existing workflows spec.
    { name: 'chromium', use: { browserName: 'chromium' } },
    // War Room multi-viewport projects. Each runs the layout + a11y
    // + overlap specs at the named width so the 1024–2560 invariant
    // is enforced at every PR.
    ...WARROOM_VIEWPORTS.map((vp) => ({
      name: vp.name,
      testMatch: /warroom\..+\.spec\.ts/,
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: vp.width, height: vp.height },
      },
    })),
  ],
});
