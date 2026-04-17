import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import StackTraceTelescope from '../cards/StackTraceTelescope';
import { RetestVerdictBlock } from '../RetestVerdictBlock';

describe('StackTraceTelescope — stale-line warning (Task 4.20)', () => {
  it('warns when frames are stale', () => {
    render(
      <StackTraceTelescope
        traces={['  at foo (src/foo.py:50)']}
        frames={[{ file: 'src/foo.py', line: 50, is_stale: true, reason: 'line 50 > file length 20' }]}
        deployedSha="abc123def456"
      />,
    );
    expect(screen.getByText(/line numbers may be stale/i)).toBeInTheDocument();
    expect(screen.getByText(/abc123de/)).toBeInTheDocument();
    expect(screen.getByText(/src\/foo\.py:50/)).toBeInTheDocument();
  });

  it('does not warn when all frames are fresh', () => {
    render(
      <StackTraceTelescope
        traces={['  at foo (src/foo.py:5)']}
        frames={[{ file: 'src/foo.py', line: 5, is_stale: false }]}
        deployedSha="abc"
      />,
    );
    expect(screen.queryByText(/line numbers may be stale/i)).toBeNull();
  });

  it('does not warn when frames prop absent (regression guard)', () => {
    render(<StackTraceTelescope traces={['  at foo (x.py:1)']} />);
    expect(screen.queryByText(/stale/i)).toBeNull();
  });
});

describe('RetestVerdictBlock', () => {
  it('renders symptom_resolved in emerald with delta', () => {
    render(
      <RetestVerdictBlock
        retest={{
          verdict: 'symptom_resolved',
          checked_at: '2026-04-17T14:40:00Z',
          original_value: '8s',
          current_value: '0.2s',
        }}
      />,
    );
    expect(screen.getByText(/symptom resolved/i)).toBeInTheDocument();
    expect(screen.getByText(/8s → 0\.2s/)).toBeInTheDocument();
    expect(screen.getByTestId('retest-verdict-block').className).toMatch(/wr-emerald/);
  });

  it('renders symptom_persists in red', () => {
    render(
      <RetestVerdictBlock
        retest={{
          verdict: 'symptom_persists',
          checked_at: '2026-04-17T14:40:00Z',
          original_value: '8s',
          current_value: '8.1s',
        }}
      />,
    );
    expect(screen.getByText(/symptom persists/i)).toBeInTheDocument();
    expect(screen.getByTestId('retest-verdict-block').className).toMatch(/wr-red/);
  });

  it('renders insufficient in amber', () => {
    render(
      <RetestVerdictBlock
        retest={{
          verdict: 'insufficient',
          checked_at: '2026-04-17T14:40:00Z',
          original_value: '—',
          current_value: '—',
        }}
      />,
    );
    expect(screen.getByTestId('retest-verdict-block').className).toMatch(/wr-amber/);
  });

  it('returns null when retest is null', () => {
    const { container } = render(<RetestVerdictBlock retest={null} />);
    expect(container.firstChild).toBeNull();
  });
});
