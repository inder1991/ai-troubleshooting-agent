import React, { useMemo, useRef, useEffect, useState, useCallback } from 'react';
import * as Accordion from '@radix-ui/react-accordion';
import { useSpring, animated } from '@react-spring/web';
import type {
  TaskEvent,
  V4Findings,
  V4SessionStatus,
  Breadcrumb,
  ReasoningChainStep,
} from '../../types';

/**
 * INVESTIGATION LOG (Slot 4) — the editorial chronicle.
 *
 * Rebuild of the left-panel timeline. Drops cards, gradients, and
 * dashboard chrome in favor of prose with a 2px left-border encoding
 * agent identity.
 *
 * Structure per phase:
 *   LOGS ANALYZED                                   ← small-caps divider
 *   │ log_agent — 3 findings, 1,247 tokens · 42s   ← 2px agent-color border
 *   │   · null_pointer × 12 on checkout-service
 *   │   · retry_storm detected
 *
 * Cross-check events get a neutral grey left-border so they sit in the
 * timeline as first-class entries, not hidden inside another agent's
 * capsule.
 *
 * The active (in-progress) agent's capsule shows a live breadcrumb line
 * from its latest `Breadcrumb.action`, falling back to `progress` event
 * message, then to the "gathering…" italic placeholder.
 *
 * Reasoning chain hides behind a tail-of-log disclosure:
 *   › how the system thought about it (3 moves)
 * Default collapsed. Clicking expands an indented italic blockquote.
 */

export type FilterMode = 'all' | 'findings' | 'raw';

// ── Agent identity colors — match the existing card-border-L/M/K/C/D tokens ──

const AGENT_BORDER_COLOR: Record<string, string> = {
  log_agent:      '#ef4444', // red
  metrics_agent:  '#d4922e', // amber
  k8s_agent:      '#f97316', // orange
  tracing_agent:  '#8b5cf6', // violet (extending existing tokens)
  code_agent:     '#3b82f6', // blue
  change_agent:   '#10b981', // emerald
};

// Neutral border for cross-check timeline entries.
const CROSS_CHECK_BORDER = '#64748b';

function agentBorder(agent: string): string {
  return AGENT_BORDER_COLOR[agent] ?? CROSS_CHECK_BORDER;
}

// ── Timeline structure ──

interface AgentSession {
  agent: string;
  startedEvent: TaskEvent;
  terminatingEvent: TaskEvent | null;
  // All non-supervisor events attributed to this agent within the phase
  findingEvents: TaskEvent[];
  progressEvents: TaskEvent[];
  toolCallEvents: TaskEvent[];
  breadcrumbs: Breadcrumb[];
  startTs: number;
  isComplete: boolean;
}

interface CrossCheckEntry {
  id: string;
  ts: number;
  message: string;
  kind: string;          // e.g. "metrics_logs" / "tracing_metrics"
  divergenceCount: number;
}

interface Phase {
  label: string;
  startTs: number;
  capsules: AgentSession[];
  crossChecks: CrossCheckEntry[];
  isCurrent: boolean;
}

function isCrossCheckEvent(ev: TaskEvent): boolean {
  return (
    ev.agent_name === 'supervisor' &&
    ev.event_type === 'summary' &&
    (ev.details as Record<string, unknown> | undefined)?.action === 'cross_check_complete'
  );
}

