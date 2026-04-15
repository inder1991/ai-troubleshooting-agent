import { describe, expect, test, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { WorkflowsGuard } from '../WorkflowsGuard';

const retry = vi.fn();
let mockState: { workflows: boolean; loading: boolean } = {
  workflows: true,
  loading: false,
};

vi.mock('../../../../contexts/FeatureFlagsContext', () => ({
  useFeatureFlags: () => ({ ...mockState, retry }),
}));

describe('WorkflowsGuard', () => {
  beforeEach(() => {
    retry.mockReset();
    mockState = { workflows: true, loading: false };
  });

  test('renders children when flag is on', () => {
    render(
      <WorkflowsGuard>
        <div data-testid="child">workflow page</div>
      </WorkflowsGuard>,
    );
    expect(screen.getByTestId('child')).toBeInTheDocument();
  });

  test('renders DisabledState when flag is off', () => {
    mockState = { workflows: false, loading: false };
    render(
      <WorkflowsGuard>
        <div data-testid="child">workflow page</div>
      </WorkflowsGuard>,
    );
    expect(screen.queryByTestId('child')).not.toBeInTheDocument();
    expect(
      screen.getByText(/workflows feature is disabled in this environment\./i),
    ).toBeInTheDocument();
  });

  test('renders loading indicator while flags are loading', () => {
    mockState = { workflows: false, loading: true };
    render(
      <WorkflowsGuard>
        <div data-testid="child">workflow page</div>
      </WorkflowsGuard>,
    );
    expect(screen.queryByTestId('child')).not.toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveAttribute('aria-busy', 'true');
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });
});
