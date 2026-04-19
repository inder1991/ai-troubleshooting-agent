import { describe, it, expect } from 'vitest';
import { synthesizePhaseNarrative } from '../phaseNarrative';
import type { TaskEvent } from '../../../types';

function event(over: Partial<TaskEvent> = {}): TaskEvent {
  return {
    timestamp: '2026-04-19T00:00:00Z',
    agent_name: 'log_agent',
    event_type: 'started',
    message: 'log_agent starting',
    ...over,
  } as TaskEvent;
}

describe('synthesizePhaseNarrative', () => {
  it('returns manual-override copy when isManualOverride', () => {
    const out = synthesizePhaseNarrative({
      events: [],
      phase: null,
      isManualOverride: true,
    });
    expect(out).toBe('Awaiting operator input.');
  });

  it('returns closed copy when historical', () => {
    const out = synthesizePhaseNarrative({
      events: [],
      phase: 'complete',
      isHistorical: true,
    });
    expect(out).toBe('Incident closed.');
  });

  it('appends resolution summary to closed copy', () => {
    const out = synthesizePhaseNarrative({
      events: [],
      phase: 'complete',
      isHistorical: true,
      resolutionSummary: 'Rolled back PR #1247.',
    });
    expect(out).toBe('Incident closed. Rolled back PR #1247.');
  });

  it('returns diagnosis-complete copy', () => {
    const out = synthesizePhaseNarrative({
      events: [],
      phase: 'diagnosis_complete',
    });
    expect(out).toBe('Diagnosis complete; fix is pending review.');
  });

  it('returns cancelled copy', () => {
    const out = synthesizePhaseNarrative({
      events: [],
      phase: 'cancelled',
    });
    expect(out).toBe('Investigation paused by operator.');
  });

  it('says "investigation is starting" when no events and active', () => {
    const out = synthesizePhaseNarrative({
      events: [],
      phase: 'collecting_context',
    });
    expect(out).toBe('Investigation is starting.');
  });

  it('names a single active agent in Commander voice', () => {
    const out = synthesizePhaseNarrative({
      events: [
        event({ agent_name: 'log_agent', event_type: 'started', message: 'analyzing logs' }),
      ],
      phase: 'collecting_context',
    });
    expect(out).toMatch(/^Log Agent is analyzing\.$/);
  });

  it('joins two active agents with "while"', () => {
    const out = synthesizePhaseNarrative({
      events: [
        event({ agent_name: 'metrics_agent', event_type: 'started', message: 'validating RED metrics', timestamp: '2026-04-19T00:00:00Z' }),
        event({ agent_name: 'log_agent', event_type: 'started', message: 'analyzing retries', timestamp: '2026-04-19T00:00:05Z' }),
      ],
      phase: 'collecting_context',
    });
    expect(out).toMatch(/Metrics Agent is validating while Log Agent is analyzing\./);
  });

  it('strips underscores + capitalises agent names', () => {
    const out = synthesizePhaseNarrative({
      events: [event({ agent_name: 'tracing_agent', event_type: 'started', message: 'querying jaeger' })],
      phase: 'collecting_context',
    });
    expect(out).toMatch(/Trace Walker is analyzing\./);
  });

  it('ignores supervisor events for active-agent derivation', () => {
    const out = synthesizePhaseNarrative({
      events: [
        event({ agent_name: 'supervisor', event_type: 'summary', message: 'cross-check complete' }),
      ],
      phase: 'collecting_context',
    });
    expect(out).toBe('Awaiting verdict from supervisor.');
  });

  it('trims trailing agents when ≥3 active', () => {
    const out = synthesizePhaseNarrative({
      events: [
        event({ agent_name: 'log_agent', event_type: 'started', timestamp: '2026-04-19T00:00:00Z' }),
        event({ agent_name: 'metrics_agent', event_type: 'started', timestamp: '2026-04-19T00:00:05Z' }),
        event({ agent_name: 'k8s_agent', event_type: 'started', timestamp: '2026-04-19T00:00:10Z' }),
        event({ agent_name: 'tracing_agent', event_type: 'started', timestamp: '2026-04-19T00:00:15Z' }),
      ],
      phase: 'collecting_context',
    });
    expect(out).toMatch(/\(\+2 more\)/);
  });
});
