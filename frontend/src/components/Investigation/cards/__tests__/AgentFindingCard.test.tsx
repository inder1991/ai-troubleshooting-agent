import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import AgentFindingCard from '../AgentFindingCard';

describe('AgentFindingCard — decorations (Task 4.15)', () => {
  it('renders baseline strip when delta present', () => {
    render(
      <AgentFindingCard
        agent="M"
        title="error rate spike"
        baselineValue={80}
        baselineDeltaPct={125}
      >
        body
      </AgentFindingCard>,
    );
    expect(screen.getByText(/\+125% vs 24h baseline/i)).toBeInTheDocument();
    expect(screen.getByText(/was 80/)).toBeInTheDocument();
  });

  it('renders signature pill when pattern matched', () => {
    render(
      <AgentFindingCard
        agent="L"
        title="OOM detected"
        signatureMatch={{ pattern_name: 'OOM Cascade', matched_at_ms: 400 }}
      >
        body
      </AgentFindingCard>,
    );
    expect(screen.getByText(/Pattern: OOM Cascade/)).toBeInTheDocument();
    expect(screen.getByText(/0\.4s/)).toBeInTheDocument();
  });

  it('renders no decorations when neither present', () => {
    render(
      <AgentFindingCard agent="L" title="basic finding">
        body
      </AgentFindingCard>,
    );
    expect(screen.queryByText(/baseline/i)).toBeNull();
    expect(screen.queryByText(/Pattern:/)).toBeNull();
  });

  it('baseline tone is emerald within 3% tolerance', () => {
    render(
      <AgentFindingCard
        agent="M"
        title="cpu within noise"
        baselineValue={80}
        baselineDeltaPct={2}
      >
        body
      </AgentFindingCard>,
    );
    const strip = screen.getByTestId('baseline-strip');
    expect(strip.className).toMatch(/wr-emerald/);
  });

  it('baseline tone is amber at medium deviation', () => {
    render(
      <AgentFindingCard
        agent="M"
        title="cpu slightly hot"
        baselineValue={80}
        baselineDeltaPct={30}
      >
        body
      </AgentFindingCard>,
    );
    const strip = screen.getByTestId('baseline-strip');
    expect(strip.className).toMatch(/wr-amber/);
  });

  it('baseline tone is red at large deviation', () => {
    render(
      <AgentFindingCard
        agent="M"
        title="cpu runaway"
        baselineValue={80}
        baselineDeltaPct={125}
      >
        body
      </AgentFindingCard>,
    );
    const strip = screen.getByTestId('baseline-strip');
    expect(strip.className).toMatch(/wr-red/);
  });

  it('shows critic dissent icon when verdicts disagree', () => {
    render(
      <AgentFindingCard
        agent="L"
        title="finding"
        criticDissent={{
          advocate_verdict: 'confirmed',
          challenger_verdict: 'challenged',
          judge_verdict: 'needs_more_evidence',
        }}
      >
        body
      </AgentFindingCard>,
    );
    expect(screen.getByLabelText(/critic disagreement/i)).toBeInTheDocument();
  });

  it('hides dissent icon when verdicts agree', () => {
    render(
      <AgentFindingCard
        agent="L"
        title="finding"
        criticDissent={{
          advocate_verdict: 'confirmed',
          challenger_verdict: 'confirmed',
          judge_verdict: 'confirmed',
        }}
      >
        body
      </AgentFindingCard>,
    );
    expect(screen.queryByLabelText(/critic disagreement/i)).toBeNull();
  });

  it('formats negative baseline delta without forced "+" sign', () => {
    render(
      <AgentFindingCard
        agent="M"
        title="rps dropped"
        baselineValue={1000}
        baselineDeltaPct={-40}
      >
        body
      </AgentFindingCard>,
    );
    expect(screen.getByText(/-40% vs 24h baseline/)).toBeInTheDocument();
  });
});
