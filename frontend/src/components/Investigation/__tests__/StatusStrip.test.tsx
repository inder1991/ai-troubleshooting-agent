import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import StatusStrip from '../StatusStrip';
import type {
  V4Findings,
  V4SessionStatus,
  WinnerCriticDissent,
  DivergenceFinding,
} from '../../../types';

function findings(over: Partial<V4Findings> = {}): V4Findings {
  return { session_id: 's', findings: [], ...over };
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

function dissent(): WinnerCriticDissent {
  return {
    advocate_verdict: 'confirmed',
    challenger_verdict: 'challenged',
    judge_verdict: 'needs_more_evidence',
    summary: 'the evidence is suggestive but not conclusive',
  };
}

function divergence(kind: DivergenceFinding['kind'] = 'metric_anomaly_no_error_logs'): DivergenceFinding {
  return {
    kind,
    severity: 'medium',
    human_summary: 'm',
    service_name: 'x',
    metadata: {},
  };
}

describe('StatusStrip', () => {
  // ── Render gating ────────────────────────────────────────────────

  it('renders nothing when findings is null', () => {
    const { container } = render(<StatusStrip findings={null} status={null} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing when all three signals are absent', () => {
    const { container } = render(
      <StatusStrip findings={findings()} status={status()} />,
    );
    expect(container.firstChild).toBeNull();
  });

  // ── Clause rendering ─────────────────────────────────────────────

  it('renders gaps clause with singular text when 1 gap', () => {
    render(
      <StatusStrip
        findings={findings()}
        status={status({ coverage_gaps: ['metrics_agent: prometheus down'] })}
      />,
    );
    expect(screen.getByText(/1 data source missing/i)).toBeInTheDocument();
  });

  it('renders gaps clause with plural text when multiple gaps', () => {
    render(
      <StatusStrip
        findings={findings()}
        status={status({ coverage_gaps: ['a', 'b', 'c'] })}
      />,
    );
    expect(screen.getByText(/3 data sources missing/i)).toBeInTheDocument();
  });

  it('renders critic dissent clause when dissent present', () => {
    render(
      <StatusStrip
        findings={findings()}
        status={status({ winner_critic_dissent: dissent() })}
      />,
    );
    expect(screen.getByText(/critic disagreed/i)).toBeInTheDocument();
  });

  it('renders divergence clause with singular/plural', () => {
    const { rerender } = render(
      <StatusStrip
        findings={findings({ divergence_findings: [divergence()] })}
        status={status()}
      />,
    );
    expect(screen.getByText(/1 signal contradict/i)).toBeInTheDocument();
    rerender(
      <StatusStrip
        findings={findings({ divergence_findings: [divergence(), divergence()] })}
        status={status()}
      />,
    );
    expect(screen.getByText(/2 signals contradict/i)).toBeInTheDocument();
  });

  it('drops clauses independently when data missing', () => {
    render(
      <StatusStrip
        findings={findings({ divergence_findings: [divergence()] })}
        status={status()}  // no gaps, no dissent
      />,
    );
    expect(screen.queryByText(/data source/i)).toBeNull();
    expect(screen.queryByText(/critic disagreed/)).toBeNull();
    expect(screen.getByText(/1 signal contradict/i)).toBeInTheDocument();
  });

  // ── Interaction ──────────────────────────────────────────────────

  it('gaps clause is a Radix Accordion trigger (aria-expanded)', () => {
    render(
      <StatusStrip
        findings={findings()}
        status={status({ coverage_gaps: ['metrics_agent: down'] })}
      />,
    );
    const trigger = screen.getByTestId('clause-gaps');
    expect(trigger.getAttribute('aria-expanded')).toBe('false');
    fireEvent.click(trigger);
    expect(trigger.getAttribute('aria-expanded')).toBe('true');
  });

  it('divergence clause is a plain button that does NOT expand inline', () => {
    const scrollSpy = vi.fn();
    Element.prototype.scrollIntoView = scrollSpy;

    render(
      <StatusStrip
        findings={findings({ divergence_findings: [divergence()] })}
        status={status()}
      />,
    );
    const btn = screen.getByTestId('clause-divergence');
    // No aria-expanded (it's a scroll trigger, not an accordion)
    expect(btn.getAttribute('aria-expanded')).toBeNull();
    fireEvent.click(btn);
    // No target in DOM — scroll is a no-op but shouldn't throw
  });

  it('opening one accordion closes another (mutually exclusive)', () => {
    render(
      <StatusStrip
        findings={findings()}
        status={status({
          coverage_gaps: ['a'],
          winner_critic_dissent: dissent(),
        })}
      />,
    );
    const gaps = screen.getByTestId('clause-gaps');
    const dissentBtn = screen.getByTestId('clause-dissent');
    fireEvent.click(gaps);
    expect(gaps.getAttribute('aria-expanded')).toBe('true');
    fireEvent.click(dissentBtn);
    expect(gaps.getAttribute('aria-expanded')).toBe('false');
    expect(dissentBtn.getAttribute('aria-expanded')).toBe('true');
  });

  // ── Anti-pattern guards ─────────────────────────────────────────

  it('is not a card — no border-b, no rounded, no bg-wr-severity', () => {
    render(
      <StatusStrip
        findings={findings({ divergence_findings: [divergence()] })}
        status={status()}
      />,
    );
    const strip = screen.getByTestId('status-strip');
    expect(strip.className).not.toMatch(/rounded-/);
    expect(strip.className).not.toMatch(/bg-wr-severity/);
    expect(strip.className).not.toMatch(/border-b/);
  });

  it('uses font-editorial italic, no mono, no uppercase', () => {
    render(
      <StatusStrip
        findings={findings({ divergence_findings: [divergence()] })}
        status={status()}
      />,
    );
    const strip = screen.getByTestId('status-strip');
    const para = strip.querySelector('p');
    expect(para?.className).toMatch(/font-editorial/);
    expect(para?.className).toMatch(/italic/);
    expect(strip.innerHTML).not.toMatch(/font-mono/);
    expect(strip.innerHTML).not.toMatch(/uppercase/);
    expect(strip.innerHTML).not.toMatch(/tracking-widest/);
  });

  it('no glyphs — no ⦿, no icons', () => {
    render(
      <StatusStrip
        findings={findings({ divergence_findings: [divergence()] })}
        status={status({ coverage_gaps: ['a'], winner_critic_dissent: dissent() })}
      />,
    );
    const strip = screen.getByTestId('status-strip');
    expect(strip.innerHTML).not.toMatch(/⦿/);
    expect(strip.innerHTML).not.toMatch(/material-symbols/);
  });
});
