import { describe, expect, test, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DisabledState } from '../DisabledState';

// Mock the feature flags hook so we can control retry/loading directly.
const retry = vi.fn();
let mockState: { workflows: boolean; loading: boolean } = {
  workflows: false,
  loading: false,
};

vi.mock('../../../../contexts/FeatureFlagsContext', () => ({
  useFeatureFlags: () => ({ ...mockState, retry }),
}));

describe('DisabledState', () => {
  beforeEach(() => {
    retry.mockReset();
    mockState = { workflows: false, loading: false };
  });

  test('renders the disabled message', () => {
    render(<DisabledState />);
    expect(
      screen.getByText(/workflows feature is disabled in this environment\./i),
    ).toBeInTheDocument();
  });

  test('clicking Retry calls useFeatureFlags().retry()', () => {
    render(<DisabledState />);
    fireEvent.click(screen.getByRole('button', { name: /retry/i }));
    expect(retry).toHaveBeenCalledTimes(1);
  });

  test('Retry button is disabled while loading', () => {
    mockState = { workflows: false, loading: true };
    render(<DisabledState />);
    const btn = screen.getByRole('button');
    expect(btn).toBeDisabled();
  });
});
