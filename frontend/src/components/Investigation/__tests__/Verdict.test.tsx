import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import Verdict from '../Verdict';
import type {
  V4Findings,
  Finding,
  DiagHypothesis,
  DiagHypothesisResult,
  BlastRadiusData,
  TaskEvent,
} from '../../../types';

function findings(over: Partial<V4Findings> = {}): V4Findings {
  return {
    session_id: 's',
    findings: [],
    ...over,
  };
}

function hypothesis(over: Partial<DiagHypothesis> = {}): DiagHypothesis {
  return {
    hypothesis_id: 'h1',
    category: 'null pointer in PaymentController',
    status: 'winner',
    confidence: 72,
    evidence_for: [],
    evidence_against: [],
    evidence_for_count: 0,
    evidence_against_count: 0,
    downstream_effects: [],
    elimination_reason: null,
    elimination_phase: null,
    ...over,
  };
}

function topFinding(over: Partial<Finding> = {}): Finding {
  return {
    finding_id: 'f1',
    agent_name: 'log_agent',
    category: 'error_pattern',
    title: 'checkout-service throwing NPE',
    description: 'details',
    summary: 'checkout-service throwing NPE',
    severity: 'high',
    confidence: 65,
    ...over,
  } as Finding;
}

function event(over: Partial<TaskEvent> = {}): TaskEvent {
  return {
    timestamp: '2026-04-19T00:00:00Z',
    agent_name: 'supervisor',
    event_type: 'summary',
    message: 'the system landed here',
    ...over,
  } as TaskEvent;
}

