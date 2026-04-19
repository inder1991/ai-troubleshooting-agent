import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import AgentsCard from '../AgentsCard';
import type { V4SessionStatus, TaskEvent, TokenUsage } from '../../../types';

function event(over: Partial<TaskEvent> = {}): TaskEvent {
  return {
    timestamp: '2026-04-19T00:00:00Z',
    agent_name: 'log_agent',
    event_type: 'started',
    message: 'x',
    ...over,
  } as TaskEvent;
}

function status(over: Partial<V4SessionStatus> = {}): V4SessionStatus {
  return {
    session_id: 's',
    service_name: 'svc',
    phase: 'collecting_context' as V4SessionStatus['phase'],
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

function tu(agent_name: string, total: number): TokenUsage {
  return { agent_name, input_tokens: 0, output_tokens: 0, total_tokens: total };
}

describe('AgentsCard', () => {
  // ── NOW strip ────────────────────────────────────────────────────

  it('NOW strip renders nothing when no agents active', () => {
    render(<AgentsCard status={status()} events={[]} />);
    expect(screen.queryByTestId('live-agent-strip')).toBeNull();
  });

  it('NOW strip renders a capsule per active agent', () => {
    const events = [
      event({ agent_name: 'log_agent', event_type: 'started' }),
      event({ agent_name: 'k8s_agent', event_type: 'started' }),
    ];
    render(<AgentsCard status={status()} events={events} />);
    expect(screen.getByTestId('live-agent-strip')).toBeInTheDocument();
    expect(screen.getByTestId('live-agent-log_agent')).toBeInTheDocument();
    expect(screen.getByTestId('live-agent-k8s_agent')).toBeInTheDocument();
  });

  it('NOW strip excludes completed agents', () => {
    const events = [
      event({ agent_name: 'log_agent', event_type: 'started' }),
      event({ agent_name: 'log_agent', event_type: 'summary' }),
      event({ agent_name: 'k8s_agent', event_type: 'started' }),
    ];
    render(<AgentsCard status={status()} events={events} />);
    expect(screen.queryByTestId('live-agent-log_agent')).toBeNull();
    expect(screen.getByTestId('live-agent-k8s_agent')).toBeInTheDocument();
  });

  it('NOW strip collapses when all agents complete', () => {
    const events = [
      event({ agent_name: 'log_agent', event_type: 'started' }),
      event({ agent_name: 'log_agent', event_type: 'summary' }),
    ];
    render(<AgentsCard status={status()} events={events} />);
    expect(screen.queryByTestId('live-agent-strip')).toBeNull();
  });

  // ── Inventory ────────────────────────────────────────────────────

  it('renders all 6 agent rows', () => {
    render(<AgentsCard status={status()} events={[]} />);
    const agents = ['log_agent', 'metrics_agent', 'k8s_agent', 'tracing_agent', 'code_agent', 'change_agent'];
    agents.forEach((a) => {
      expect(screen.getByTestId(`agents-row-${a}`)).toBeInTheDocument();
    });
  });

  it('row shows token count when backend emits it', () => {
    const s = status({
      token_usage: [tu('log_agent', 1247), tu('metrics_agent', 892)],
    });
    render(<AgentsCard status={s} events={[]} />);
    expect(screen.getByTestId('agents-row-log_agent').textContent).toMatch(/1,247/);
    expect(screen.getByTestId('agents-row-metrics_agent').textContent).toMatch(/892/);
  });

  it('total footer renders only when some tokens are recorded', () => {
    const { rerender } = render(<AgentsCard status={status()} events={[]} />);
    expect(screen.queryByTestId('agents-total-tokens')).toBeNull();

    rerender(<AgentsCard status={status({ token_usage: [tu('log_agent', 100)] })} events={[]} />);
    expect(screen.getByTestId('agents-total-tokens').textContent).toMatch(/100 tokens/);
  });

  // ── PR-D: reactivity (re-investigation) ─────────────────────────

  it('NOW strip flips completed agent back to active when a fresh `started` arrives later (re-investigation)', () => {
    // Typical re-investigation event order for the same agent.
    const events = [
      event({ agent_name: 'log_agent', event_type: 'started', timestamp: '2026-04-19T00:00:00Z' }),
      event({ agent_name: 'log_agent', event_type: 'summary', timestamp: '2026-04-19T00:00:10Z' }),
      event({ agent_name: 'log_agent', event_type: 'started', timestamp: '2026-04-19T00:00:20Z' }),
    ];
    render(<AgentsCard status={status()} events={events} />);
    expect(screen.getByTestId('live-agent-log_agent')).toBeInTheDocument();
    const dot = screen.getByTestId('agents-row-log_agent').querySelector('[role="status"]');
    expect(dot?.getAttribute('title')).toBe('active');
  });

  it('last-event-wins: error after summary renders as error', () => {
    const events = [
      event({ agent_name: 'log_agent', event_type: 'started' }),
      event({ agent_name: 'log_agent', event_type: 'summary' }),
      event({ agent_name: 'log_agent', event_type: 'started' }),
      event({ agent_name: 'log_agent', event_type: 'error', message: 'boom' }),
    ];
    render(<AgentsCard status={status()} events={events} />);
    const dot = screen.getByTestId('agents-row-log_agent').querySelector('[role="status"]');
    expect(dot?.getAttribute('title')).toBe('error');
  });

  it('NOW strip re-renders immediately when a new event arrives (no polling involved)', () => {
    const base = [event({ agent_name: 'log_agent', event_type: 'started' })];
    const { rerender } = render(<AgentsCard status={status()} events={base} />);
    expect(screen.getByTestId('live-agent-log_agent')).toBeInTheDocument();
    expect(screen.queryByTestId('live-agent-metrics_agent')).toBeNull();

    // A new event arrives via WebSocket → parent passes a new events array.
    const after = [...base, event({ agent_name: 'metrics_agent', event_type: 'started' })];
    rerender(<AgentsCard status={status()} events={after} />);
    expect(screen.getByTestId('live-agent-log_agent')).toBeInTheDocument();
    expect(screen.getByTestId('live-agent-metrics_agent')).toBeInTheDocument();
  });

  it('status dot reflects completed / active / error / pending', () => {
    const events = [
      event({ agent_name: 'log_agent', event_type: 'started' }),
      event({ agent_name: 'log_agent', event_type: 'summary' }),       // complete
      event({ agent_name: 'metrics_agent', event_type: 'started' }),   // active
      event({ agent_name: 'k8s_agent', event_type: 'started' }),
      event({ agent_name: 'k8s_agent', event_type: 'error', message: 'boom' }),
      // change_agent has nothing → pending
    ];
    render(<AgentsCard status={status()} events={events} />);
    const getDot = (agent: string) =>
      screen.getByTestId(`agents-row-${agent}`).querySelector('[role="status"]');
    expect(getDot('log_agent')?.getAttribute('title')).toBe('complete');
    expect(getDot('metrics_agent')?.getAttribute('title')).toBe('active');
    expect(getDot('k8s_agent')?.getAttribute('title')).toBe('error');
    expect(getDot('change_agent')?.getAttribute('title')).toBe('pending');
  });
});