function buildPhases(
  events: TaskEvent[],
  breadcrumbs: Breadcrumb[] | undefined,
): Phase[] {
  // Group breadcrumbs by agent once up-front.
  const breadcrumbsByAgent: Record<string, Breadcrumb[]> = {};
  for (const b of breadcrumbs || []) {
    (breadcrumbsByAgent[b.agent_name] ??= []).push(b);
  }

  // Phase boundaries from phase_change events.
  const boundaries: { index: number; label: string; ts: number }[] = [];
  events.forEach((ev, i) => {
    if (ev.event_type === 'phase_change') {
      const label = ev.details?.phase ? String(ev.details.phase) : ev.message;
      boundaries.push({ index: i, label, ts: new Date(ev.timestamp).getTime() });
    }
  });

  // Split events into phase buckets.
  const buckets: { label: string; ts: number; events: TaskEvent[] }[] = [];
  if (boundaries.length === 0) {
    buckets.push({
      label: 'initial',
      ts: events.length > 0 ? new Date(events[0].timestamp).getTime() : Date.now(),
      events: [...events],
    });
  } else {
    // Events before the first boundary become a synthetic preamble.
    if (boundaries[0].index > 0) {
      buckets.push({
        label: 'initial',
        ts: new Date(events[0].timestamp).getTime(),
        events: events.slice(0, boundaries[0].index),
      });
    }
    for (let p = 0; p < boundaries.length; p++) {
      const start = boundaries[p].index;
      const end = p + 1 < boundaries.length ? boundaries[p + 1].index : events.length;
      buckets.push({
        label: boundaries[p].label,
        ts: boundaries[p].ts,
        events: events.slice(start + 1, end), // skip the phase_change event itself
      });
    }
  }

  // Build phase records.
  return buckets.map((bucket, idx) => {
    const isLast = idx === buckets.length - 1;
    const agentSessions: Record<string, AgentSession> = {};
    const crossChecks: CrossCheckEntry[] = [];

    for (const ev of bucket.events) {
      if (isCrossCheckEvent(ev)) {
        const d = (ev.details || {}) as Record<string, unknown>;
        crossChecks.push({
          id: `${ev.timestamp}-${d.cross_check ?? ''}`,
          ts: new Date(ev.timestamp).getTime(),
          message: ev.message,
          kind: String(d.cross_check ?? ''),
          divergenceCount: Number(d.divergence_count ?? 0),
        });
        continue;
      }
      if (ev.agent_name === 'supervisor') continue;

      const s = (agentSessions[ev.agent_name] ??= {
        agent: ev.agent_name,
        startedEvent: ev,
        terminatingEvent: null,
        findingEvents: [],
        progressEvents: [],
        toolCallEvents: [],
        breadcrumbs: breadcrumbsByAgent[ev.agent_name] ?? [],
        startTs: new Date(ev.timestamp).getTime(),
        isComplete: false,
      });

      if (ev.event_type === 'started') {
        s.startedEvent = ev;
        s.startTs = new Date(ev.timestamp).getTime();
      } else if (ev.event_type === 'summary' || ev.event_type === 'success') {
        s.terminatingEvent = ev;
        s.isComplete = true;
      } else if (ev.event_type === 'finding') {
        s.findingEvents.push(ev);
      } else if (ev.event_type === 'progress') {
        s.progressEvents.push(ev);
      } else if (ev.event_type === 'tool_call') {
        s.toolCallEvents.push(ev);
      }
    }

    const capsules = Object.values(agentSessions).sort((a, b) => a.startTs - b.startTs);
    const allComplete = capsules.length > 0 && capsules.every((c) => c.isComplete);
    return {
      label: bucket.label,
      startTs: bucket.ts,
      capsules,
      crossChecks,
      isCurrent: isLast && !allComplete,
    };
  });
}

// ── Duration helpers ──

function formatElapsed(startTs: number, endTs: number): string {
  const sec = Math.max(0, Math.floor((endTs - startTs) / 1000));
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  if (m === 0) return `${s}s`;
  return `${m}m ${s}s`;
}

// ── Live breadcrumb (active capsule only) ──

function latestLiveLine(
  capsule: AgentSession,
): { text: string; source: 'breadcrumb' | 'progress' | 'placeholder' } {
  const latestBc = capsule.breadcrumbs[capsule.breadcrumbs.length - 1];
  if (latestBc?.action) {
    return { text: latestBc.action, source: 'breadcrumb' };
  }
  const latestProg = capsule.progressEvents[capsule.progressEvents.length - 1];
  if (latestProg?.message) {
    return { text: latestProg.message, source: 'progress' };
  }
  return { text: 'gathering…', source: 'placeholder' };
}

// ── Reasoning disclosure ──

const ReasoningDisclosure: React.FC<{ chain: ReasoningChainStep[] }> = ({ chain }) => {
  const [open, setOpen] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState(0);

  useEffect(() => {
    if (contentRef.current) setHeight(contentRef.current.scrollHeight);
  }, [chain, open]);

  const reduce =
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const spring = useSpring({
    height: open ? height : 0,
    opacity: open ? 1 : 0,
    config: reduce ? { duration: 0 } : { tension: 210, friction: 24 },
  });

  if (chain.length === 0) return null;

  return (
    <div className="mt-10" data-testid="reasoning-disclosure">
      <Accordion.Root type="single" collapsible value={open ? 'r' : ''} onValueChange={(v) => setOpen(v === 'r')}>
        <Accordion.Item value="r">
          <Accordion.Header asChild>
            <Accordion.Trigger
              data-testid="reasoning-trigger"
              className="font-editorial italic text-[12px] text-wr-text-subtle hover:text-wr-paper focus-visible:text-wr-paper transition-colors underline-offset-4 hover:underline focus:outline-none focus-visible:underline"
            >
              <span aria-hidden className="mr-1">›</span>
              how the system thought about it ({chain.length} move{chain.length === 1 ? '' : 's'})
            </Accordion.Trigger>
          </Accordion.Header>
          <Accordion.Content asChild forceMount>
            <animated.div style={{ ...spring, overflow: 'hidden' }} aria-hidden={!open}>
              <div ref={contentRef} className="mt-3 ml-6 space-y-2">
                {chain.map((step, i) => (
                  <p
                    key={i}
                    className="font-editorial italic text-[13px] text-wr-text-muted leading-[1.5]"
                  >
                    <span className="text-wr-text-subtle mr-2">{step.step ?? i + 1}.</span>
                    <span className="text-wr-paper">{step.observation}</span>
                    {step.inference && (
                      <>
                        <span className="text-wr-text-subtle"> → </span>
                        {step.inference}
                      </>
                    )}
                  </p>
                ))}
              </div>
            </animated.div>
          </Accordion.Content>
        </Accordion.Item>
      </Accordion.Root>
    </div>
  );
};

