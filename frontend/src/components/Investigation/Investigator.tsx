import React, { useState, useEffect, useMemo } from 'react';
import type { TaskEvent, V4Findings, V4SessionStatus } from '../../types';
import { FeedbackRow } from './FeedbackRow';
import { submitInvestigationFeedback } from '../../services/api';
import Verdict from './Verdict';
import StatusStrip from './StatusStrip';
import PatientZeroMetadata from './PatientZeroMetadata';
import InvestigationLog from './InvestigationLog';

interface InvestigatorProps {
  sessionId: string;
  events: TaskEvent[];
  wsConnected: boolean;
  findings: V4Findings | null;
  status: V4SessionStatus | null;
  onAttachRepo?: () => void;
}

const Investigator: React.FC<InvestigatorProps> = ({
  sessionId,
  events,
  // wsConnected intentionally unused — status chrome retired with the
  // old header; keep on the props contract for parent compatibility.
  findings,
  status,
  onAttachRepo,
}) => {
  // Repo mismatch detection (Patient Zero banner)
  const repoMismatch = useMemo(() => {
    if (!findings?.patient_zero?.service || !findings?.target_service) return false;
    return findings.patient_zero.service.toLowerCase() !== findings.target_service.toLowerCase();
  }, [findings?.patient_zero?.service, findings?.target_service]);

  // Time-to-impact — Patient Zero's live elapsed timer.
  const firstErrorTime = findings?.patient_zero?.first_error_time;
  const [elapsedSec, setElapsedSec] = useState(0);
  useEffect(() => {
    if (!firstErrorTime) return;
    const start = new Date(firstErrorTime).getTime();
    const tick = () => setElapsedSec(Math.floor((Date.now() - start) / 1000));
    tick();
    const iv = setInterval(tick, 1000);
    return () => clearInterval(iv);
  }, [firstErrorTime]);

  const formatElapsed = (sec: number) => {
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  };

  // Timeline, filter toolbar, scroll-follow, and reasoning disclosure
  // all moved to InvestigationLog.tsx in PR 3.

  return (
    <div className="warroom-left-editorial flex flex-col h-full bg-wr-bg/20">
      {/* Note: CoverageGapsBanner, CriticDissentBanner, BudgetPill, and
          SelfConsistencyBadge are intentionally NOT rendered here anymore.
          — Gaps + dissent fold into <StatusStrip /> below Patient Zero.
          — Budget + SelfConsistency move to the bottom progress bar (PR 4).
          See docs/design/left-panel-editorial.md for the rationale. */}
      {/* Patient Zero Banner (sticky) */}
      {findings?.patient_zero && (
        <div className="sticky top-0 z-10 bg-gradient-to-r from-red-950/80 to-red-900/40 border-b border-wr-severity-high/30 px-4 py-3 animate-pulse-red">
          <div className="flex items-center gap-2 mb-1">
            <span className="w-2.5 h-2.5 rounded-full bg-red-500 animate-pulse" />
            <span className="text-body-xs font-bold uppercase tracking-wider text-red-400">Patient Zero</span>
            {firstErrorTime && (
              <span className="ml-auto text-lg font-mono font-bold text-red-400">{formatElapsed(elapsedSec)}</span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <span className="text-sm font-mono text-red-200 font-bold">{findings.patient_zero.service}</span>
            {repoMismatch && (
              <span className="inline-flex items-center text-body-xs font-bold uppercase px-1.5 py-0.5 rounded bg-wr-severity-medium/20 text-amber-400 border border-wr-severity-medium/30">
                Repo Mismatch
              </span>
            )}
          </div>
          <p className="text-body-xs text-red-300/70 mt-0.5">{findings.patient_zero.evidence}</p>
          {/* PR 2b — Env context + service ownership. Additive, never
              shouts when data missing. Each line drops silently. */}
          <PatientZeroMetadata findings={findings} />
          {repoMismatch && onAttachRepo && (
            <div className="mt-1.5 flex items-center gap-2">
              <p className="text-body-xs text-amber-300/80">
                Root cause in <strong>{findings.patient_zero.service}</strong>, repo provided for <strong>{findings.target_service}</strong>
              </p>
              <button
                onClick={onAttachRepo}
                className="text-body-xs font-bold uppercase px-2 py-0.5 rounded bg-wr-severity-medium/20 text-amber-300 border border-wr-severity-medium/30 hover:bg-amber-500/30 transition-colors"
              >
                Attach Repo
              </button>
            </div>
          )}
        </div>
      )}

      {/* Slot 2 — VERDICT (editorial prose) + blast-radius sentence */}
      <Verdict findings={findings} events={events} />

      {/* Slot 3 — Status Strip (single-line marginalia; folds in the
          old CoverageGapsBanner + CriticDissentBanner data) */}
      <StatusStrip findings={findings} status={status} />

      {/* Agent Pulse Indicator removed from left panel — moved to the
          right-panel AGENTS card in PR 5 (see docs/design/left-panel-editorial.md) */}

      {/* Slot 4 — Investigation Log (editorial chronicle). Owns its own
          header, filter toolbar, phase dividers, agent capsules, live
          breadcrumb, cross-check entries, and reasoning disclosure. */}
      <InvestigationLog events={events} findings={findings} status={status} />

      {/* Hypothesis Scoreboard removed — its role is now owned by
          <Verdict /> above, promoted to a hero slot under Patient Zero.
          See docs/design/left-panel-editorial.md. */}
      {/* Feedback row (Task 4.13) — user labels the outcome; priors update server-side.
          Gating on phase === 'complete' is scheduled for PR 4. */}
      <FeedbackRow
        runId={`investigation-${sessionId}`}
        submit={async (payload) => {
          await submitInvestigationFeedback(payload);
          return { ok: true };
        }}
      />
    </div>
  );
};


export default Investigator;
