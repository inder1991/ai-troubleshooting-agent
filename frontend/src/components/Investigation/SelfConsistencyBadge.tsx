/**
 * SelfConsistencyBadge — shows N/N agreement after a self-consistency run.
 *
 * - Hides entirely when nRuns <= 1 (feature was off).
 * - Emerald when all runs agreed.
 * - Amber when it was a partial majority (penalty applied).
 * - Red when no majority emerged (inconclusive).
 */
export interface SelfConsistencyBadgeProps {
  nRuns: number;
  agreedCount: number;
  penaltyPct: number;
}

export function SelfConsistencyBadge({
  nRuns,
  agreedCount,
  penaltyPct,
}: SelfConsistencyBadgeProps) {
  if (nRuns <= 1) return null;

  const unanimous = agreedCount === nRuns;
  const majority = !unanimous && agreedCount > nRuns / 2;

  const tone = unanimous
    ? 'text-wr-emerald border-wr-emerald/40 bg-wr-emerald/10'
    : majority
      ? 'text-wr-amber border-wr-amber/40 bg-wr-amber/10'
      : 'text-wr-red border-wr-red/40 bg-wr-red/10';

  const suffix = unanimous
    ? ''
    : majority
      ? ` (-${penaltyPct}% conf)`
      : ' (inconclusive)';

  return (
    <span
      data-testid="self-consistency-badge"
      className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-mono ${tone}`}
      title="Self-consistency: investigation re-run with shuffled agent order"
    >
      {agreedCount}/{nRuns} agree{suffix}
    </span>
  );
}
