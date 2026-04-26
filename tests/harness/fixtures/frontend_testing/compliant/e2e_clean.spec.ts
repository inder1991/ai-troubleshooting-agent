/* Q5 compliant — e2e file uses Playwright, not vitest.

Pretend-path: frontend/e2e/login.spec.ts
*/
import { test, expect } from "@playwright/test";

test("homepage", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveTitle(/DebugDuck/);
});
