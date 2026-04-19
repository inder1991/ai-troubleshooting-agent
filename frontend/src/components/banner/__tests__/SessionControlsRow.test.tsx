import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import SessionControlsRow from '../SessionControlsRow';
import { IncidentLifecycleProvider } from '../../../contexts/IncidentLifecycleContext';
import type { V4SessionStatus, V4Findings, DiagnosticPhase } from '../../../types';
import * as apiModule from '../../../services/api';

function status(phase: DiagnosticPhase = 'collecting_context'): V4SessionStatus {
  return {
    session_id: 's',
    service_name: 'svc',
    phase,
    confidence: 0,
    findings_count: 0,
    token_usage: [],
    breadcrumbs: [],
    created_at: '2026-04-20T00:00:00Z',
    updated_at: '2026-04-20T00:00:00Z',
    pending_action: null,
  };
}

function Harness({
  phase = 'collecting_context' as DiagnosticPhase,
  now,
}: {
  phase?: DiagnosticPhase;
  now?: number;
}) {
  const s = status(phase);
  const f: V4Findings = { session_id: 's', findings: [] };
  return (
    <IncidentLifecycleProvider status={s} now={now ?? Date.now()}>
      <SessionControlsRow sessionId="s1" findings={f} status={s} />
    </IncidentLifecycleProvider>
  );
}

describe('SessionControlsRow', () => {
  beforeEach(() => {
    // jsdom writeText shim
    Object.defineProperty(window.navigator, 'clipboard', {
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
      configurable: true,
    });
    // Confirm dialog — default-accept for tests unless overridden.
    vi.spyOn(window, 'confirm').mockReturnValue(true);
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders copy-link and cancel buttons', () => {
    render(<Harness />);
    expect(screen.getByTestId('copy-session-link')).toBeInTheDocument();
    expect(screen.getByTestId('cancel-investigation')).toBeInTheDocument();
  });

  it('copy-link button writes the current URL to clipboard', () => {
    render(<Harness />);
    fireEvent.click(screen.getByTestId('copy-session-link'));
    expect(window.navigator.clipboard.writeText).toHaveBeenCalled();
  });

  it('cancel button fires cancelInvestigation for active phase', async () => {
    const spy = vi.spyOn(apiModule, 'cancelInvestigation').mockResolvedValue({ status: 'cancelled' });
    render(<Harness phase="collecting_context" />);
    fireEvent.click(screen.getByTestId('cancel-investigation'));
    await waitFor(() => expect(spy).toHaveBeenCalledWith('s1'));
  });

  it('cancel button disabled during terminal phase', () => {
    render(<Harness phase="complete" />);
    const btn = screen.getByTestId('cancel-investigation');
    expect(btn).toBeDisabled();
  });

  it('cancel button disabled during cancelled phase', () => {
    render(<Harness phase="cancelled" />);
    expect(screen.getByTestId('cancel-investigation')).toBeDisabled();
  });

  it('cancel respects user-declined confirm dialog', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    const spy = vi.spyOn(apiModule, 'cancelInvestigation');
    render(<Harness phase="collecting_context" />);
    fireEvent.click(screen.getByTestId('cancel-investigation'));
    expect(spy).not.toHaveBeenCalled();
  });

  it('cancel error is shown when API call fails', async () => {
    vi.spyOn(apiModule, 'cancelInvestigation').mockRejectedValue(
      new Error('backend unreachable'),
    );
    render(<Harness phase="collecting_context" />);
    fireEvent.click(screen.getByTestId('cancel-investigation'));
    await waitFor(() =>
      expect(screen.getByTestId('cancel-error').textContent).toMatch(/backend unreachable/),
    );
  });

  it('cancel disabled for historical lifecycle', () => {
    // Terminal phase + old updated_at → lifecycle historical
    render(
      <Harness
        phase="complete"
        now={Date.parse('2026-04-25T00:00:00Z')}
      />,
    );
    expect(screen.getByTestId('cancel-investigation')).toBeDisabled();
  });
});
