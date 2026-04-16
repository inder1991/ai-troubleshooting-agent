import { describe, expect, test, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ValidationBanner } from '../ValidationBanner';

describe('ValidationBanner', () => {
  test('renders nothing when errors array is empty', () => {
    const { container } = render(<ValidationBanner errors={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  test('shows summary with error and warning counts', () => {
    render(
      <ValidationBanner
        errors={[
          { path: 'steps[0].id', message: 'missing id', severity: 'error' },
          { path: 'steps[1]', message: 'maybe wrong', severity: 'warning' },
          { path: 'steps[2]', message: 'also bad' }, // defaults to error
        ]}
      />,
    );
    expect(screen.getByText(/2 errors/i)).toBeInTheDocument();
    expect(screen.getByText(/1 warning/i)).toBeInTheDocument();
  });

  test('omits zero counts from summary', () => {
    render(
      <ValidationBanner
        errors={[{ path: 'a', message: 'm', severity: 'warning' }]}
      />,
    );
    expect(screen.queryByText(/0 errors/i)).not.toBeInTheDocument();
    expect(screen.getByText(/1 warning/i)).toBeInTheDocument();
  });

  test('expands to show error list when toggle is clicked', () => {
    render(
      <ValidationBanner
        errors={[
          { path: 'steps[0].id', message: 'missing id', severity: 'error' },
        ]}
      />,
    );
    // Not visible initially
    expect(screen.queryByText('missing id')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /expand|show|details/i }));
    expect(screen.getByText('missing id')).toBeInTheDocument();
    expect(screen.getByText('steps[0].id')).toBeInTheDocument();
  });

  test('"Jump to step" calls onJump(stepId) exactly once', () => {
    const onJump = vi.fn();
    render(
      <ValidationBanner
        errors={[
          {
            path: 'steps[0].inputs',
            message: 'bad ref',
            stepId: 'step-1',
            severity: 'error',
          },
        ]}
        onJump={onJump}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /expand|show|details/i }));
    fireEvent.click(screen.getByRole('button', { name: /jump to step/i }));
    expect(onJump).toHaveBeenCalledTimes(1);
    expect(onJump).toHaveBeenCalledWith('step-1');
  });

  test('warning-only banner uses amber accent class', () => {
    const { container } = render(
      <ValidationBanner
        errors={[{ path: 'a', message: 'm', severity: 'warning' }]}
      />,
    );
    // root banner wrapper is the first element
    const root = container.firstElementChild as HTMLElement;
    expect(root.className).toMatch(/wr-status-warning/);
    expect(root.className).not.toMatch(/wr-status-error/);
  });

  test('error severity uses red accent class', () => {
    const { container } = render(
      <ValidationBanner
        errors={[{ path: 'a', message: 'm', severity: 'error' }]}
      />,
    );
    const root = container.firstElementChild as HTMLElement;
    expect(root.className).toMatch(/wr-status-error/);
  });
});
