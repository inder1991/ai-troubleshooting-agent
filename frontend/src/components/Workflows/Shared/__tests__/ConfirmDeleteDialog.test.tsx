import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ConfirmDeleteDialog } from '../ConfirmDeleteDialog';

describe('ConfirmDeleteDialog', () => {
  const defaultProps = {
    workflowName: 'my-workflow',
    onConfirm: vi.fn(),
    onCancel: vi.fn(),
  };

  it('renders with workflow name prompt', () => {
    render(<ConfirmDeleteDialog {...defaultProps} />);
    expect(screen.getByText(/my-workflow/)).toBeInTheDocument();
  });

  it('delete button is disabled until name matches', () => {
    render(<ConfirmDeleteDialog {...defaultProps} />);
    const btn = screen.getByRole('button', { name: /delete/i });
    expect(btn).toBeDisabled();
  });

  it('enables delete button when name matches', async () => {
    const user = userEvent.setup();
    render(<ConfirmDeleteDialog {...defaultProps} />);
    const input = screen.getByPlaceholderText('my-workflow');
    await user.type(input, 'my-workflow');
    const btn = screen.getByRole('button', { name: /delete/i });
    expect(btn).not.toBeDisabled();
  });

  it('calls onConfirm when delete clicked', async () => {
    const onConfirm = vi.fn();
    const user = userEvent.setup();
    render(<ConfirmDeleteDialog {...defaultProps} onConfirm={onConfirm} />);
    const input = screen.getByPlaceholderText('my-workflow');
    await user.type(input, 'my-workflow');
    await user.click(screen.getByRole('button', { name: /delete/i }));
    expect(onConfirm).toHaveBeenCalledOnce();
  });

  it('calls onCancel when cancel clicked', async () => {
    const onCancel = vi.fn();
    const user = userEvent.setup();
    render(<ConfirmDeleteDialog {...defaultProps} onCancel={onCancel} />);
    await user.click(screen.getByRole('button', { name: /cancel/i }));
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it('shows deleting state', () => {
    render(<ConfirmDeleteDialog {...defaultProps} deleting />);
    expect(screen.getByText(/deleting/i)).toBeInTheDocument();
  });

  it('pressing Escape calls onCancel', async () => {
    const onCancel = vi.fn();
    const user = userEvent.setup();
    render(<ConfirmDeleteDialog workflowName="test" onConfirm={vi.fn()} onCancel={onCancel} />);
    await user.keyboard('{Escape}');
    expect(onCancel).toHaveBeenCalled();
  });

  it('has role="alertdialog" and aria-modal', () => {
    render(<ConfirmDeleteDialog workflowName="test" onConfirm={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByRole('alertdialog')).toHaveAttribute('aria-modal', 'true');
  });

  it('input receives initial focus', () => {
    render(<ConfirmDeleteDialog workflowName="test" onConfirm={vi.fn()} onCancel={vi.fn()} />);
    expect(document.activeElement?.tagName).toBe('INPUT');
  });
});
