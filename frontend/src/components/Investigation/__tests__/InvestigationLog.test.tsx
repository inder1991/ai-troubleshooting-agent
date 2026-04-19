import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import InvestigationLog from '../InvestigationLog';
import type {
  TaskEvent,
  V4Findings,
  V4SessionStatus,
  Breadcrumb,
  ReasoningChainStep,
} from '../../../types';

function event(over: Partial<TaskEvent> = {}): TaskEvent {
  return {
    timestamp: '2026-04-19T00:00:00Z',
    agent_name: 'log_agent',
    event_type: 'started',
    message: 'starting log analysis',
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

function findings(over: Partial<V4Findings> = {}): V4Findings {
  return { session_id: 's', findings: [], ...over };
}

describe('InvestigationLog', () => {
  // ── Empty state ─────────────────────────────────────────────────

  it('renders empty-state prose when no events', () => {
    render(<InvestigationLog events={[]} findings={findings()} status={status()} />);
    expect(screen.getByTestId('log-empty').textContent).toMatch(
      /waiting for the first agent to report/i,
    );
  });

  // ── Phase rendering ─────────────────────────────────────────────

  it('renders one phase with small-caps label when a phase_change lands', () => {
    const events = [
      event({ event_type: 'phase_change', message: 'logs_analyzed', details: { phase: 'logs_analyzed' } }),
      event({ event_type: 'started', agent_name: 'log_agent' }),
      event({ event_type: 'summary', agent_name: 'log_agent', message: 'done' }),
    ];
    render(<InvestigationLog events={events} findings={findings()} status={status()} />);
    const phase = screen.getByTestId('phase-logs_analyzed');
    const header = phase.querySelector('header');
    expect(header).not.toBeNull();
    // small-caps, not UPPERCASE CSS
    expect(header?.textContent?.toLowerCase()).toMatch(/logs analyzed/);
    expect(header?.getAttribute('style')).toMatch(/font-variant:\s*small-caps/);
  });

  it('renders agent capsule with 2px agent-identity left-border', () => {
    const events = [
      event({ event_type: 'phase_change', message: 'logs_analyzed', details: { phase: 'logs_analyzed' } }),
      event({ event_type: 'started', agent_name: 'log_agent' }),
      event({ event_type: 'finding', agent_name: 'log_agent', message: 'NullPointerException × 12' }),
      event({ event_type: 'summary', agent_name: 'log_agent', message: 'done' }),
    ];
    render(<InvestigationLog events={events} findings={findings()} status={status()} />);
    const capsule = screen.getByTestId('capsule-log_agent');
    // Agent red identity color (jsdom normalises hex → rgb)
    expect(capsule.getAttribute('style')).toMatch(
      /border-left:\s*2px\s+solid\s+(?:#ef4444|rgb\(239,\s*68,\s*68\))/i,
    );
  });

  it('renders finding lines under the capsule header', () => {
    const events = [
      event({ event_type: 'phase_change', message: 'logs_analyzed', details: { phase: 'logs_analyzed' } }),
      event({ event_type: 'started', agent_name: 'log_agent' }),
      event({ event_type: 'finding', agent_name: 'log_agent', message: 'NullPointerException × 12' }),
      event({ event_type: 'finding', agent_name: 'log_agent', message: 'retry_storm detected' }),
      event({ event_type: 'summary', agent_name: 'log_agent', message: 'done' }),
    ];
    render(<InvestigationLog events={events} findings={findings()} status={status()} />);
    expect(screen.getByText('NullPointerException × 12')).toBeInTheDocument();
    expect(screen.getByText('retry_storm detected')).toBeInTheDocument();
  });

  // ── Live breadcrumb ─────────────────────────────────────────────

  it('renders live breadcrumb for the active (in-progress) agent', () => {
    const events = [
      event({ event_type: 'phase_change', message: 'k8s_analyzed', details: { phase: 'k8s_analyzed' } }),
      event({ event_type: 'started', agent_name: 'k8s_agent' }),
      // no summary yet — agent still in progress
    ];
    const bc: Breadcrumb[] = [{
      timestamp: '2026-04-19T00:00:00Z',
      agent_name: 'k8s_agent',
      action: 'querying pods in checkout-prod namespace',
      detail: '',
    }];
    render(<InvestigationLog events={events} findings={findings()} status={status({ breadcrumbs: bc })} />);
    expect(screen.getByTestId('live-line-k8s_agent').textContent).toMatch(
      /querying pods in checkout-prod namespace/,
    );
  });

  it('falls back to progress event when no breadcrumbs', () => {
    const events = [
      event({ event_type: 'phase_change', message: 'k8s_analyzed', details: { phase: 'k8s_analyzed' } }),
      event({ event_type: 'started', agent_name: 'k8s_agent' }),
      event({ event_type: 'progress', agent_name: 'k8s_agent', message: 'examining pod logs' }),
    ];
    render(<InvestigationLog events={events} findings={findings()} status={status()} />);
    expect(screen.getByTestId('live-line-k8s_agent').textContent).toMatch(/examining pod logs/);
  });

  it('falls back to "gathering…" when no breadcrumb or progress', () => {
    const events = [
      event({ event_type: 'phase_change', message: 'k8s_analyzed', details: { phase: 'k8s_analyzed' } }),
      event({ event_type: 'started', agent_name: 'k8s_agent' }),
    ];
    render(<InvestigationLog events={events} findings={findings()} status={status()} />);
    expect(screen.getByTestId('live-line-k8s_agent').textContent).toMatch(/gathering/);
  });

  it('does not render live breadcrumb for a completed agent', () => {
    const events = [
      event({ event_type: 'phase_change', message: 'logs_analyzed', details: { phase: 'logs_analyzed' } }),
      event({ event_type: 'started', agent_name: 'log_agent' }),
      event({ event_type: 'summary', agent_name: 'log_agent', message: 'done' }),
    ];
    const bc: Breadcrumb[] = [{
      timestamp: '2026-04-19T00:00:00Z',
      agent_name: 'log_agent',
      action: 'should not appear',
      detail: '',
    }];
    render(<InvestigationLog events={events} findings={findings()} status={status({ breadcrumbs: bc })} />);
    expect(screen.queryByTestId('live-line-log_agent')).toBeNull();
  });

  // ── Cross-check entries ─────────────────────────────────────────

  it('renders cross-check completion as a first-class timeline entry', () => {
    const events = [
      event({ event_type: 'phase_change', message: 'metrics_analyzed', details: { phase: 'metrics_analyzed' } }),
      event({ event_type: 'started', agent_name: 'metrics_agent' }),
      event({ event_type: 'summary', agent_name: 'metrics_agent', message: 'done' }),
      event({
        event_type: 'summary',
        agent_name: 'supervisor',
        message: 'cross-check: metrics ↔ logs — 2 signal disagreements',
        details: {
          action: 'cross_check_complete',
          cross_check: 'metrics_logs',
          divergence_count: 2,
        },
      }),
    ];
    render(<InvestigationLog events={events} findings={findings()} status={status()} />);
    const entry = screen.getByTestId('cross-check-metrics_logs');
    // Strips the "cross-check: " prefix to avoid redundancy with small-caps phase label
    expect(entry.textContent).toMatch(/metrics.*logs.*2 signal disagreements/i);
    expect(entry.textContent).not.toMatch(/^cross-check:/);
  });

  // ── Filter toolbar (editorial text links) ───────────────────────

  it('renders three filter links (no pills, no mono)', () => {
    const events = [
      event({ event_type: 'phase_change', message: 'logs_analyzed', details: { phase: 'logs_analyzed' } }),
      event({ event_type: 'started', agent_name: 'log_agent' }),
      event({ event_type: 'summary', agent_name: 'log_agent', message: 'done' }),
    ];
    render(<InvestigationLog events={events} findings={findings()} status={status()} />);
    expect(screen.getByTestId('filter-all')).toBeInTheDocument();
    expect(screen.getByTestId('filter-findings')).toBeInTheDocument();
    expect(screen.getByTestId('filter-raw')).toBeInTheDocument();
    // All three in one italic serif wrap
    const wrap = screen.getByTestId('filter-all').parentElement;
    expect(wrap?.className).toMatch(/font-editorial/);
    expect(wrap?.className).toMatch(/italic/);
  });

  it('active filter gets underline via aria-pressed', () => {
    const events = [
      event({ event_type: 'phase_change', message: 'logs_analyzed', details: { phase: 'logs_analyzed' } }),
      event({ event_type: 'started', agent_name: 'log_agent' }),
      event({ event_type: 'summary', agent_name: 'log_agent', message: 'done' }),
    ];
    render(<InvestigationLog events={events} findings={findings()} status={status()} />);
    expect(screen.getByTestId('filter-all').getAttribute('aria-pressed')).toBe('true');
    fireEvent.click(screen.getByTestId('filter-findings'));
    expect(screen.getByTestId('filter-findings').getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByTestId('filter-all').getAttribute('aria-pressed')).toBe('false');
  });

  // ── Reasoning disclosure ────────────────────────────────────────

  it('renders reasoning disclosure when chain present, default collapsed', () => {
    const events = [
      event({ event_type: 'phase_change', message: 'logs_analyzed', details: { phase: 'logs_analyzed' } }),
      event({ event_type: 'started', agent_name: 'log_agent' }),
    ];
    const chain: ReasoningChainStep[] = [
      { step: 1, observation: 'saw errors', inference: 'looks like NPE' },
      { step: 2, observation: 'scoped to checkout', inference: 'isolated blast radius' },
    ];
    render(<InvestigationLog events={events} findings={findings({ reasoning_chain: chain })} status={status()} />);
    const trigger = screen.getByTestId('reasoning-trigger');
    expect(trigger.getAttribute('aria-expanded')).toBe('false');
    expect(trigger.textContent).toMatch(/how the system thought about it \(2 moves\)/i);
  });

  it('reasoning disclosure does not render when chain empty', () => {
    const events = [event({ event_type: 'started', agent_name: 'log_agent' })];
    render(<InvestigationLog events={events} findings={findings({ reasoning_chain: [] })} status={status()} />);
    expect(screen.queryByTestId('reasoning-disclosure')).toBeNull();
  });

  // ── Anti-pattern guards ─────────────────────────────────────────

  it('is not a card-grid — no rounded log containers, no severity bg fills', () => {
    const events = [
      event({ event_type: 'phase_change', message: 'logs_analyzed', details: { phase: 'logs_analyzed' } }),
      event({ event_type: 'started', agent_name: 'log_agent' }),
      event({ event_type: 'summary', agent_name: 'log_agent', message: 'done' }),
    ];
    render(<InvestigationLog events={events} findings={findings()} status={status()} />);
    const log = screen.getByTestId('investigation-log');
    expect(log.innerHTML).not.toMatch(/class="[^"]*rounded-lg[^"]*"/);
    expect(log.innerHTML).not.toMatch(/bg-wr-severity-/);
    expect(log.innerHTML).not.toMatch(/shadow-glow/);
  });

  it('no cyan in log header, no amber in filter chrome', () => {
    const events = [
      event({ event_type: 'phase_change', message: 'logs_analyzed', details: { phase: 'logs_analyzed' } }),
      event({ event_type: 'started', agent_name: 'log_agent' }),
    ];
    render(<InvestigationLog events={events} findings={findings()} status={status()} />);
    const html = screen.getByTestId('investigation-log').innerHTML;
    expect(html).not.toMatch(/wr-accent-2/);
    expect(html).not.toMatch(/text-amber-/);
    expect(html).not.toMatch(/text-cyan-/);
  });

  it('phase header uses small-caps, not uppercase CSS', () => {
    const events = [
      event({ event_type: 'phase_change', message: 'logs_analyzed', details: { phase: 'logs_analyzed' } }),
      event({ event_type: 'started', agent_name: 'log_agent' }),
    ];
    render(<InvestigationLog events={events} findings={findings()} status={status()} />);
    const phase = screen.getByTestId('phase-logs_analyzed');
    const header = phase.querySelector('header');
    expect(header?.className).not.toMatch(/uppercase/);
    expect(header?.className).not.toMatch(/tracking-widest/);
    expect(header?.getAttribute('style')).toMatch(/small-caps/);
  });
});
