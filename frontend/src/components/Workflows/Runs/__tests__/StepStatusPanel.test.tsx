import { describe, expect, test, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { StepStatusPanel } from '../StepStatusPanel';
import type { LiveEvent } from '../StepStatusPanel';
import type { StepRunDetail, StepRunStatus } from '../../../../types';

function makeStep(overrides: Partial<StepRunDetail> = {}): StepRunDetail {
  return {
    id: 'sr-1',
    step_id: 'step-a',
    status: 'pending',
    attempt: 1,
    ...overrides,
  };
}

describe('StepStatusPanel', () => {
  test('renders one card per stepRun', () => {
    const steps: StepRunDetail[] = [
      makeStep({ id: 'sr-1', step_id: 'step-a' }),
      makeStep({ id: 'sr-2', step_id: 'step-b' }),
      makeStep({ id: 'sr-3', step_id: 'step-c' }),
    ];
    render(<StepStatusPanel stepRuns={steps} />);
    expect(screen.getByText('step-a')).toBeInTheDocument();
    expect(screen.getByText('step-b')).toBeInTheDocument();
    expect(screen.getByText('step-c')).toBeInTheDocument();
  });

  test('status badge shows correct color class for each status', () => {
    const statuses: Array<{ status: StepRunStatus; expectedClass: string }> = [
      { status: 'running', expectedClass: 'bg-amber' },
      { status: 'success', expectedClass: 'bg-emerald' },
      { status: 'failed', expectedClass: 'bg-red' },
      { status: 'skipped', expectedClass: 'bg-neutral' },
      { status: 'cancelled', expectedClass: 'bg-slate' },
      { status: 'pending', expectedClass: 'bg-neutral' },
    ];

    for (const { status, expectedClass } of statuses) {
      const { unmount } = render(
        <StepStatusPanel stepRuns={[makeStep({ id: `sr-${status}`, step_id: `step-${status}`, status })]} />,
      );
      const badge = screen.getByTestId(`status-badge-step-${status}`);
      const classes = badge.className;
      expect(classes).toContain(expectedClass);
      unmount();
    }
  });

  test('running step shows pulse animation', () => {
    render(
      <StepStatusPanel stepRuns={[makeStep({ status: 'running', step_id: 'run-step' })]} />,
    );
    const badge = screen.getByTestId('status-badge-run-step');
    expect(badge.className).toContain('animate-pulse');
  });

  test('failed step shows error message', () => {
    render(
      <StepStatusPanel
        stepRuns={[
          makeStep({
            status: 'failed',
            step_id: 'fail-step',
            error: { type: 'RuntimeError', message: 'something broke' },
          }),
        ]}
      />,
    );
    expect(screen.getByText(/something broke/)).toBeInTheDocument();
  });

  test('expandable output: click "Show output" renders JSON', async () => {
    const user = userEvent.setup();
    render(
      <StepStatusPanel
        stepRuns={[
          makeStep({
            status: 'success',
            step_id: 'out-step',
            output: { result: 42 },
          }),
        ]}
      />,
    );
    // Output should not be visible initially
    expect(screen.queryByText(/"result"/)).not.toBeInTheDocument();

    const btn = screen.getByRole('button', { name: /show output/i });
    await user.click(btn);

    expect(screen.getByText(/"result"/)).toBeInTheDocument();
    expect(screen.getByText(/42/)).toBeInTheDocument();
  });

  test('step card responds to Enter key when clickable', async () => {
    const onClick = vi.fn();
    const user = userEvent.setup();
    render(
      <StepStatusPanel
        stepRuns={[makeStep({ step_id: 'kb-step' })]}
        onCardClick={onClick}
      />,
    );
    const card = screen.getByTestId('step-card-kb-step');
    card.focus();
    await user.keyboard('{Enter}');
    expect(onClick).toHaveBeenCalledWith('kb-step');
  });

  test('step card responds to Space key when clickable', async () => {
    const onClick = vi.fn();
    const user = userEvent.setup();
    render(
      <StepStatusPanel
        stepRuns={[makeStep({ step_id: 'sp-step' })]}
        onCardClick={onClick}
      />,
    );
    const card = screen.getByTestId('step-card-sp-step');
    card.focus();
    await user.keyboard(' ');
    expect(onClick).toHaveBeenCalledWith('sp-step');
  });

  test('step card has role="button" when clickable', () => {
    render(
      <StepStatusPanel
        stepRuns={[makeStep({ step_id: 'role-step' })]}
        onCardClick={vi.fn()}
      />,
    );
    expect(screen.getByTestId('step-card-role-step')).toHaveAttribute('role', 'button');
  });

  test('step card has no role when not clickable', () => {
    render(
      <StepStatusPanel stepRuns={[makeStep({ step_id: 'norole-step' })]} />,
    );
    expect(screen.getByTestId('step-card-norole-step')).not.toHaveAttribute('role');
  });

  test('LiveEvent overlays: pending step + step.started event → running', () => {
    const events: LiveEvent[] = [
      {
        id: 1,
        type: 'step.started',
        data: { step_id: 'step-x', status: 'running', attempt: 1 },
        timestamp: new Date().toISOString(),
      },
    ];
    render(
      <StepStatusPanel
        stepRuns={[makeStep({ step_id: 'step-x', status: 'pending' })]}
        liveEvents={events}
      />,
    );
    const badge = screen.getByTestId('status-badge-step-x');
    expect(badge.className).toContain('bg-amber');
    expect(badge.className).toContain('animate-pulse');
  });
});
