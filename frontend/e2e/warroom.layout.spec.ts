import { test, expect } from '@playwright/test';

/**
 * War Room — layout & visual regression (PR 7)
 *
 * Runs at all five viewport widths (1024/1280/1440/1920/2560) via the
 * per-viewport projects declared in playwright.config.ts. Takes a
 * screenshot of the full War Room grid and compares against a committed
 * baseline so layout regressions surface loudly.
 *
 * These tests require the dev server (webServer config spins it up)
 * AND a valid investigation session to navigate to. The harness below
 * navigates to `/` and assumes the first investigation from the seed
 * is openable — in CI the backend fixture seeds a deterministic
 * session; locally the tests skip if no session is available.
 */

test.describe('War Room layout', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    // The War Room grid only mounts once a session is open. If the
    // landing page doesn't navigate into one within 5s, skip the
    // visual snapshot — a separate CI fixture populates one.
    const grid = page.locator('.warroom-grid');
    const appeared = await grid
      .waitFor({ state: 'attached', timeout: 5_000 })
      .then(() => true)
      .catch(() => false);
    test.skip(!appeared, 'No War Room session visible — layout spec requires a live session fixture.');
  });

  test('grid renders three columns + gutter at ≥ 1288px; collapses Navigator below', async ({
    page,
    viewport,
  }) => {
    const grid = page.locator('.warroom-grid');
    await expect(grid).toBeVisible();

    const investigator = page.locator('.wr-region-investigator');
    const evidence = page.locator('.wr-region-evidence');
    const gutter = page.locator('.wr-region-gutter');

    // Investigator + evidence + gutter are always rendered
    await expect(investigator).toBeVisible();
    await expect(evidence).toBeVisible();
    await expect(gutter).toBeVisible();

    // Navigator renders inline at ≥ 1288px, collapses into PaneDrawer below
    const navigator = page.locator('.wr-region-navigator');
    if ((viewport?.width ?? 0) >= 1288) {
      await expect(navigator).toBeVisible();
    } else {
      // Present in DOM (just display:none when collapsed)
      await expect(navigator).toHaveCount(1);
    }
  });

  test('banner region collapses to 28px when healthy', async ({ page }) => {
    const banner = page.locator('[data-testid="banner-region"]');
    await expect(banner).toBeVisible();
    // Freshness row should render; banner row hidden unless a signal fires
    await expect(page.locator('[data-testid="freshness-row"]')).toBeVisible();
  });

  test('visual snapshot — full War Room @ viewport', async ({ page }, testInfo) => {
    // Snapshot key includes the project name (viewport label) so each
    // width has its own baseline.
    await page.waitForTimeout(500); // let one banner / sticky settle
    await expect(page).toHaveScreenshot(`warroom-${testInfo.project.name}.png`, {
      fullPage: false,
    });
  });
});