// ── Agent capsule (prose, 2px left-border) ──

const AgentCapsuleProse: React.FC<{
  capsule: AgentSession;
  filterMode: FilterMode;
  isActive: boolean;
  now: number;
}> = ({ capsule, filterMode, isActive, now }) => {
  const endTs = capsule.terminatingEvent
    ? new Date(capsule.terminatingEvent.timestamp).getTime()
    : now;
  const elapsed = formatElapsed(capsule.startTs, endTs);
  const tokenCount = null; // Token counts live on V4SessionStatus, not on the event stream.
                           // We keep the layout open for PR 4 to wire token deltas through.

  const findingLines = filterMode === 'raw' ? [] : capsule.findingEvents;
  const rawLines = filterMode === 'findings' ? [] : capsule.toolCallEvents;

  const borderColor = agentBorder(capsule.agent);

  return (
    <div
      className="relative pl-3 py-1"
      style={{ borderLeft: `2px solid ${borderColor}` }}
      data-testid={`capsule-${capsule.agent}`}
    >
      <div className="text-[13px] text-wr-paper">
        <span className="font-medium">{capsule.agent.replace(/_/g, ' ')}</span>
        <span className="text-wr-text-muted"> — </span>
        {capsule.isComplete ? (
          <span className="text-wr-text-muted">
            {capsule.findingEvents.length} finding{capsule.findingEvents.length === 1 ? '' : 's'}
            {tokenCount != null && `, ${tokenCount} tokens`}
            {' · '}
            <span className="tabular-nums">{elapsed}</span>
          </span>
        ) : (
          <span className="text-wr-text-muted">
            investigating · <span className="tabular-nums">{elapsed}</span>
          </span>
        )}
      </div>

      {/* Live breadcrumb — only for the active (in-progress) agent. */}
      {isActive && !capsule.isComplete && <LiveLine capsule={capsule} />}

      {/* Finding lines */}
      {findingLines.length > 0 && (
        <ul className="mt-1 space-y-0.5">
          {findingLines.map((ev, i) => (
            <li key={i} className="text-[12px] text-wr-paper pl-2">
              <span className="text-wr-text-muted mr-1.5">·</span>
              {ev.message}
            </li>
          ))}
        </ul>
      )}

      {/* Raw tool calls — only in 'all' or 'raw' modes. Rendered as
          mono for actual tool invocations (the one place mono is allowed
          in the editorial scope). */}
      {rawLines.length > 0 && (
        <ul className="mt-1 space-y-0.5">
          {rawLines.map((ev, i) => (
            <li
              key={i}
              className="text-[11px] text-wr-text-muted font-mono pl-2 truncate"
            >
              <span className="mr-1.5">›</span>
              {ev.message}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

const LiveLine: React.FC<{ capsule: AgentSession }> = ({ capsule }) => {
  // useMemo keyed on (breadcrumbs length, progress length) so we only
  // recompute when new data arrives — not on every parent render.
  const live = useMemo(
    () => latestLiveLine(capsule),
    [capsule.breadcrumbs.length, capsule.progressEvents.length, capsule.agent],
  );
  return (
    <p
      className={
        live.source === 'placeholder'
          ? 'text-[12px] italic text-wr-text-subtle pl-2 mt-0.5 truncate'
          : 'text-[12px] text-wr-text-muted pl-2 mt-0.5 truncate'
      }
      data-testid={`live-line-${capsule.agent}`}
      title={live.text}
    >
      <span className="mr-1.5">·</span>
      {live.text}
    </p>
  );
};

// ── Cross-check entry ──

const CrossCheckEntryRow: React.FC<{ entry: CrossCheckEntry }> = ({ entry }) => (
  <div
    className="relative pl-3 py-1"
    style={{ borderLeft: `2px solid ${CROSS_CHECK_BORDER}` }}
    data-testid={`cross-check-${entry.kind}`}
  >
    <p className="text-[13px] text-wr-paper">{entry.message.replace(/^cross-check: /i, '')}</p>
  </div>
);

// ── Filter text links (inline, editorial) ──

const FILTER_MODES: { id: FilterMode; label: string }[] = [
  { id: 'all',      label: 'all' },
  { id: 'findings', label: 'findings' },
  { id: 'raw',      label: 'raw events' },
];

const FilterLinks: React.FC<{
  mode: FilterMode;
  onChange: (m: FilterMode) => void;
}> = ({ mode, onChange }) => (
  <span className="font-editorial italic text-[12px] text-wr-text-muted">
    <span className="mr-2">showing</span>
    {FILTER_MODES.map((f, i) => {
      const active = f.id === mode;
      return (
        <React.Fragment key={f.id}>
          {i > 0 && <span className="mx-2">·</span>}
          <button
            type="button"
            onClick={() => onChange(f.id)}
            className={
              (active
                ? 'text-wr-paper underline underline-offset-4 '
                : 'text-wr-text-muted hover:text-wr-paper hover:underline underline-offset-4 ') +
              'focus:outline-none focus-visible:underline transition-colors'
            }
            data-testid={`filter-${f.id}`}
            aria-pressed={active}
          >
            {f.label}
          </button>
        </React.Fragment>
      );
    })}
  </span>
);

// ── Component ──

interface InvestigationLogProps {
  events: TaskEvent[];
  findings: V4Findings | null;
  status: V4SessionStatus | null;
}

const InvestigationLog: React.FC<InvestigationLogProps> = ({ events, findings, status }) => {
  const [filterMode, setFilterMode] = useState<FilterMode>('all');
  const scrollRef = useRef<HTMLDivElement>(null);
  const userScrolledUpRef = useRef(false);
  const [now, setNow] = useState(() => Date.now());

  // Tick once a second so live elapsed times move.
  useEffect(() => {
    const iv = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(iv);
  }, []);

  // Preserve manual scroll; otherwise follow tail.
  const handleScroll = useCallback(() => {
    if (!scrollRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
    userScrolledUpRef.current = scrollHeight - scrollTop - clientHeight > 120;
  }, []);

  useEffect(() => {
    if (scrollRef.current && !userScrolledUpRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [events.length]);

  const phases = useMemo(
    () => buildPhases(events, status?.breadcrumbs),
    [events, status?.breadcrumbs],
  );

  if (events.length === 0) {
    return (
      <div className="flex-1 px-6 py-3">
        <div className="flex items-center gap-3 mb-2 px-0 pt-1">
          <h2 className="text-[13px] font-medium text-wr-paper">Investigation log</h2>
        </div>
        <p className="font-editorial italic text-[14px] text-wr-text-muted mt-6" data-testid="log-empty">
          Waiting for the first agent to report.
        </p>
      </div>
    );
  }

  return (
    <div
      ref={scrollRef}
      onScroll={handleScroll}
      className="flex-1 overflow-y-auto px-6 py-3 custom-scrollbar"
      data-testid="investigation-log"
    >
      {/* Heading + filter links */}
      <div className="flex items-baseline gap-4 mb-2">
        <h2 className="text-[13px] font-medium text-wr-paper">Investigation log</h2>
        <div className="ml-auto">
          <FilterLinks mode={filterMode} onChange={setFilterMode} />
        </div>
      </div>

      {/* Phases */}
      <div className="mt-6 space-y-10">
        {phases.map((phase, pi) => (
          <section key={`${phase.label}-${pi}`} data-testid={`phase-${phase.label}`}>
            <header
              className="mb-3 text-[11px] text-wr-text-muted"
              style={{
                fontVariant: 'small-caps',
                letterSpacing: '0.15em',
              }}
            >
              {phase.label.replace(/_/g, ' ')}
              {phase.isCurrent && (
                <span className="ml-2 text-wr-text-subtle">(active)</span>
              )}
            </header>

            <div className="space-y-3">
              {/* Agent capsules, interleaved chronologically with cross-check
                  entries (both are sorted on their startTs). */}
              {[
                ...phase.capsules.map((c) => ({ kind: 'capsule' as const, ts: c.startTs, data: c })),
                ...phase.crossChecks.map((x) => ({ kind: 'crosscheck' as const, ts: x.ts, data: x })),
              ]
                .sort((a, b) => a.ts - b.ts)
                .map((item) =>
                  item.kind === 'capsule' ? (
                    <AgentCapsuleProse
                      key={`${phase.label}-${item.data.agent}-${item.data.startTs}`}
                      capsule={item.data}
                      filterMode={filterMode}
                      isActive={phase.isCurrent && !item.data.isComplete}
                      now={now}
                    />
                  ) : (
                    <CrossCheckEntryRow
                      key={`${phase.label}-${item.data.id}`}
                      entry={item.data}
                    />
                  ),
                )}
            </div>
          </section>
        ))}
      </div>

      {/* Tail-of-log reasoning disclosure */}
      <ReasoningDisclosure chain={findings?.reasoning_chain ?? []} />
    </div>
  );
};

export default InvestigationLog;