describe('Verdict', () => {
  // ── Empty ────────────────────────────────────────────────────────

  it('renders fallback line when findings is null and no events', () => {
    render(<Verdict findings={null} events={[]} />);
    expect(screen.getByText(/no interpretation yet/i)).toBeInTheDocument();
  });

  it('renders fallback line when findings has no derivable sentence', () => {
    render(<Verdict findings={findings()} events={[]} />);
    expect(screen.getByText(/no interpretation yet/i)).toBeInTheDocument();
  });

  // ── Precedence ───────────────────────────────────────────────────

  it('prefers hypothesis winner over top finding', () => {
    const hypoResult: DiagHypothesisResult = {
      status: 'resolved',
      winner_id: 'h1',
      elimination_log: [],
      recommendations: [],
    };
    render(
      <Verdict
        findings={findings({
          hypothesis_result: hypoResult,
          hypotheses: [hypothesis({ category: 'null_pointer_in_payment_flow', confidence: 72 })],
          findings: [topFinding({ title: 'DIFFERENT: top finding title' })],
        })}
        events={[]}
      />,
    );
    // Winner wins, finding loses
    expect(screen.getByText(/null pointer in payment flow/i)).toBeInTheDocument();
    expect(screen.queryByText(/DIFFERENT:/)).toBeNull();
  });

  it('prefers top finding when its confidence exceeds the hypothesis winner (PR-C precedence fix)', () => {
    const hypoResult: DiagHypothesisResult = {
      status: 'resolved',
      winner_id: 'h1',
      elimination_log: [],
      recommendations: [],
    };
    render(
      <Verdict
        findings={findings({
          hypothesis_result: hypoResult,
          hypotheses: [hypothesis({ category: 'weak_hypothesis_winner', confidence: 55 })],
          findings: [topFinding({ title: 'AGENT FINDING — stronger signal', confidence: 92 })],
        })}
        events={[]}
      />,
    );
    expect(screen.getByText(/AGENT FINDING — stronger signal/)).toBeInTheDocument();
    expect(screen.queryByText(/weak hypothesis winner/)).toBeNull();
    // Verdict block carries data-source="finding" in the high-confidence branch
    const verdict = screen.getByTestId('verdict');
    expect(verdict.getAttribute('data-source')).toBe('finding');
  });

  it('breaks confidence ties toward hypothesis winner', () => {
    const hypoResult: DiagHypothesisResult = {
      status: 'resolved',
      winner_id: 'h1',
      elimination_log: [],
      recommendations: [],
    };
    render(
      <Verdict
        findings={findings({
          hypothesis_result: hypoResult,
          hypotheses: [hypothesis({ category: 'hypothesis_wins_on_tie', confidence: 72 })],
          findings: [topFinding({ title: 'top finding tied', confidence: 72 })],
        })}
        events={[]}
      />,
    );
    expect(screen.getByText(/hypothesis wins on tie/)).toBeInTheDocument();
    const verdict = screen.getByTestId('verdict');
    expect(verdict.getAttribute('data-source')).toBe('hypothesis');
  });

  it('falls back to top finding when no hypothesis winner', () => {
    render(
      <Verdict
        findings={findings({
          findings: [topFinding({ title: 'checkout-service throwing NPE', confidence: 75 })],
        })}
        events={[]}
      />,
    );
    expect(screen.getByText(/checkout-service throwing NPE/i)).toBeInTheDocument();
  });

  it('falls back to latest summary event when no findings or hypotheses', () => {
    render(
      <Verdict
        findings={findings()}
        events={[
          event({ message: 'earlier summary' }),
          event({ message: 'the latest summary' }),
        ]}
      />,
    );
    expect(screen.getByText(/the latest summary/i)).toBeInTheDocument();
  });

  // ── Confidence voice mapping ─────────────────────────────────────

  it('prefix "Likely cause" when confidence >= 70', () => {
    const hypoResult: DiagHypothesisResult = {
      status: 'resolved', winner_id: 'h1', elimination_log: [], recommendations: [],
    };
    render(<Verdict
      findings={findings({
        hypothesis_result: hypoResult,
        hypotheses: [hypothesis({ confidence: 78 })],
      })}
      events={[]}
    />);
    expect(screen.getByText(/Likely cause —/)).toBeInTheDocument();
  });

  it('prefix "Probably" when confidence 50–69', () => {
    const hypoResult: DiagHypothesisResult = {
      status: 'resolved', winner_id: 'h1', elimination_log: [], recommendations: [],
    };
    render(<Verdict
      findings={findings({
        hypothesis_result: hypoResult,
        hypotheses: [hypothesis({ confidence: 58 })],
      })}
      events={[]}
    />);
    expect(screen.getByText(/Probably —/)).toBeInTheDocument();
  });

  it('prefix "Unclear" when confidence < 50', () => {
    const hypoResult: DiagHypothesisResult = {
      status: 'resolved', winner_id: 'h1', elimination_log: [], recommendations: [],
    };
    render(<Verdict
      findings={findings({
        hypothesis_result: hypoResult,
        hypotheses: [hypothesis({ confidence: 35 })],
      })}
      events={[]}
    />);
    expect(screen.getByText(/Unclear —/)).toBeInTheDocument();
    expect(screen.getByText(/is one possibility/)).toBeInTheDocument();
  });

  // ── Blast radius ─────────────────────────────────────────────────

  it('renders blast radius sentence when data is present', () => {
    const blast: BlastRadiusData = {
      primary_service: 'checkout-service',
      upstream_affected: ['auth-service'],
      downstream_affected: ['payments-api', 'notification-svc'],
      shared_resources: [],
      estimated_user_impact: 'thousands of users',
      scope: 'service_group',
    };
    render(<Verdict
      findings={findings({
        blast_radius: blast,
        findings: [topFinding()],
      })}
      events={[]}
    />);
    expect(screen.getByTestId('blast-radius')).toBeInTheDocument();
    expect(screen.getByTestId('blast-radius').textContent).toMatch(/Affects 3 services/);
    expect(screen.getByTestId('blast-radius').textContent).toMatch(/thousands of users/);
  });

  it('drops blast radius entirely when all clauses absent', () => {
    const blast: BlastRadiusData = {
      primary_service: 'x',
      upstream_affected: [],
      downstream_affected: [],
      shared_resources: [],
      estimated_user_impact: '',
      scope: 'single_service',
    };
    render(<Verdict
      findings={findings({ blast_radius: blast, findings: [topFinding()] })}
      events={[]}
    />);
    expect(screen.queryByTestId('blast-radius')).toBeNull();
  });

  it('handles singular vs plural service count', () => {
    const blast: BlastRadiusData = {
      primary_service: 'x',
      upstream_affected: ['a'],
      downstream_affected: [],
      shared_resources: [],
      estimated_user_impact: '',
      scope: 'single_service',
    };
    render(<Verdict
      findings={findings({ blast_radius: blast, findings: [topFinding()] })}
      events={[]}
    />);
    expect(screen.getByTestId('blast-radius').textContent).toMatch(/Affects 1 service\b/);
  });

  // ── Anti-pattern guards (editorial discipline) ────────────────────

  it('is not a card — no border, no rounded, no bg-wr-severity', () => {
    render(<Verdict
      findings={findings({ findings: [topFinding()] })}
      events={[]}
    />);
    const verdict = screen.getByTestId('verdict');
    expect(verdict.className).not.toMatch(/rounded-/);
    expect(verdict.className).not.toMatch(/bg-wr-severity/);
    // Border-l-* is allowed (agent-identity); border-(r|t|b) not allowed
    expect(verdict.className).not.toMatch(/border-r/);
    expect(verdict.className).not.toMatch(/border-t/);
    expect(verdict.className).not.toMatch(/border-b/);
  });

  it('uses font-editorial for hero text (Fraunces)', () => {
    render(<Verdict findings={findings({ findings: [topFinding()] })} events={[]} />);
    // The verdict sentence <p> should carry font-editorial
    const p = screen.getByTestId('verdict').querySelector('p');
    expect(p?.className).toMatch(/font-editorial/);
    expect(p?.className).toMatch(/italic/);
  });

  it('no font-mono anywhere in the component', () => {
    render(<Verdict findings={findings({ findings: [topFinding()] })} events={[]} />);
    const all = screen.getByTestId('verdict').innerHTML;
    expect(all).not.toMatch(/font-mono/);
  });

  it('no all-caps / tracking-widest labels', () => {
    render(<Verdict findings={findings({ findings: [topFinding()] })} events={[]} />);
    const all = screen.getByTestId('verdict').innerHTML;
    expect(all).not.toMatch(/uppercase/);
    expect(all).not.toMatch(/tracking-widest/);
    expect(all).not.toMatch(/VERDICT/);
  });
});
