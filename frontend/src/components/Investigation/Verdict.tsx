import React from 'react';
import Balancer from 'react-wrap-balancer';
import type {
  V4Findings,
  TaskEvent,
  DiagHypothesis,
  BlastRadiusData,
} from '../../types';

/**
 * VERDICT (Slot 2) — the editorial interpretation.
 *
 * Deliberately not a card. No label, no border, no confidence badge.
 * Confidence is woven into the prose ("likely", "probably", "unclear")
 * so the sentence itself communicates how sure the system is.
 *
 * Voice rules:
 *   - ≥70%   → "Likely cause — X (N% confidence)."
 *   - 50–69% → "Probably — X (N% confidence)."
 *   - <50%   → "Unclear — X is one possibility (N% confidence)."
 *
 * Data precedence:
 *   1. findings.hypothesis_result.winner_id → resolve in findings.hypotheses[]
 *   2. findings.findings[0]                  (top severity/confidence agent finding)
 *   3. latest `summary` event                (fallback for early investigation)
 *
 * Blast-radius sentence immediately follows VERDICT in the same voice,
 * conditionally rendered when `findings.blast_radius` is present.
 */

interface VerdictProps {
  findings: V4Findings | null;
  events: TaskEvent[];
}

interface VerdictBody {
  text: string;
  confidence: number;
  source: 'hypothesis' | 'finding' | 'event';
}

function humanizeCategory(category: string): string {
  // Category strings come from log-pattern deduplication, so they're often
  // exception-type tokens like "NullPointerException" or
  // "null_pointer_in_payment_flow". Soften to prose.
  const snake = category.replace(/([a-z])([A-Z])/g, '$1 $2').toLowerCase();
  return snake.replace(/_/g, ' ');
}

function resolveVerdict(
  findings: V4Findings | null,
  events: TaskEvent[],
): VerdictBody | null {
  if (!findings) return null;

  // 1. Hypothesis winner
  const winnerId = findings.hypothesis_result?.winner_id;
  if (winnerId) {
    const winner = (findings.hypotheses || []).find(
      (h: DiagHypothesis) => h.hypothesis_id === winnerId,
    );
    if (winner) {
      return {
        text: humanizeCategory(winner.category),
        confidence: winner.confidence,
        source: 'hypothesis',
      };
    }
  }

  // 2. Top finding
  const topFinding = findings.findings?.[0];
  if (topFinding && (topFinding.title || topFinding.summary)) {
    return {
      text: topFinding.title || topFinding.summary || '',
      confidence: topFinding.confidence ?? 0,
      source: 'finding',
    };
  }

  // 3. Latest summary event
  const summaries = events.filter((e) => e.event_type === 'summary' && e.message);
  const last = summaries[summaries.length - 1];
  if (last) {
    return {
      text: last.message,
      confidence: Number(last.details?.confidence ?? 0),
      source: 'event',
    };
  }

  return null;
}

function prefixForConfidence(confidence: number): string {
  if (confidence >= 70) return 'Likely cause —';
  if (confidence >= 50) return 'Probably —';
  return 'Unclear —';
}

function formatVerdict(body: VerdictBody): string {
  const prefix = prefixForConfidence(body.confidence);
  const tail = body.confidence > 0
    ? ` (${Math.round(body.confidence)}% confidence).`
    : '.';
  // For low-confidence framing, soften "X" to "X is one possibility"
  const text = body.confidence < 50
    ? `${body.text} is one possibility`
    : body.text;
  return `${prefix} ${text}${tail}`;
}

// ── Blast radius sentence ────────────────────────────────────────────

function countAffectedServices(blast: BlastRadiusData): number {
  // Count unique services across upstream + downstream + shared. The
  // primary_service is the origin, not "affected by" in the SRE sense.
  const set = new Set<string>();
  (blast.upstream_affected || []).forEach((s) => set.add(s));
  (blast.downstream_affected || []).forEach((s) => set.add(s));
  (blast.shared_resources || []).forEach((s) => set.add(s));
  return set.size;
}

function formatBlastRadius(blast: BlastRadiusData): string | null {
  const clauses: string[] = [];

  const count = countAffectedServices(blast);
  if (count > 0) {
    clauses.push(`Affects ${count} service${count === 1 ? '' : 's'}`);
  }

  const userImpact = (blast.estimated_user_impact || '').trim();
  if (userImpact) {
    // The backend gives prose like "thousands of users". Weave it in without
    // a colon to keep it one sentence.
    clauses.push(userImpact);
  }

  if (clauses.length === 0) return null;

  // Capitalize first clause's first letter (in case user_impact came first
  // and is lowercase).
  const first = clauses[0];
  clauses[0] = first.charAt(0).toUpperCase() + first.slice(1);

  return `${clauses.join('; ')}.`;
}

// ── Component ────────────────────────────────────────────────────────

const Verdict: React.FC<VerdictProps> = ({ findings, events }) => {
  const body = resolveVerdict(findings, events);

  if (!body) {
    return (
      <div className="px-6 pt-10 pb-6" data-testid="verdict">
        <p className="font-editorial italic text-wr-text-muted text-[14px] leading-[1.45]">
          <Balancer>
            No interpretation yet — agents are still gathering evidence.
          </Balancer>
        </p>
      </div>
    );
  }

  const blast = findings?.blast_radius ?? null;
  const blastSentence = blast ? formatBlastRadius(blast) : null;

  return (
    <div
      className="px-6 pt-10 pb-6 space-y-3"
      data-testid="verdict"
      data-source={body.source}
    >
      <p
        className="font-editorial italic text-wr-paper leading-[1.45]"
        style={{ fontSize: 'clamp(17px, 1.2vw, 20px)' }}
      >
        <Balancer>{formatVerdict(body)}</Balancer>
      </p>
      {blastSentence && (
        <p
          className="font-editorial italic text-wr-paper/75 text-[14px] leading-[1.45]"
          data-testid="blast-radius"
        >
          <Balancer>{blastSentence}</Balancer>
        </p>
      )}
    </div>
  );
};

export default Verdict;
