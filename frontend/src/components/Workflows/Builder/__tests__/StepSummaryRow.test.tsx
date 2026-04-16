import { describe, expect, test, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { StepSummaryRow } from '../StepSummaryRow';
import type { StepSpec, PredicateExpr } from '../../../../types';

function makeStep(over: Partial<StepSpec> = {}): StepSpec {
  return {
    id: 'step1',
    agent: 'log_analyzer',
    agent_version: 1,
    inputs: {},
    ...over,
  };
}

describe('StepSummaryRow', () => {
  test('renders index, id, and agent@version', () => {
    render(
      <StepSummaryRow
        step={makeStep()}
        index={0}
        active={false}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByText('step1')).toBeInTheDocument();
    expect(screen.getByText(/log_analyzer@1/i)).toBeInTheDocument();
    // Index shown as 1-based
    expect(screen.getByText('1')).toBeInTheDocument();
  });

  test('shows trigger summary when "when" is set', () => {
    const expr = {
      op: 'eq',
      args: [
        { ref: { from: 'input', path: 'color' } },
        { literal: 'red' },
      ],
    } as unknown as PredicateExpr;
    render(
      <StepSummaryRow
        step={makeStep({ when: expr })}
        index={0}
        active={false}
        onSelect={vi.fn()}
      />,
    );
    expect(
      screen.getByText(/if input\.color == "red"/i),
    ).toBeInTheDocument();
  });

  test('omits trigger summary when "when" is absent', () => {
    render(
      <StepSummaryRow
        step={makeStep()}
        index={0}
        active={false}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.queryByText(/^if /)).not.toBeInTheDocument();
  });

  test('continue on failure shows "continue" label', () => {
    render(
      <StepSummaryRow
        step={makeStep({ on_failure: 'continue' })}
        index={0}
        active={false}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByText(/continue/i)).toBeInTheDocument();
  });

  test('fallback on failure shows fallback:<id>', () => {
    render(
      <StepSummaryRow
        step={makeStep({ on_failure: 'fallback', fallback_step_id: 'alt1' })}
        index={0}
        active={false}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByText(/fallback:alt1/i)).toBeInTheDocument();
  });

  test('default "fail" on_failure is hidden', () => {
    render(
      <StepSummaryRow
        step={makeStep({ on_failure: 'fail' })}
        index={0}
        active={false}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.queryByText(/^fail$/i)).not.toBeInTheDocument();
  });

  test('concurrency_group pill shown when set', () => {
    render(
      <StepSummaryRow
        step={makeStep({ concurrency_group: 'db-writes' })}
        index={0}
        active={false}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByText(/db-writes/)).toBeInTheDocument();
  });

  test('timeout pill shown as <n>s', () => {
    render(
      <StepSummaryRow
        step={makeStep({ timeout_seconds_override: 30 })}
        index={0}
        active={false}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByText('30s')).toBeInTheDocument();
  });

  test('error badge shows count when errors present', () => {
    render(
      <StepSummaryRow
        step={makeStep()}
        index={0}
        active={false}
        onSelect={vi.fn()}
        errors={[
          { path: 'steps[0].id', message: 'bad' },
          { path: 'steps[0].agent', message: 'bad' },
        ]}
      />,
    );
    expect(screen.getByLabelText(/2 errors?/i)).toBeInTheDocument();
  });

  test('no error badge when errors is empty/undefined', () => {
    render(
      <StepSummaryRow
        step={makeStep()}
        index={0}
        active={false}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.queryByLabelText(/error/i)).not.toBeInTheDocument();
  });

  test('row is a button and calls onSelect when clicked', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(
      <StepSummaryRow
        step={makeStep()}
        index={0}
        active={false}
        onSelect={onSelect}
      />,
    );
    await user.click(screen.getByRole('button', { name: /step1/i }));
    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  test('active state sets aria-current="true"', () => {
    render(
      <StepSummaryRow
        step={makeStep()}
        index={0}
        active={true}
        onSelect={vi.fn()}
      />,
    );
    const btn = screen.getByRole('button', { name: /step1/i });
    expect(btn).toHaveAttribute('aria-current', 'true');
  });
});
