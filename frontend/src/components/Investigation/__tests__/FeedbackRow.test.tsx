import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { FeedbackRow } from '../FeedbackRow';

describe('FeedbackRow', () => {
  it('submits feedback with selected correctness and root cause', async () => {
    const user = userEvent.setup();
    const submit = vi.fn(async () => ({ ok: true }));
    render(<FeedbackRow runId="r1" submit={submit} />);

    await user.click(screen.getByRole('button', { name: /correct/i }));
    const input = screen.getByLabelText(/actual root cause/i);
    await user.type(input, 'deploy regression');
    await user.click(screen.getByRole('button', { name: /submit/i }));

    await waitFor(() => {
      expect(submit).toHaveBeenCalledWith({
        runId: 'r1',
        wasCorrect: true,
        actualRootCause: 'deploy regression',
      });
    });
  });

  it('submits wasCorrect=false when "wrong" clicked', async () => {
    const user = userEvent.setup();
    const submit = vi.fn(async () => ({ ok: true }));
    render(<FeedbackRow runId="r1" submit={submit} />);

    await user.click(screen.getByRole('button', { name: /wrong/i }));
    await user.click(screen.getByRole('button', { name: /submit/i }));

    await waitFor(() => {
      expect(submit).toHaveBeenCalledWith({
        runId: 'r1',
        wasCorrect: false,
        actualRootCause: '',
      });
    });
  });

  it('disables submit until a verdict is selected', () => {
    render(<FeedbackRow runId="r1" submit={vi.fn()} />);
    expect(screen.getByRole('button', { name: /submit/i })).toBeDisabled();
  });

  it('shows thank-you confirmation after successful submit', async () => {
    const user = userEvent.setup();
    const submit = vi.fn(async () => ({ ok: true }));
    render(<FeedbackRow runId="r1" submit={submit} />);

    await user.click(screen.getByRole('button', { name: /correct/i }));
    await user.click(screen.getByRole('button', { name: /submit/i }));

    await waitFor(() => {
      expect(screen.getByText(/thanks for the feedback/i)).toBeInTheDocument();
    });
  });

  it('disables buttons after successful submit to prevent double-post', async () => {
    const user = userEvent.setup();
    const submit = vi.fn(async () => ({ ok: true }));
    render(<FeedbackRow runId="r1" submit={submit} />);

    await user.click(screen.getByRole('button', { name: /correct/i }));
    await user.click(screen.getByRole('button', { name: /submit/i }));

    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /submit/i })).toBeNull();
    });
  });

  it('surfaces error message on submit failure and keeps form editable', async () => {
    const user = userEvent.setup();
    const submit = vi.fn(async () => {
      throw new Error('network down');
    });
    render(<FeedbackRow runId="r1" submit={submit} />);

    await user.click(screen.getByRole('button', { name: /correct/i }));
    await user.click(screen.getByRole('button', { name: /submit/i }));

    await waitFor(() => {
      expect(screen.getByText(/network down|couldn.t submit/i)).toBeInTheDocument();
    });
    // Form still editable
    expect(screen.getByRole('button', { name: /submit/i })).toBeInTheDocument();
  });
});
