import React, { useState, useCallback } from 'react';
import * as Accordion from '@radix-ui/react-accordion';
import { useSpring, animated } from '@react-spring/web';
import type { V4Findings, V4SessionStatus, CodeImpact, DiffAnalysisItem, SuggestedFixArea } from '../../types';
import { useIncidentLifecycle } from '../../contexts/IncidentLifecycleContext';
import { generateFix } from '../../services/api';

/**
 * FixReadyBar — center-panel addition #2 (the user's #2)
 *
 * A sticky, phase-gated surface above the evidence AnchorToolbar. When
 * the diagnosis completes and a fix is proposed, this is the first
 * thing the SRE sees: a one-line summary of the fix + a click-to-expand
 * diff + actions. Saves 2-5 minutes of scrolling to find the fix at
 * the tail of every successful investigation.
 *
 * Trigger:
 *   status.phase ∈ {diagnosis_complete, complete}
 *   AND at least one of:
 *     · findings.root_cause_location is non-null
 *     · findings.diff_analysis has entries
 *     · findings.suggested_fix_areas has entries
 *
 * Renders 0px when untriggered.
 *
 * Lifecycle-aware:
 *   · active   — action-bar voice: "Fix ready · [view diff] [open PR] [dismiss]"
 *   · recent   — same but gently muted
 *   · historical — history-bar voice: "Fix applied X ago · [view diff]"
 *
 * Dismiss is session-scoped; re-appears if phase cycles to a new
 * diagnosis_complete.
 */

interface FixReadyBarProps {
  findings: V4Findings | null;
  status: V4SessionStatus | null;
  /** PR-B — session context so the "open PR" button can call
   *  /api/v4/session/{id}/fix/generate directly when no external
   *  onOpenPR handler is wired in. Parent components that want custom
   *  behavior (e.g. open a confirmation dialog first) can still pass
   *  onOpenPR and the sessionId path is skipped. */
  sessionId?: string;
  onOpenPR?: () => void;
}

interface FixSummary {
  /** Primary target location, e.g. "PaymentController.process, line 127" */
  primaryLocation: string;
  /** Number of files touched by the fix */
  fileCount: number;
  /** Optional commit_sha when pre-applied (historical mode) */
  commitSha?: string;
}

function deriveFixSummary(findings: V4Findings | null): FixSummary | null {
  if (!findings) return null;

  const loc: CodeImpact | null = findings.root_cause_location ?? null;
  const diffs: DiffAnalysisItem[] = findings.diff_analysis ?? [];
  const suggestions: SuggestedFixArea[] = findings.suggested_fix_areas ?? [];

  if (!loc && diffs.length === 0 && suggestions.length === 0) return null;

  // Prefer root_cause_location for the primary label — most surgical.
  let primaryLocation = '';
  if (loc) {
    const file = loc.file_path.split('/').pop() ?? loc.file_path;
    const line = loc.relevant_lines?.[0]?.start;
    primaryLocation = line ? `${file}, line ${line}` : file;
  } else if (diffs.length > 0) {
    const file = diffs[0].file.split('/').pop() ?? diffs[0].file;
    primaryLocation = file;
  } else if (suggestions.length > 0) {
    const file = suggestions[0].file_path.split('/').pop() ?? suggestions[0].file_path;
    primaryLocation = file;
  }

  const touchedFiles = new Set<string>();
  if (loc) touchedFiles.add(loc.file_path);
  for (const d of diffs) touchedFiles.add(d.file);
  for (const s of suggestions) touchedFiles.add(s.file_path);

  return {
    primaryLocation,
    fileCount: touchedFiles.size,
    commitSha: diffs[0]?.commit_sha,
  };
}

const TERMINAL_PHASES = new Set(['diagnosis_complete', 'complete']);

