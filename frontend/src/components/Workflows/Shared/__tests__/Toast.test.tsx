import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act, fireEvent } from '@testing-library/react';
import { ToastProvider, useToast } from '../Toast';

/* Helper that renders a button wired to showToast so we can trigger toasts
   from inside the provider tree. */
function Harness({
  toastProps,
}: {
  toastProps?: Parameters<ReturnType<typeof useToast>['showToast']>[0];
}) {
  const defaults = { type: 'info' as const, message: 'Hello toast' };
  const merged = { ...defaults, ...toastProps };

  function Inner() {
    const { showToast } = useToast();
    return <button onClick={() => showToast(merged)}>fire</button>;
  }

  return (
    <ToastProvider>
      <Inner />
    </ToastProvider>
  );
}

describe('Toast notification system', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders a toast with the given message', () => {
    render(<Harness />);

    fireEvent.click(screen.getByText('fire'));
    expect(screen.getByText('Hello toast')).toBeInTheDocument();
  });

  it('auto-dismisses after the default duration', () => {
    render(<Harness />);

    fireEvent.click(screen.getByText('fire'));
    expect(screen.getByText('Hello toast')).toBeInTheDocument();

    // Advance past default 4000ms + 200ms exit animation
    act(() => vi.advanceTimersByTime(4200));
    expect(screen.queryByText('Hello toast')).not.toBeInTheDocument();
  });

  it('auto-dismisses after a custom duration', () => {
    render(
      <Harness toastProps={{ type: 'success', message: 'Quick', duration: 1000 }} />,
    );

    fireEvent.click(screen.getByText('fire'));
    expect(screen.getByText('Quick')).toBeInTheDocument();

    act(() => vi.advanceTimersByTime(1200));
    expect(screen.queryByText('Quick')).not.toBeInTheDocument();
  });

  it('shows an action button when provided and calls onClick', () => {
    const actionFn = vi.fn();
    render(
      <Harness
        toastProps={{
          type: 'error',
          message: 'Failed',
          action: { label: 'Retry', onClick: actionFn },
        }}
      />,
    );

    fireEvent.click(screen.getByText('fire'));
    const retryBtn = screen.getByText('Retry');
    expect(retryBtn).toBeInTheDocument();

    fireEvent.click(retryBtn);
    expect(actionFn).toHaveBeenCalledOnce();
  });

  it('stacks multiple toasts', () => {
    function Multi() {
      const { showToast } = useToast();
      return (
        <>
          <button onClick={() => showToast({ type: 'info', message: 'First' })}>one</button>
          <button onClick={() => showToast({ type: 'success', message: 'Second' })}>two</button>
        </>
      );
    }

    render(
      <ToastProvider>
        <Multi />
      </ToastProvider>,
    );

    fireEvent.click(screen.getByText('one'));
    fireEvent.click(screen.getByText('two'));

    expect(screen.getAllByTestId('toast')).toHaveLength(2);
    expect(screen.getByText('First')).toBeInTheDocument();
    expect(screen.getByText('Second')).toBeInTheDocument();
  });

  it('removes a toast when close button is clicked', () => {
    render(<Harness />);

    fireEvent.click(screen.getByText('fire'));
    expect(screen.getByText('Hello toast')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /close/i }));
    // Wait for exit animation
    act(() => vi.advanceTimersByTime(250));
    expect(screen.queryByText('Hello toast')).not.toBeInTheDocument();
  });

  it('uses role="alert" for error toasts', () => {
    render(<Harness toastProps={{ type: 'error', message: 'Oops' }} />);

    fireEvent.click(screen.getByText('fire'));
    expect(screen.getByRole('alert')).toBeInTheDocument();
  });

  it('uses role="status" for success toasts', () => {
    render(<Harness toastProps={{ type: 'success', message: 'Done' }} />);

    fireEvent.click(screen.getByText('fire'));
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('uses role="status" for info toasts', () => {
    render(<Harness toastProps={{ type: 'info', message: 'FYI' }} />);

    fireEvent.click(screen.getByText('fire'));
    expect(screen.getByRole('status')).toBeInTheDocument();
  });
});
