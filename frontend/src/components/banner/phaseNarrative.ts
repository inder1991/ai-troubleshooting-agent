import type { TaskEvent, DiagnosticPhase } from '../../types';

/**
 * Commander's Intent voice for the freshness row's phase narrative.
 *
 * Converts raw agent state into plain English — strips underscores,
 * capitalizes agent names as proper nouns, prefers state verbs
 * ("analyzing", "validating") over event verbs ("just landed",
 * "finished"). One short sentence. Italic serif in the render layer.
 *
 * Rules:
 *   · historical / complete: frozen, resolution-oriented
 *   · cancelled: "Investigation paused by operator."
 *   · manual override (handled in render layer): "Awaiting operator input."
 *   · terminal but recent: "Diagnosis complete; fix is pending review."
 *   · active w/ ≥2 agents mid-flight: "Agent A is X while Agent B is Y."
 *   · active w/ 1 agent: "Agent A is X."
 *   · empty / unknown: "Investigation is starting."
 */

// Map backend agent_name → human-readable noun.
const AGENT_LABEL: Record<string, string> = {
  log_agent: 'Log Agent',
  metrics_agent: 'Metrics Agent',
  k8s_agent: 'K8s Probe',
  tracing_agent: 'Trace Walker',
  code_agent: 'Code Navigator',
  change_agent: 'Change Intel',
  critic: 'Critic Ensemble',
  fix_generator: 'Fix Generator',
  supervisor: 'Supervisor',
};

function labelFor(agent: string): string {
  return AGENT_LABEL[agent] ?? agent.replace(/_/g, ' ');
}

// Present-continuous verb derived from the latest event on this agent.
function verbForLatest(event: TaskEvent | undefined): string {
  if (!event) return 'investigating';
  const msg = event.message?.toLowerCase() ?? '';
  if (/(analy[sz]ing|querying|fetching|reading|searching)/.test(msg)) {
    return 'analyzing';
  }
  if (/(validat|verif|cross.?check|reconcil)/.test(msg)) return 'validating';
  if (/(correlat|compar|rank|score)/.test(msg)) return 'reconciling';
  if (/(eliminat|rul[ei]|reject)/.test(msg)) return 'narrowing hypotheses';
  if (/(found|detected|identified)/.test(msg)) return 'reporting findings';
  return 'investigating';
}

/**
 * Group the event stream by agent, determine which agents are still
 * active (started but not terminated). Returns them in start-order.
 */
function deriveActiveAgents(
  events: TaskEvent[],
): Array<{ agent: string; latest: TaskEvent | undefined; startTs: number }> {
  const started = new Map<string, number>(); // agent → start-ts
  const terminated = new Set<string>();
  const latest = new Map<string, TaskEvent>();

  for (const e of events) {
    if (e.agent_name === 'supervisor') continue;
    if (e.event_type === 'started') {
      if (!started.has(e.agent_name)) {
        started.set(e.agent_name, Date.parse(e.timestamp));
      }
    } else if (e.event_type === 'summary' || e.event_type === 'success') {
      terminated.add(e.agent_name);
    }
    latest.set(e.agent_name, e);
  }

  return Array.from(started.entries())
    .filter(([a]) => !terminated.has(a))
    .map(([agent, startTs]) => ({ agent, latest: latest.get(agent), startTs }))
    .sort((a, b) => a.startTs - b.startTs);
}

export interface NarrativeContext {
  events: TaskEvent[];
  phase: DiagnosticPhase | null;
  /** Manual-override (Assume Control) short-circuits the narrative. */
  isManualOverride?: boolean;
  /** Historical incidents get frozen resolution copy. */
  isHistorical?: boolean;
  /** Optional resolution summary for historical copy. */
  resolutionSummary?: string;
}

export function synthesizePhaseNarrative(ctx: NarrativeContext): string {
  if (ctx.isManualOverride) return 'Awaiting operator input.';

  if (ctx.isHistorical) {
    if (ctx.resolutionSummary) {
      return `Incident closed. ${ctx.resolutionSummary}`;
    }
    return 'Incident closed.';
  }

  const phase = ctx.phase;

  if (phase === 'complete') {
    if (ctx.resolutionSummary) {
      return `Incident closed. ${ctx.resolutionSummary}`;
    }
    return 'Incident closed.';
  }
  if (phase === 'diagnosis_complete') {
    return 'Diagnosis complete; fix is pending review.';
  }
  if (phase === 'cancelled') {
    return 'Investigation paused by operator.';
  }
  if (phase === 'error') {
    return 'Investigation hit an unrecoverable error.';
  }

  const active = deriveActiveAgents(ctx.events);
  if (active.length === 0) {
    if (ctx.events.length === 0) return 'Investigation is starting.';
    return 'Awaiting verdict from supervisor.';
  }

  if (active.length === 1) {
    const a = active[0];
    return `${labelFor(a.agent)} is ${verbForLatest(a.latest)}.`;
  }

  // ≥2 active — join the first two with while; trailing truncated.
  const first = active[0];
  const second = active[1];
  const extra = active.length > 2 ? ` (+${active.length - 2} more)` : '';
  return `${labelFor(first.agent)} is ${verbForLatest(first.latest)} while ${labelFor(
    second.agent,
  )} is ${verbForLatest(second.latest)}${extra}.`;
}
