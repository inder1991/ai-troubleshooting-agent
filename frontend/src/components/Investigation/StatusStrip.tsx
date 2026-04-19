import React, { useRef, useState, useLayoutEffect } from 'react';
import * as Accordion from '@radix-ui/react-accordion';
import { useSpring, animated } from '@react-spring/web';
import type {
  V4Findings,
  V4SessionStatus,
  WinnerCriticDissent,
} from '../../types';

/**
 * STATUS STRIP (Slot 3) — marginalia beneath the VERDICT.
 *
 * A single editorial sentence. Clauses are separated by `·`. Each clause
 * drops out independently when its count is zero; the whole strip drops
 * out when all three are absent. No dots-as-glyphs, no pills, no icons.
 *
 * Interaction:
 *   · `N data sources missing`  → inline expand (coverage gaps)
 *   · `critic disagreed`        → inline expand (dissent summary)
 *   · `N signals contradict`    → Lenis-smooth scroll to the
 *                                 DisagreementStrip in col-5, then a
 *                                 one-shot flash.
 */

interface StatusStripProps {
  findings: V4Findings | null;
  // coverage_gaps + winner_critic_dissent live on the status endpoint
  // rather than findings. divergence_findings lives on findings.
  status: V4SessionStatus | null;
}

// DOM convention — DisagreementStrip in col-5 carries this test-id.
const DISAGREEMENT_STRIP_SELECTOR = '[data-testid="disagreement-strip"]';

function scrollToDisagreements() {
  const el = document.querySelector(DISAGREEMENT_STRIP_SELECTOR);
  if (!el) return;
  const reduce =
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  el.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
  // One-shot brightness flash on the strip's text.
  const html = el as HTMLElement;
  const prior = html.style.color;
  html.style.transition = 'color 0.8s ease-out';
  html.style.color = '#e8e0d4';
  window.setTimeout(() => {
    html.style.color = prior;
    html.style.transition = '';
  }, 800);
}

// ── Expandable body (React Spring physics; honours reduced-motion) ──

const ExpandableBody: React.FC<{
  isOpen: boolean;
  children: React.ReactNode;
}> = ({ isOpen, children }) => {
  const contentRef = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState(0);

  useLayoutEffect(() => {
    if (contentRef.current) {
      setHeight(contentRef.current.scrollHeight);
    }
  }, [children]);

  const reduce =
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const spring = useSpring({
    height: isOpen ? height : 0,
    opacity: isOpen ? 1 : 0,
    config: reduce
      ? { duration: 0 }
      : { tension: 210, friction: 24 },
  });

  return (
    <animated.div
      style={{ ...spring, overflow: 'hidden' }}
      aria-hidden={!isOpen}
    >
      <div ref={contentRef} className="pt-2 pb-1">
        {children}
      </div>
    </animated.div>
  );
};

// ── Per-clause expansion bodies ──

const CoverageGapsBody: React.FC<{ gaps: string[] }> = ({ gaps }) => (
  <ul className="font-editorial italic text-wr-text-muted text-[13px] space-y-0.5 ml-3">
    {gaps.map((gap, i) => (
      <li key={i}>· {gap}</li>
    ))}
  </ul>
);

const CriticDissentBody: React.FC<{ dissent: WinnerCriticDissent }> = ({ dissent }) => {
  const line =
    `advocate said ${dissent.advocate_verdict.replace(/_/g, ' ')}; ` +
    `challenger said ${dissent.challenger_verdict.replace(/_/g, ' ')}; ` +
    `judge said ${dissent.judge_verdict.replace(/_/g, ' ')}.`;
  return (
    <div className="font-editorial italic text-wr-text-muted text-[13px] ml-3 space-y-1">
      <p>{line}</p>
      {dissent.summary && (
        <p className="text-wr-text-subtle">"{dissent.summary}"</p>
      )}
    </div>
  );
};

// ── Clause model ──

type ClauseId = 'gaps' | 'dissent' | 'divergence';

interface Clause {
  id: ClauseId;
  text: string;
  kind: 'accordion' | 'scroll';
}

function buildClauses(
  findings: V4Findings,
  status: V4SessionStatus | null,
): Clause[] {
  const clauses: Clause[] = [];

  const gapCount = (status?.coverage_gaps || []).length;
  if (gapCount > 0) {
    clauses.push({
      id: 'gaps',
      text: `${gapCount} data source${gapCount === 1 ? '' : 's'} missing`,
      kind: 'accordion',
    });
  }

  if (status?.winner_critic_dissent) {
    clauses.push({
      id: 'dissent',
      text: 'critic disagreed',
      kind: 'accordion',
    });
  }

  const divCount = (findings.divergence_findings || []).length;
  if (divCount > 0) {
    clauses.push({
      id: 'divergence',
      text: `${divCount} signal${divCount === 1 ? '' : 's'} contradict`,
      kind: 'scroll',
    });
  }

  return clauses;
}

// ── Component ────────────────────────────────────────────────────────

const StatusStrip: React.FC<StatusStripProps> = ({ findings, status }) => {
  const [openValue, setOpenValue] = useState<string>(''); // '' | ClauseId

  if (!findings) return null;
  const clauses = buildClauses(findings, status);
  if (clauses.length === 0) return null;

  return (
    <div
      className="px-6 pb-6"
      data-testid="status-strip"
      role="region"
      aria-label="investigation status summary"
    >
      <Accordion.Root
        type="single"
        collapsible
        value={openValue}
        onValueChange={setOpenValue}
      >
        <p className="font-editorial italic text-wr-text-muted text-[12px] leading-[1.5]">
          {clauses.map((clause, idx) => {
            const isLast = idx === clauses.length - 1;
            const sep = isLast ? '.' : ' · ';

            if (clause.kind === 'scroll') {
              return (
                <React.Fragment key={clause.id}>
                  <button
                    type="button"
                    onClick={scrollToDisagreements}
                    className="underline-offset-4 hover:underline focus-visible:underline focus:outline-none text-wr-text-muted hover:text-wr-paper focus-visible:text-wr-paper transition-colors"
                    aria-label={`${clause.text} — open in evidence column`}
                    data-testid={`clause-${clause.id}`}
                  >
                    {clause.text}
                  </button>
                  {sep}
                </React.Fragment>
              );
            }

            return (
              <React.Fragment key={clause.id}>
                <Accordion.Item value={clause.id} asChild>
                  <span>
                    <Accordion.Header asChild>
                      <Accordion.Trigger
                        data-testid={`clause-${clause.id}`}
                        className="underline-offset-4 hover:underline focus-visible:underline focus:outline-none text-wr-text-muted hover:text-wr-paper focus-visible:text-wr-paper data-[state=open]:text-wr-paper transition-colors"
                      >
                        {clause.text}
                      </Accordion.Trigger>
                    </Accordion.Header>
                  </span>
                </Accordion.Item>
                {sep}
              </React.Fragment>
            );
          })}
        </p>

        {/* Expansion bodies, rendered outside the sentence so the height
            animation pushes the log down, not the inline prose. */}
        <ExpandableBody isOpen={openValue === 'gaps'}>
          <CoverageGapsBody gaps={status?.coverage_gaps || []} />
        </ExpandableBody>
        <ExpandableBody isOpen={openValue === 'dissent'}>
          {status?.winner_critic_dissent ? (
            <CriticDissentBody dissent={status.winner_critic_dissent} />
          ) : null}
        </ExpandableBody>
      </Accordion.Root>
    </div>
  );
};

export default StatusStrip;
