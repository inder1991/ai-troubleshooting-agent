/* Q5 violation — Playwright import in unit test (must live under frontend/e2e/). */
import { test, expect } from "@playwright/test";

test("x", async ({ page }) => {
  expect(page).toBeTruthy();
});
