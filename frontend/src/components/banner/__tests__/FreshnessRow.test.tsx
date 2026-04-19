import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import FreshnessRow from '../FreshnessRow';
import { IncidentLifecycleProvider } from '../../../contexts/IncidentLifecycleContext';
import { AppControlProvider } from '../../../contexts/AppControlContext';
import type { V4Findings, V4SessionStatus, TaskEvent, TokenUsage, DiagnosticPhase } from '../../../types';

function status(over: Partial<V4SessionStatus> = {}): V4SessionStatus {
  return {
    session_id: 's',
    service_name: 'svc',
    phase: 'collecting_context' as DiagnosticPhase,
    confidence: 0,
    findings_count: 0,
    token_usage: [],
    breadcrumbs: [],
    created_at: '2026-04-19T00:00:00Z',
    updated_at: '2026-04-19T00:00:00Z',
    pending_action: null,
    ...over,
  };
}

function findings(over: Partial<V4Findings> = {}): V4Findings {
  return { session_id: 's', findings: [], ...over };
}

function tu(agent: string, total: number): TokenUsage {
  return { agent_name: agent, input_tokens: 0, output_tokens: 0, total_tokens: total };
}

function event(over: Partial<TaskEvent> = {}): TaskEvent {
  return {
    timestamp: '2026-04-19T00:00:00Z',
    agent_name: 'log_agent',
    event_type: 'started',
    message: 'x',
    ...over,
  } as TaskEvent;
}

function Harness({
  findings: f = findings(),
  status: s = status(),
  events = [],
  lastFetchAgoSec = 3,
  wsConnected = true,
  now,
}: {
  findings?: V4Findings;
  status?: V4SessionStatus;
  events?: TaskEvent[];
  lastFetchAgoSec?: number;
  wsConnected?: boolean;
  now?: number;
}) {
  return (
    <AppControlProvider>
      <IncidentLifecycleProvider status={s} now={now}>
        <FreshnessRow
          findings={f}
          status={s}
          events={events}
          lastFetchAgoSec={lastFetchAgoSec}
          wsConnected={wsConnected}
        />
      </IncidentLifecycleProvider>
    </AppControlProvider>
  );
}

