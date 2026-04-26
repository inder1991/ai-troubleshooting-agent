import { describe, it, expect } from 'vitest';
import { scheduleSignals } from '../signalScheduler';

function base() {
  return {
    fetchFailCount: 0,
    fetchErrorDismissed: false,
    wsConnected: true,
    phase: null,
  };
}

describe('scheduleSignals', () => {
  it('returns null top + empty suppressed when healthy', () => {
    const s = scheduleSignals(base());
    expect(s.top).toBeNull();
    expect(s.suppressed).toEqual([]);
  });

  it('emits fetch-fail when count >= 3 and not dismissed', () => {
    const s = scheduleSignals({ ...base(), fetchFailCount: 4 });
    expect(s.top?.kind).toBe('fetch-fail');
    expect(s.top?.headline).toMatch(/4 failed attempts/);
  });

  it('suppresses fetch-fail when dismissed', () => {
    const s = scheduleSignals({
      ...base(),
      fetchFailCount: 4,
      fetchErrorDismissed: true,
    });
    expect(s.top).toBeNull();
  });

  it('emits ws-disconnected when wsConnected is false', () => {
    const s = scheduleSignals({ ...base(), wsConnected: false });
    expect(s.top?.kind).toBe('ws-disconnected');
  });

  it('respects severity order across all kinds', () => {
    const s = scheduleSignals({
      ...base(),
      fetchFailCount: 3,
      wsConnected: false,
      drainMode: true,
      budget: {
        tool_calls_used: 10,
        tool_calls_max: 10,
        llm_usd_used: 0,
        llm_usd_max: 1,
      },
      parallelIncidentIds: ['INC-999'],
      idleSeconds: 700,
    });
    expect(s.top?.kind).toBe('fetch-fail');
    const order = s.suppressed.map((x) => x.kind);
    expect(order).toEqual([
      'drain',
      'budget-cap',
      'parallel-incident',
      'stale-session',
      'ws-disconnected',
    ]);
  });

  it('budget-cap fires when tool-calls ratio reaches 1', () => {
    const s = scheduleSignals({
      ...base(),
      budget: {
        tool_calls_used: 18,
        tool_calls_max: 18,
        llm_usd_used: 0,
        llm_usd_max: 1,
      },
    });
    expect(s.top?.kind).toBe('budget-cap');
  });

  it('budget-cap fires when usd ratio reaches 1', () => {
    const s = scheduleSignals({
      ...base(),
      budget: {
        tool_calls_used: 1,
        tool_calls_max: 100,
        llm_usd_used: 5,
        llm_usd_max: 5,
      },
    });
    expect(s.top?.kind).toBe('budget-cap');
  });

  it('stale-session suppressed when isHistorical', () => {
    const s = scheduleSignals({ ...base(), idleSeconds: 700, isHistorical: true });
    expect(s.top).toBeNull();
  });

  it('parallel-incident includes extra-count phrasing', () => {
    const s = scheduleSignals({
      ...base(),
      parallelIncidentIds: ['INC-111', 'INC-222', 'INC-333'],
    });
    expect(s.top?.kind).toBe('parallel-incident');
    expect(s.top?.headline).toMatch(/INC-111.*\+2 more/);
  });
});
