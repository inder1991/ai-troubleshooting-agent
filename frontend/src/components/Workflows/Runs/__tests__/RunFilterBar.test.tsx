import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { RunFilterBar } from '../RunFilterBar';

describe('RunFilterBar', () => {
  const defaultProps = {
    statuses: [] as string[],
    onStatusToggle: vi.fn(),
    sortBy: 'started_at' as const,
    sortOrder: 'desc' as const,
    onSortChange: vi.fn(),
  };

  it('renders status chip buttons', () => {
    render(<RunFilterBar {...defaultProps} />);
    expect(screen.getByRole('button', { name: /succeeded/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /failed/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /running/i })).toBeInTheDocument();
  });

  it('highlights active status chips', () => {
    render(<RunFilterBar {...defaultProps} statuses={['failed']} />);
    const btn = screen.getByRole('button', { name: /failed/i });
    expect(btn.className).toContain('bg-red');
  });

  it('calls onStatusToggle when chip clicked', async () => {
    const onStatusToggle = vi.fn();
    const user = userEvent.setup();
    render(<RunFilterBar {...defaultProps} onStatusToggle={onStatusToggle} />);
    await user.click(screen.getByRole('button', { name: /failed/i }));
    expect(onStatusToggle).toHaveBeenCalledWith('failed');
  });

  it('shows sort dropdown', () => {
    render(<RunFilterBar {...defaultProps} />);
    expect(screen.getByLabelText(/sort/i)).toBeInTheDocument();
  });
});
