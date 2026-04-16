import { test, expect } from '@playwright/test';

/**
 * E2E smoke test for the Workflow Builder flow.
 *
 * Requires the backend running with:
 *   WORKFLOWS_ENABLED=true WORKFLOW_RUNNERS_STUB=true
 *
 * The stub runner echoes inputs back, so every step succeeds deterministically.
 */
test.describe('Workflow builder smoke', () => {
  test('create workflow, add steps, save, run, verify success', async ({
    page,
  }) => {
    // ----------------------------------------------------------------
    // 1. Navigate to workflows list
    // ----------------------------------------------------------------
    await page.goto('/workflows');
    await expect(
      page.getByRole('heading', { name: 'Workflows' }),
    ).toBeVisible();

    // ----------------------------------------------------------------
    // 2. Create workflow "Smoke"
    // ----------------------------------------------------------------
    await page.getByTestId('create-workflow-btn').click();
    await page.getByTestId('wf-name-input').fill('Smoke');
    await page.getByTestId('wf-create-submit').click();

    // Wait for navigation to builder page
    await page.waitForURL(/\/workflows\/[^/]+$/);
    await expect(
      page.getByRole('heading', { name: 'Smoke' }),
    ).toBeVisible();

    // ----------------------------------------------------------------
    // 3. Add step A — log_agent v1
    // ----------------------------------------------------------------
    await page.getByTestId('add-step-btn').click();
    await page.getByTestId('agent-option-log_agent').click();

    // The first step should now appear in the step list
    const stepList = page.getByTestId('step-list');
    const stepRows = stepList.getByTestId('step-row');
    await expect(stepRows).toHaveCount(1);

    // Click the step to open the drawer
    await stepRows.first().click();
    await expect(page.getByTestId('step-drawer')).toBeVisible();

    // Verify agent is log_agent in the Agent section
    const agentSelect = page.getByLabel('Select Agent');
    await expect(agentSelect).toHaveValue('log_agent');

    // ----------------------------------------------------------------
    // 4. Add step B — log_agent v1 (second step)
    // ----------------------------------------------------------------
    // Close drawer first by clicking outside or the close button
    await page.getByLabel('Close').click();

    await page.getByTestId('add-step-btn').click();
    await page.getByTestId('agent-option-log_agent').click();

    // Should now have 2 steps
    await expect(stepRows).toHaveCount(2);

    // Click step B to open its drawer
    await stepRows.nth(1).click();
    await expect(page.getByTestId('step-drawer')).toBeVisible();

    // If the Inputs section has fields, we could switch one to "Node"
    // mode to reference step A's output. For now, just verify the drawer
    // opened for step B.
    await expect(agentSelect).toHaveValue('log_agent');

    // Close the drawer
    await page.getByLabel('Close').click();

    // ----------------------------------------------------------------
    // 5. Save — version 1 created
    // ----------------------------------------------------------------
    await page.getByTestId('save-btn').click();

    // Wait for the success banner
    await expect(page.getByTestId('save-success-banner')).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByTestId('save-success-banner')).toHaveText(
      'Version saved successfully',
    );

    // ----------------------------------------------------------------
    // 6. Run — fill inputs — submit
    // ----------------------------------------------------------------
    await page.getByTestId('run-btn').click();

    // The InputsForm modal should appear
    await expect(page.getByTestId('inputs-form-modal')).toBeVisible();

    // If the schema has no required fields, the Run button in the modal
    // should be enabled. Click it.
    const runSubmitBtn = page.getByRole('button', { name: 'Run workflow' });
    await expect(runSubmitBtn).toBeVisible();
    await runSubmitBtn.click();

    // ----------------------------------------------------------------
    // 7. Assert steps reach SUCCESS on RunDetailPage
    // ----------------------------------------------------------------
    // Should navigate to /workflows/runs/:runId
    await page.waitForURL(/\/workflows\/runs\/[^/]+$/, {
      timeout: 15_000,
    });

    // Wait for the run status badge to show "succeeded"
    const runStatusBadge = page.getByTestId('run-status-badge');
    await expect(runStatusBadge).toBeVisible({ timeout: 30_000 });

    // The stub runner completes near-instantly, so wait for "succeeded"
    await expect(runStatusBadge).toHaveText('succeeded', {
      timeout: 30_000,
    });

    // Verify individual step status badges show "success"
    // Step IDs are auto-generated (e.g. "log_agent_1", "log_agent_2")
    // so we look for any status badges with "success" text.
    const stepBadges = page.locator('[data-testid^="status-badge-"]');
    const count = await stepBadges.count();
    expect(count).toBeGreaterThanOrEqual(2);

    for (let i = 0; i < count; i++) {
      await expect(stepBadges.nth(i)).toHaveText('success', {
        timeout: 15_000,
      });
    }
  });
});
