import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { VersionDiff } from '../VersionDiff';
import type { StepSpec } from '../../../../types';

function makeStep(overrides: Partial<StepSpec> & { id: string }): StepSpec {
  return { agent: 'log_agent', agent_version: 1, inputs: {}, ...overrides };
}

describe('VersionDiff', () => {
  it('shows added steps in green', () => {
    render(<VersionDiff oldSteps={[]} newSteps={[makeStep({ id: 'new_step' })]} />);
    const row = screen.getByTestId('diff-row-new_step');
    expect(row.className).toContain('green');
    expect(screen.getByText('Added')).toBeInTheDocument();
  });

  it('shows removed steps in red', () => {
    render(<VersionDiff oldSteps={[makeStep({ id: 'old_step' })]} newSteps={[]} />);
    const row = screen.getByTestId('diff-row-old_step');
    expect(row.className).toContain('red');
    expect(screen.getByText('Removed')).toBeInTheDocument();
  });

  it('shows modified steps in amber when agent differs', () => {
    render(<VersionDiff
      oldSteps={[makeStep({ id: 's1', agent: 'log_agent' })]}
      newSteps={[makeStep({ id: 's1', agent: 'metrics_agent' })]}
    />);
    const row = screen.getByTestId('diff-row-s1');
    expect(row.className).toContain('amber');
    expect(screen.getByText('Modified')).toBeInTheDocument();
    expect(screen.getByText(/agent/)).toBeInTheDocument();
  });

  it('shows unchanged steps as dimmed', () => {
    const steps = [makeStep({ id: 's1' })];
    render(<VersionDiff oldSteps={steps} newSteps={steps} />);
    // When all steps are unchanged, shows "no changes" message
    expect(screen.getByText(/no changes/i)).toBeInTheDocument();
  });

  it('handles empty diff', () => {
    render(<VersionDiff oldSteps={[]} newSteps={[]} />);
    expect(screen.getByText(/no changes/i)).toBeInTheDocument();
  });
});
