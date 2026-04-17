import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import HypothesisScoreboard from '../HypothesisScoreboard';
import type { DiagHypothesis } from '../../../types';

function h(
  id: string,
  category: string,
  confidence: number,
  status: DiagHypothesis['status'] = 'active',
  eliminationReason: string | null = null,
): DiagHypothesis {
  return {
    hypothesis_id: id,
    category,
    status,
    confidence,
    evidence_for: [],
    evidence_against: [],
    evidence_for_count: 0,
    evidence_against_count: 0,
    downstream_effects: [],
    elimination_reason: eliminationReason,
    elimination_phase: eliminationReason ? 'reduce' : null,
  };
}

describe('HypothesisScoreboard (top-3)', () => {
  it('renders up to 3 rows when more hypotheses exist', () => {
    const hypotheses = [
      h('h1', 'memory', 82, 'winner'),
      h('h2', 'database', 41, 'eliminated', 'lower confidence by 41 pts'),
      h('h3', 'network', 18, 'eliminated', 'contradicted by k8s evidence'),
      h('h4', 'cpu', 10, 'eliminated', 'no CPU evidence'),
      h('h5', 'config', 5, 'eliminated', 'no config changes'),
    ];
    render(
      <HypothesisScoreboard hypotheses={hypotheses} result={null} legacyGuess={null} />
    );
    // 3 visible rows
    const rowsContainer = screen.getByTestId('hypothesis-scoreboard-rows');
    expect(rowsContainer.children.length).toBe(3);
    // 2 hypotheses not rendered (h4, h5)
    expect(screen.getByText(/2 more hypotheses .* hidden/i)).toBeInTheDocument();
  });

  it('does not render the "more hidden" line when 3 or fewer', () => {
    const hypotheses = [
      h('h1', 'memory', 82, 'winner'),
      h('h2', 'database', 41),
      h('h3', 'network', 18),
    ];
    render(
      <HypothesisScoreboard hypotheses={hypotheses} result={null} legacyGuess={null} />
    );
    expect(screen.queryByText(/more hypothes/i)).toBeNull();
  });

  it('shows elimination reasons for eliminated hypotheses', () => {
    const hypotheses = [
      h('h1', 'memory', 82, 'winner'),
      h('h2', 'database', 41, 'eliminated', 'lower confidence by 41 pts'),
      h('h3', 'network', 18, 'eliminated', 'contradicted by k8s evidence'),
    ];
    render(
      <HypothesisScoreboard hypotheses={hypotheses} result={null} legacyGuess={null} />
    );
    expect(screen.getByText(/lower confidence by 41 pts/)).toBeInTheDocument();
    expect(screen.getByText(/contradicted by k8s evidence/)).toBeInTheDocument();
  });

  it('puts winner row first', () => {
    const hypotheses = [
      h('h2', 'database', 41, 'eliminated', 'lower confidence'),
      h('h1', 'memory', 82, 'winner'),
      h('h3', 'network', 18, 'eliminated', 'contradicted'),
    ];
    render(
      <HypothesisScoreboard hypotheses={hypotheses} result={null} legacyGuess={null} />
    );
    const rows = screen.getByTestId('hypothesis-scoreboard-rows').children;
    // First row contains WINNER badge
    expect(rows[0].textContent).toMatch(/WINNER/);
  });

  it('returns null when no hypotheses and no legacy guess', () => {
    const { container } = render(
      <HypothesisScoreboard hypotheses={[]} result={null} legacyGuess={null} />
    );
    expect(container.firstChild).toBeNull();
  });
});