describe('FreshnessRow', () => {
  it('renders a live status dot + age in the healthy case', () => {
    render(<Harness />);
    const row = screen.getByTestId('freshness-row');
    expect(row.textContent).toMatch(/live/);
    expect(screen.getByTestId('freshness-age').textContent).toMatch(/3s/);
  });

  it('shows incident id when present', () => {
    render(<Harness findings={findings({ incident_id: 'INC-2026-A3F7' })} />);
    expect(screen.getByTestId('freshness-incident-id').textContent).toMatch(
      /INC-2026-A3F7/,
    );
  });

  it('hides incident-id clause when absent', () => {
    render(<Harness />);
    expect(screen.queryByTestId('freshness-incident-id')).toBeNull();
  });

  it('renders tokens clause when token_usage totals > 0', () => {
    render(<Harness status={status({ token_usage: [tu('log_agent', 1247)] })} />);
    expect(screen.getByTestId('freshness-tokens').textContent).toMatch(/1\.2k tokens/);
  });

  it('renders cost clause when budget reports usd_used > 0', () => {
    render(
      <Harness
        status={status({
          budget: {
            tool_calls_used: 1,
            tool_calls_max: 10,
            llm_usd_used: 0.042,
            llm_usd_max: 1,
          },
        })}
      />,
    );
    expect(screen.getByTestId('freshness-cost').textContent).toMatch(/\$0\.042/);
  });

  it('hides both tokens and cost when zero', () => {
    render(<Harness />);
    expect(screen.queryByTestId('freshness-tokens')).toBeNull();
    expect(screen.queryByTestId('freshness-cost')).toBeNull();
  });

  it('uses mono for incident id and serif italic for tokens / cost', () => {
    render(
      <Harness
        findings={findings({ incident_id: 'INC-1' })}
        status={status({
          token_usage: [tu('log_agent', 100)],
          budget: { tool_calls_used: 1, tool_calls_max: 10, llm_usd_used: 0.01, llm_usd_max: 1 },
        })}
      />,
    );
    expect(screen.getByTestId('freshness-incident-id').className).toMatch(/font-mono/);
    expect(screen.getByTestId('freshness-tokens').className).toMatch(/font-editorial/);
    expect(screen.getByTestId('freshness-tokens').className).toMatch(/italic/);
    expect(screen.getByTestId('freshness-cost').className).toMatch(/font-editorial/);
  });

  it('flips to archived for historical incidents', () => {
    const closed = status({
      phase: 'complete',
      updated_at: '2026-04-10T00:00:00Z', // 9 days before now
    });
    render(<Harness status={closed} now={Date.parse('2026-04-19T00:00:00Z')} />);
    const row = screen.getByTestId('freshness-row');
    expect(row.textContent).toMatch(/archived/);
    expect(screen.getByTestId('freshness-age').textContent).toMatch(/closed/);
  });

  // ── PR-D: terminal-phase neutralization ─────────────────────────

  it('shows "resolved" (not "live") the moment phase goes terminal, even if just now', () => {
    // Incident just completed — still in `recent` bucket, not historical.
    const closed = status({
      phase: 'complete',
      updated_at: '2026-04-19T00:00:00Z',
    });
    render(
      <Harness
        status={closed}
        now={Date.parse('2026-04-19T00:00:05Z')} // 5s after close
        lastFetchAgoSec={2}
      />,
    );
    const row = screen.getByTestId('freshness-row');
    expect(row.textContent).toMatch(/resolved/);
    expect(row.textContent).not.toMatch(/\blive\b/);
  });

  it('drops seconds counter for terminal phase even when recently closed', () => {
    const closed = status({
      phase: 'complete',
      updated_at: '2026-04-19T00:00:00Z',
    });
    render(
      <Harness
        status={closed}
        now={Date.parse('2026-04-19T00:00:05Z')}
        lastFetchAgoSec={2}
      />,
    );
    const age = screen.getByTestId('freshness-age').textContent || '';
    expect(age).toMatch(/closed/);
    expect(age).not.toMatch(/\b2s\b/);
  });

  it('tokens clause updates reactively when status.token_usage grows (PR-D)', () => {
    const { rerender } = render(
      <Harness status={status({ token_usage: [tu('log_agent', 1000)] })} />,
    );
    expect(screen.getByTestId('freshness-tokens').textContent).toMatch(/1\.0k tokens/);

    rerender(
      <AppControlProvider>
        <IncidentLifecycleProvider status={status()} now={undefined}>
          <FreshnessRow
            findings={findings()}
            status={status({
              token_usage: [tu('log_agent', 1000), tu('metrics_agent', 2500)],
            })}
            events={[]}
            lastFetchAgoSec={3}
            wsConnected={true}
          />
        </IncidentLifecycleProvider>
      </AppControlProvider>,
    );
    expect(screen.getByTestId('freshness-tokens').textContent).toMatch(/3\.5k tokens/);
  });

  it('cost clause updates reactively when budget.llm_usd_used grows (PR-D)', () => {
    const { rerender } = render(
      <Harness
        status={status({
          budget: { tool_calls_used: 1, tool_calls_max: 10, llm_usd_used: 0.010, llm_usd_max: 1 },
        })}
      />,
    );
    expect(screen.getByTestId('freshness-cost').textContent).toMatch(/\$0\.010/);

    rerender(
      <AppControlProvider>
        <IncidentLifecycleProvider status={status()} now={undefined}>
          <FreshnessRow
            findings={findings()}
            status={status({
              budget: { tool_calls_used: 2, tool_calls_max: 10, llm_usd_used: 0.087, llm_usd_max: 1 },
            })}
            events={[]}
            lastFetchAgoSec={3}
            wsConnected={true}
          />
        </IncidentLifecycleProvider>
      </AppControlProvider>,
    );
    expect(screen.getByTestId('freshness-cost').textContent).toMatch(/\$0\.087/);
  });

  it('treats diagnosis_complete the same way as complete', () => {
    const closed = status({
      phase: 'diagnosis_complete',
      updated_at: '2026-04-19T00:00:00Z',
    });
    render(
      <Harness
        status={closed}
        now={Date.parse('2026-04-19T00:01:00Z')}
      />,
    );
    expect(screen.getByTestId('freshness-row').textContent).toMatch(/resolved/);
  });

  it('renders the phase narrative line', () => {
    render(<Harness events={[event({ agent_name: 'log_agent', event_type: 'started' })]} />);
    expect(screen.getByTestId('phase-narrative').textContent).toMatch(
      /Log Agent is/,
    );
  });
});