export const FixReadyBar: React.FC<FixReadyBarProps> = ({
  findings,
  status,
  sessionId,
  onOpenPR,
}) => {
  const { lifecycle } = useIncidentLifecycle();
  const [dismissed, setDismissed] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);

  // PR-B — default handler: call the existing /fix/generate endpoint
  // when the parent didn't supply a custom onOpenPR. Resolves the
  // dead-button bug (SDET audit C1) so the action is always live.
  const handleOpenPR = useCallback(async () => {
    if (onOpenPR) {
      onOpenPR();
      return;
    }
    if (!sessionId || generating) return;
    setGenerating(true);
    setGenerateError(null);
    try {
      await generateFix(sessionId);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to start';
      setGenerateError(msg);
      window.setTimeout(() => setGenerateError(null), 4000);
    } finally {
      setGenerating(false);
    }
  }, [onOpenPR, sessionId, generating]);

  const phase = status?.phase;
  const triggered = phase && TERMINAL_PHASES.has(phase);
  const fix = deriveFixSummary(findings);

  const reduce =
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const spring = useSpring({
    height: expanded ? 'auto' : 0,
    opacity: expanded ? 1 : 0,
    config: reduce ? { duration: 0 } : { tension: 210, friction: 24 },
  });

  if (!triggered || !fix || dismissed) return null;

  const isHistorical = lifecycle === 'historical';
  const diffLines = findings?.diff_analysis ?? [];

  return (
    <div
      className="fix-ready-bar border-b border-wr-border bg-wr-bg/95 backdrop-blur"
      data-testid="fix-ready-bar"
    >
      <Accordion.Root
        type="single"
        collapsible
        value={expanded ? 'diff' : ''}
        onValueChange={(v) => setExpanded(v === 'diff')}
      >
        <Accordion.Item value="diff">
          <div className="flex items-center gap-3 px-4 py-2">
            {/* Green checkmark tick */}
            <span
              aria-hidden
              className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-emerald-500/20 text-emerald-400 text-[10px] shrink-0"
            >
              ✓
            </span>

            {/* Headline prose */}
            <p
              className="flex-1 min-w-0 text-[13px] text-wr-paper leading-[1.4]"
              data-testid="fix-ready-headline"
            >
              {isHistorical
                ? `Fix applied · ${fix.primaryLocation}`
                : `Fix ready · ${fix.primaryLocation}`}
              {fix.fileCount > 1 && (
                <span className="text-wr-text-muted">
                  {' '}({fix.fileCount} files)
                </span>
              )}
            </p>

            {/* Actions */}
            <Accordion.Header asChild>
              <Accordion.Trigger asChild>
                <button
                  type="button"
                  className="shrink-0 text-[12px] text-wr-paper underline-offset-4 hover:underline focus-visible:underline focus:outline-none"
                  data-testid="fix-ready-view-diff"
                >
                  {expanded ? 'hide diff' : 'view diff'}
                </button>
              </Accordion.Trigger>
            </Accordion.Header>

            {!isHistorical && (onOpenPR || sessionId) && (
              <button
                type="button"
                onClick={handleOpenPR}
                disabled={generating}
                className="shrink-0 text-[12px] text-wr-paper underline-offset-4 hover:underline focus-visible:underline focus:outline-none disabled:opacity-50 disabled:cursor-wait"
                data-testid="fix-ready-open-pr"
              >
                {generating ? 'starting…' : 'open PR'}
              </button>
            )}
            {generateError && (
              <span
                className="shrink-0 text-[11px] text-red-400 font-editorial italic"
                role="alert"
                data-testid="fix-ready-open-pr-error"
              >
                {generateError}
              </span>
            )}

            {!isHistorical && (
              <button
                type="button"
                onClick={() => setDismissed(true)}
                className="shrink-0 text-[12px] text-wr-text-muted hover:text-wr-paper underline-offset-4 hover:underline focus-visible:underline focus:outline-none transition-colors"
                data-testid="fix-ready-dismiss"
                aria-label="Dismiss fix-ready bar"
              >
                dismiss
              </button>
            )}
          </div>

          {/* Inline diff accordion content */}
          <Accordion.Content asChild forceMount>
            <animated.div
              style={{ ...spring, overflow: 'hidden' }}
              aria-hidden={!expanded}
            >
              <div
                className="px-4 pb-3 pt-1 border-t border-wr-border-subtle/60"
                data-testid="fix-ready-diff-panel"
              >
                {diffLines.length > 0 ? (
                  <ul className="space-y-2 text-[12px]">
                    {diffLines.slice(0, 5).map((d, i) => (
                      <li key={i} className="font-mono text-wr-text-muted">
                        <span className="text-wr-paper">{d.file}</span>
                        {d.commit_sha && (
                          <span className="ml-2 text-wr-text-subtle">@{d.commit_sha.slice(0, 7)}</span>
                        )}
                        {d.reasoning && (
                          <p className="font-sans text-wr-text-muted italic mt-0.5 ml-2">
                            {d.reasoning}
                          </p>
                        )}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-[12px] text-wr-text-muted italic">
                    Suggested change is above — full diff will appear here once generated.
                  </p>
                )}
              </div>
            </animated.div>
          </Accordion.Content>
        </Accordion.Item>
      </Accordion.Root>
    </div>
  );
};

export default FixReadyBar;
