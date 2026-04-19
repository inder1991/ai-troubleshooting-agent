import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import {
  deriveLifecycle,
  IncidentLifecycleProvider,
  useIncidentLifecycle,
} from '../IncidentLifecycleContext';
import type { V4SessionStatus, DiagnosticPhase } from '../../types';

function status(over: Partial<V4SessionStatus> = {}): V4SessionStatus {
  return {
    session_id: 's',
    service_name: 'svc',
    phase: 'collecting_context' as DiagnosticPhase,
    confidence: 50,
    findings_count: 0,
    token_usage: [],
    breadcrumbs: [],
    created_at: '2026-04-19T00:00:00Z',
    updated_at: '2026-04-19T00:00:00Z',
    pending_action: null,
    ...over,
  };
}

describe('deriveLifecycle', () => {
  it('returns active for a null status', () => {
    const v = deriveLifecycle(null);
    expect(v.lifecycle).toBe('active');
    expect(v.isTerminal).toBe(false);
    expect(v.pollingSuspended).toBe(false);
  });

  it('returns active for a non-terminal phase', () => {
    const v = deriveLifecycle(status({ phase: 'collecting_context' }));
    expect(v.lifecycle).toBe('active');
    expect(v.isTerminal).toBe(false);
  });

  it('returns active for re_investigating phase', () => {
    const v = deriveLifecycle(status({ phase: 're_investigating' }));
    expect(v.lifecycle).toBe('active');
    expect(v.isTerminal).toBe(false);
  });

  it('returns recent for terminal phase closed < 6h ago', () => {
    const now = Date.parse('2026-04-19T02:00:00Z');
    const v = deriveLifecycle(
      status({
        phase: 'complete',
        updated_at: '2026-04-19T00:00:00Z', // 2h ago
      }),
      now,
    );
    expect(v.lifecycle).toBe('recent');
    expect(v.isTerminal).toBe(true);
    expect(v.pollingSuspended).toBe(false);
  });

  it('returns historical for terminal phase closed > 6h ago', () => {
    const now = Date.parse('2026-04-19T12:00:00Z');
    const v = deriveLifecycle(
      status({
        phase: 'complete',
        updated_at: '2026-04-19T00:00:00Z', // 12h ago
      }),
      now,
    );
    expect(v.lifecycle).toBe('historical');
    expect(v.isTerminal).toBe(true);
    expect(v.pollingSuspended).toBe(true);
  });

  it('treats diagnosis_complete as terminal', () => {
    const now = Date.parse('2026-04-20T00:00:00Z');
    const v = deriveLifecycle(
      status({
        phase: 'diagnosis_complete',
        updated_at: '2026-04-19T00:00:00Z', // 24h ago
      }),
      now,
    );
    expect(v.lifecycle).toBe('historical');
    expect(v.isTerminal).toBe(true);
  });

  it('treats cancelled as non-terminal (investigation can resume)', () => {
    const v = deriveLifecycle(status({ phase: 'cancelled' }));
    expect(v.lifecycle).toBe('active');
    expect(v.isTerminal).toBe(false);
  });

  it('exposes updatedAtMs as the parsed timestamp', () => {
    const v = deriveLifecycle(
      status({ updated_at: '2026-04-19T00:00:00Z' }),
    );
    expect(v.updatedAtMs).toBe(Date.parse('2026-04-19T00:00:00Z'));
  });
});

describe('IncidentLifecycleProvider + useIncidentLifecycle', () => {
  function Consumer() {
    const v = useIncidentLifecycle();
    return <div data-testid="lifecycle">{v.lifecycle}</div>;
  }

  it('provides value derived from status prop', () => {
    const { getByTestId } = render(
      <IncidentLifecycleProvider
        status={status({ phase: 'complete', updated_at: '2026-04-19T00:00:00Z' })}
        now={Date.parse('2026-04-19T01:00:00Z')}
      >
        <Consumer />
      </IncidentLifecycleProvider>,
    );
    expect(getByTestId('lifecycle').textContent).toBe('recent');
  });

  it('falls back to active when consumer is outside a provider', () => {
    const { getByTestId } = render(<Consumer />);
    expect(getByTestId('lifecycle').textContent).toBe('active');
  });
});
