import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { LineageDrawer } from '../LineageDrawer';

const PAYLOAD = {
  tool_name: 'metrics.query_instant',
  query: 'up{namespace="payments"}',
  query_timestamp: '2026-04-17T14:30:00Z',
  raw_value: '1',
};

describe('LineageDrawer', () => {
  it('renders tool/query/timestamp/raw rows', () => {
    render(<LineageDrawer open payload={PAYLOAD} onClose={vi.fn()} />);
    expect(screen.getByText(/metrics\.query_instant/)).toBeInTheDocument();
    expect(screen.getByText(/up\{namespace="payments"\}/)).toBeInTheDocument();
    expect(screen.getByText(/14:30:00/)).toBeInTheDocument();
  });

  it('returns null when closed', () => {
    const { container } = render(
      <LineageDrawer open={false} payload={PAYLOAD} onClose={vi.fn()} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('returns null when payload is null even if open=true', () => {
    const { container } = render(
      <LineageDrawer open payload={null} onClose={vi.fn()} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders re-run button only when rerun callback provided', () => {
    const { rerender } = render(
      <LineageDrawer open payload={PAYLOAD} onClose={vi.fn()} />,
    );
    expect(screen.queryByRole('button', { name: /re-run query/i })).toBeNull();

    rerender(
      <LineageDrawer open payload={PAYLOAD} onClose={vi.fn()} rerun={vi.fn()} />,
    );
    expect(screen.getByRole('button', { name: /re-run query/i })).toBeInTheDocument();
  });

  it('re-run replaces raw value and shows original underneath', async () => {
    const user = userEvent.setup();
    const rerun = vi.fn(async () => ({ raw_value: '42' }));
    render(<LineageDrawer open payload={PAYLOAD} onClose={vi.fn()} rerun={rerun} />);

    await user.click(screen.getByRole('button', { name: /re-run query/i }));
    await waitFor(() => {
      expect(screen.getByText(/Latest: 42/)).toBeInTheDocument();
    });
    expect(screen.getByText(/Original: 1/)).toBeInTheDocument();
  });

  it('surfaces an alert when re-run fails', async () => {
    const user = userEvent.setup();
    const rerun = vi.fn(async () => {
      throw new Error('network down');
    });
    render(<LineageDrawer open payload={PAYLOAD} onClose={vi.fn()} rerun={rerun} />);
    await user.click(screen.getByRole('button', { name: /re-run query/i }));
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/network down/);
    });
  });

  it('onClose fires when the close button is clicked', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<LineageDrawer open payload={PAYLOAD} onClose={onClose} />);
    await user.click(screen.getByRole('button', { name: /close lineage drawer/i }));
    expect(onClose).toHaveBeenCalled();
  });
});
