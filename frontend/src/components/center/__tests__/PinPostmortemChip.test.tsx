import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PinPostmortemChip } from '../PinPostmortemChip';
import { IncidentLifecycleProvider } from '../../../contexts/IncidentLifecycleContext';
import type { V4Findings, V4SessionStatus, DiagnosticPhase } from '../../../types';

function findings(over: Partial<V4Findings> = {}): V4Findings {
  return { session_id: 's', findings: [], ...over };
}

function status(phase: DiagnosticPhase = 'collecting_context', updatedAt = '2026-04-19T00:00:00Z'): V4SessionStatus {
  return {
    session_id: 's',
    service_name: 'svc',
    phase,
    confidence: 0,
    findings_count: 0,
    token_usage: [],
    breadcrumbs: [],
    created_at: updatedAt,
    updated_at: updatedAt,
    pending_action: null,
  };
}

function Harness({
  f,
  s,
  now,
  onOpenDossier,
}: {
  f: V4Findings;
  s?: V4SessionStatus | null;
  now?: number;
  onOpenDossier?: () => void;
}) {
  return (
    <IncidentLifecycleProvider status={s ?? null} now={now}>
      <PinPostmortemChip findings={f} onOpenDossier={onOpenDossier} />
    </IncidentLifecycleProvider>
  );
}

describe('PinPostmortemChip', () => {
  it('renders nothing when there are no evidence pins', () => {
    const { container } = render(<Harness f={findings()} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders a chip with count + dossier link when pins exist', () => {
    render(
      <Harness
        f={findings({
          evidence_pins: [
            { label: 'NPE on checkout-service' },
            { label: 'metric spike on payments-api' },
          ] as unknown as V4Findings['evidence_pins'],
        })}
      />,
    );
    const chip = screen.getByTestId('pin-postmortem-chip');
    expect(chip.textContent).toMatch(/2 pinned/);
    expect(chip.textContent).toMatch(/view dossier draft/);
  });

  it('uses singular label for exactly 1 pin', () => {
    render(
      <Harness
        f={findings({
          evidence_pins: [
            { label: 'only one' },
          ] as unknown as V4Findings['evidence_pins'],
        })}
      />,
    );
    expect(screen.getByTestId('pin-postmortem-chip').textContent).toMatch(/1 pinned/);
  });

  it('click fires onOpenDossier', () => {
    const onOpenDossier = vi.fn();
    render(
      <Harness
        f={findings({
          evidence_pins: [{ label: 'x' }] as unknown as V4Findings['evidence_pins'],
        })}
        onOpenDossier={onOpenDossier}
      />,
    );
    fireEvent.click(screen.getByTestId('pin-postmortem-chip'));
    expect(onOpenDossier).toHaveBeenCalledTimes(1);
  });

  it('hides entirely when lifecycle is historical', () => {
    const { container } = render(
      <Harness
        f={findings({
          evidence_pins: [{ label: 'x' }] as unknown as V4Findings['evidence_pins'],
        })}
        s={status('complete', '2026-04-19T00:00:00Z')}
        now={Date.parse('2026-04-20T00:00:00Z')}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('HoverCard trigger has an accessible name', () => {
    render(
      <Harness
        f={findings({
          evidence_pins: [
            { label: 'x' },
            { label: 'y' },
          ] as unknown as V4Findings['evidence_pins'],
        })}
      />,
    );
    const trigger = screen.getByTestId('pin-postmortem-chip');
    expect(trigger.getAttribute('aria-label')).toMatch(/2 pinned — open dossier draft/);
  });
});
