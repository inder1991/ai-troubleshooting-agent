/**
 * AgentCircuitIndicator — small circle showing per-agent breaker state.
 *
 * Backend source: the per-backend circuit breakers registered by Task 3.4's
 * @with_circuit_breaker decorator. State mapping:
 *   closed   = breaker healthy, requests flowing
 *   half_open = recovery probe window
 *   open     = requests being fast-failed
 */
export type CircuitState = 'closed' | 'half_open' | 'open';

export interface AgentCircuitIndicatorProps {
  agent: string;
  state: CircuitState;
}

const TONE: Record<CircuitState, string> = {
  closed: 'text-wr-emerald border-wr-emerald/50 bg-wr-emerald/10',
  half_open: 'text-wr-amber border-wr-amber/50 bg-wr-amber/10',
  open: 'text-wr-red border-wr-red/50 bg-wr-red/10',
};

const LABEL: Record<CircuitState, string> = {
  closed: 'CLOSED',
  half_open: 'HALF',
  open: 'OPEN',
};

export function AgentCircuitIndicator({
  agent,
  state,
}: AgentCircuitIndicatorProps) {
  return (
    <span
      data-testid={`breaker-${agent}`}
      className={`inline-flex items-center gap-1 rounded-full border px-1.5 py-0 text-[10px] font-mono uppercase tracking-wider ${TONE[state]}`}
      title={`${agent} circuit: ${state}`}
    >
      <span
        className={`w-1.5 h-1.5 rounded-full ${
          state === 'open'
            ? 'bg-wr-red'
            : state === 'half_open'
              ? 'bg-wr-amber'
              : 'bg-wr-emerald'
        }`}
        aria-hidden
      />
      {LABEL[state]}
    </span>
  );
}
