import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { FixReadyBar } from '../FixReadyBar';
import { IncidentLifecycleProvider } from '../../../contexts/IncidentLifecycleContext';
import type { V4Findings, V4SessionStatus, CodeImpact, DiagnosticPhase } from '../../../types';

function status(phase: DiagnosticPhase = 'diagnosis_complete', updatedAt = '2026-04-19T00:00:00Z'): V4SessionStatus {
  return {
    session_id: 's',
    service_name: 'svc',
    phase,
    confidence: 80,
    findings_count: 0,
    token_usage: [],
    breadcrumbs: [],
    created_at: '2026-04-19T00:00:00Z',
    updated_at: updatedAt,
    pending_action: null,
  };
}

function loc(): CodeImpact {
  return {
    file_path: 'backend/src/payments/PaymentController.py',
    impact_type: 'direct_error',
    relevant_lines: [{ start: 127, end: 127 }],
    code_snippet: 'x',
    relationship: 'root',
    fix_relevance: 'must_fix',
  };
}

function findings(over: Partial<V4Findings> = {}): V4Findings {
  return { session_id: 's', findings: [], ...over };
}

function Harness({
  findings: f,
  status: s,
  now,
  onOpenPR,
}: {
  findings: V4Findings | null;
  status: V4SessionStatus | null;
  now?: number;
  onOpenPR?: () => void;
}) {
  // Default `now` to status.updated_at so lifecycle lands in the
  // "recent" bucket unless the test overrides to force historical.
  const effectiveNow =
    now ?? (s?.updated_at ? Date.parse(s.updated_at) + 1000 : Date.now());
  return (
    <IncidentLifecycleProvider status={s} now={effectiveNow}>
      <FixReadyBar findings={f} status={s} onOpenPR={onOpenPR} />
    </IncidentLifecycleProvider>
  );
}

describe('FixReadyBar', () => {
  // ── Trigger gates ──

  it('renders nothing when phase is not terminal', () => {
    const { container } = render(
      <Harness
        findings={findings({ root_cause_location: loc() })}
        status={status('collecting_context')}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing when no fix data is available', () => {
    const { container } = render(
      <Harness findings={findings()} status={status('diagnosis_complete')} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders when phase=diagnosis_complete + root_cause_location present', () => {
    render(
      <Harness
        findings={findings({ root_cause_location: loc() })}
        status={status('diagnosis_complete')}
      />,
    );
    expect(screen.getByTestId('fix-ready-bar')).toBeInTheDocument();
    expect(screen.getByTestId('fix-ready-headline').textContent).toMatch(
      /Fix ready.*PaymentController\.py, line 127/,
    );
  });

  it('renders when phase=complete + suggested_fix_areas present', () => {
    render(
      <Harness
        findings={findings({
          suggested_fix_areas: [
            { file_path: 'a/b/retry.py', rationale: 'cap attempts', fix_priority: 'high' } as unknown as V4Findings['suggested_fix_areas'][number],
          ],
        })}
        status={status('complete')}
      />,
    );
    expect(screen.getByTestId('fix-ready-headline').textContent).toMatch(/retry\.py/);
  });

  // ── Actions ──

  it('fires onOpenPR when Open PR clicked (active lifecycle)', () => {
    const onOpenPR = vi.fn();
    render(
      <Harness
        findings={findings({ root_cause_location: loc() })}
        status={status('diagnosis_complete')}
        onOpenPR={onOpenPR}
      />,
    );
    fireEvent.click(screen.getByTestId('fix-ready-open-pr'));
    expect(onOpenPR).toHaveBeenCalledTimes(1);
  });

  it('dismiss button hides the bar', () => {
    render(
      <Harness
        findings={findings({ root_cause_location: loc() })}
        status={status('diagnosis_complete')}
      />,
    );
    expect(screen.getByTestId('fix-ready-bar')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('fix-ready-dismiss'));
    expect(screen.queryByTestId('fix-ready-bar')).toBeNull();
  });

  it('view diff toggles the inline accordion', () => {
    render(
      <Harness
        findings={findings({ root_cause_location: loc() })}
        status={status('diagnosis_complete')}
      />,
    );
    const trigger = screen.getByTestId('fix-ready-view-diff');
    expect(trigger.getAttribute('aria-expanded')).toBe('false');
    fireEvent.click(trigger);
    expect(trigger.getAttribute('aria-expanded')).toBe('true');
  });

  // ── Historical lifecycle ──

  it('uses history-bar voice and hides open-PR + dismiss when historical', () => {
    const now = Date.parse('2026-04-20T00:00:00Z'); // 24h after close
    render(
      <Harness
        findings={findings({ root_cause_location: loc() })}
        status={status('complete', '2026-04-19T00:00:00Z')}
        now={now}
        onOpenPR={() => {}}
      />,
    );
    expect(screen.getByTestId('fix-ready-headline').textContent).toMatch(/Fix applied/);
    expect(screen.queryByTestId('fix-ready-open-pr')).toBeNull();
    expect(screen.queryByTestId('fix-ready-dismiss')).toBeNull();
  });
});
