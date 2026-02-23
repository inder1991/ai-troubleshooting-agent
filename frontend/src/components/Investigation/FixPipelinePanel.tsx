import React, { useState } from 'react';
import type { V4Findings, DiagnosticPhase, FixStatus, FixVerificationResult } from '../../types';
import { generateFix, decideOnFix } from '../../services/api';
import AgentFindingCard from './cards/AgentFindingCard';
import HoldToConfirm from '../ui/HoldToConfirm';
import CopyButton from '../ui/CopyButton';

interface FixPipelinePanelProps {
  sessionId: string;
  findings: V4Findings | null;
  phase: DiagnosticPhase | null;
  onRefresh: () => void;
}

// ─── Status Badge ─────────────────────────────────────────────────────────

const statusConfig: Record<FixStatus, { label: string; color: string }> = {
  not_started: { label: 'NOT STARTED', color: 'text-slate-400 bg-slate-500/10 border-slate-500/20' },
  generating: { label: 'GENERATING', color: 'text-amber-400 bg-amber-500/10 border-amber-500/20' },
  awaiting_review: { label: 'AWAITING REVIEW', color: 'text-violet-400 bg-violet-500/10 border-violet-500/20' },
  human_feedback: { label: 'PROCESSING FEEDBACK', color: 'text-blue-400 bg-blue-500/10 border-blue-500/20' },
  verification_in_progress: { label: 'VERIFYING', color: 'text-cyan-400 bg-cyan-500/10 border-cyan-500/20' },
  verified: { label: 'VERIFIED', color: 'text-green-400 bg-green-500/10 border-green-500/20' },
  verification_failed: { label: 'VERIFICATION FAILED', color: 'text-red-400 bg-red-500/10 border-red-500/20' },
  approved: { label: 'APPROVED', color: 'text-green-400 bg-green-500/10 border-green-500/20' },
  rejected: { label: 'REJECTED', color: 'text-red-400 bg-red-500/10 border-red-500/20' },
  pr_creating: { label: 'CREATING PR', color: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20' },
  pr_created: { label: 'PR CREATED', color: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20' },
  failed: { label: 'FAILED', color: 'text-red-400 bg-red-500/10 border-red-500/20' },
};

const FixStatusBadge: React.FC<{ status: FixStatus }> = ({ status }) => {
  const cfg = statusConfig[status] || statusConfig.not_started;
  return (
    <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded border ${cfg.color}`}>
      {cfg.label}
    </span>
  );
};

// ─── Verification Verdict Badge ───────────────────────────────────────────

const verdictConfig: Record<string, { icon: string; color: string }> = {
  approve: { icon: 'check_circle', color: 'text-green-400 bg-green-500/10 border-green-500/20' },
  reject: { icon: 'cancel', color: 'text-red-400 bg-red-500/10 border-red-500/20' },
  needs_changes: { icon: 'edit_note', color: 'text-amber-400 bg-amber-500/10 border-amber-500/20' },
};

// ─── Diff Viewer ──────────────────────────────────────────────────────────

const DiffViewer: React.FC<{ diff: string }> = ({ diff }) => {
  if (!diff) return null;
  const lines = diff.split('\n');
  return (
    <pre className="text-[10px] font-mono bg-slate-900/60 rounded p-3 max-h-[300px] overflow-y-auto overflow-x-auto custom-scrollbar whitespace-pre">
      {lines.map((line, i) => {
        let lineColor = 'text-slate-400';
        if (line.startsWith('+') && !line.startsWith('+++')) lineColor = 'text-green-400';
        else if (line.startsWith('-') && !line.startsWith('---')) lineColor = 'text-red-400';
        else if (line.startsWith('@@')) lineColor = 'text-cyan-400';
        else if (line.startsWith('diff') || line.startsWith('index')) lineColor = 'text-slate-500';
        return (
          <div key={i} className={lineColor}>
            {line}
          </div>
        );
      })}
    </pre>
  );
};

// ─── Main Component ───────────────────────────────────────────────────────

const FixPipelinePanel: React.FC<FixPipelinePanelProps> = ({
  sessionId,
  findings,
  phase,
  onRefresh,
}) => {
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [guidance, setGuidance] = useState('');
  const [feedbackText, setFeedbackText] = useState('');
  const [showDiff, setShowDiff] = useState(true);

  const fixData = findings?.fix_data || null;
  const fixStatus: FixStatus = fixData?.fix_status || 'not_started';
  const verification = fixData?.verification_result || null;

  // ── Action Handlers ──────────────────────────────────────────────────

  const handleGenerateFix = async () => {
    setLoading('generating');
    setError(null);
    try {
      await generateFix(sessionId, guidance);
      onRefresh();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to start fix generation');
    } finally {
      setLoading(null);
    }
  };

  const handleApprove = async () => {
    setLoading('approving');
    setError(null);
    try {
      await decideOnFix(sessionId, 'approve');
      onRefresh();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to approve fix');
    } finally {
      setLoading(null);
    }
  };

  const handleReject = async () => {
    setLoading('rejecting');
    setError(null);
    try {
      await decideOnFix(sessionId, 'reject');
      onRefresh();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to reject fix');
    } finally {
      setLoading(null);
    }
  };

  const handleFeedback = async () => {
    if (!feedbackText.trim()) return;
    setLoading('feedback');
    setError(null);
    try {
      await decideOnFix(sessionId, `feedback: ${feedbackText}`);
      setFeedbackText('');
      onRefresh();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to send feedback');
    } finally {
      setLoading(null);
    }
  };

  // ── Render Helpers ───────────────────────────────────────────────────

  const renderAttemptCounter = () => {
    if (!fixData || fixData.max_attempts <= 0) return null;
    return (
      <span className="text-[9px] text-slate-500 font-mono">
        Attempt {fixData.attempt_count}/{fixData.max_attempts}
      </span>
    );
  };

  const renderVerificationResult = (vr: FixVerificationResult) => {
    const cfg = verdictConfig[vr.verdict] || verdictConfig.needs_changes;
    return (
      <div className="rounded-lg bg-slate-800/30 border border-slate-700/50 p-3 space-y-2">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-sm" style={{ fontFamily: 'Material Symbols Outlined' }}>
            {cfg.icon}
          </span>
          <span className={`text-[10px] font-bold px-2 py-0.5 rounded border ${cfg.color}`}>
            {vr.verdict.replace(/_/g, ' ').toUpperCase()}
          </span>
          <span className="text-[10px] font-mono text-slate-400">
            {Math.round(vr.confidence * 100)}% confidence
          </span>
        </div>

        {vr.reasoning && (
          <p className="text-[10px] text-slate-400 leading-relaxed">{vr.reasoning}</p>
        )}

        {vr.issues_found.length > 0 && (
          <div className="space-y-1">
            <span className="text-[9px] font-bold text-red-400 uppercase tracking-wider">Issues Found</span>
            {vr.issues_found.map((issue, i) => (
              <div key={i} className="flex items-start gap-1.5 text-[10px] text-red-300">
                <span className="text-red-500 shrink-0 mt-0.5">&#x2022;</span>
                <span>{issue}</span>
              </div>
            ))}
          </div>
        )}

        {vr.regression_risks.length > 0 && (
          <div className="space-y-1">
            <span className="text-[9px] font-bold text-amber-400 uppercase tracking-wider">Regression Risks</span>
            {vr.regression_risks.map((risk, i) => (
              <div key={i} className="flex items-start gap-1.5 text-[10px] text-amber-300">
                <span className="text-amber-500 shrink-0 mt-0.5">&#x2022;</span>
                <span>{risk}</span>
              </div>
            ))}
          </div>
        )}

        {vr.suggestions.length > 0 && (
          <div className="space-y-1">
            <span className="text-[9px] font-bold text-cyan-400 uppercase tracking-wider">Suggestions</span>
            {vr.suggestions.map((s, i) => (
              <div key={i} className="flex items-start gap-1.5 text-[10px] text-cyan-300">
                <span className="text-cyan-500 shrink-0 mt-0.5">&#x2022;</span>
                <span>{s}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  // ── Section Renderers (by fix_status) ────────────────────────────────

  const renderGenerateSection = () => (
    <div className="space-y-3">
      <p className="text-[11px] text-slate-400">
        Generate an automated fix based on the diagnosis findings. Optionally provide guidance to steer the fix.
      </p>
      <textarea
        placeholder="Optional guidance (e.g. 'focus on the null pointer in UserService.java')"
        value={guidance}
        onChange={(e) => setGuidance(e.target.value)}
        rows={2}
        className="w-full text-[11px] bg-slate-800/60 border border-slate-700/50 rounded px-3 py-2 text-slate-200 placeholder-slate-600 font-mono focus:outline-none focus:border-emerald-500/50 resize-none"
      />
      <button
        onClick={handleGenerateFix}
        disabled={loading === 'generating'}
        className="text-[10px] font-bold px-4 py-1.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/30 disabled:opacity-50 disabled:cursor-not-allowed disabled:saturate-0 flex items-center gap-2"
      >
        {loading === 'generating' ? (
          <div className="w-3 h-3 border-2 border-emerald-400/30 border-t-emerald-400 rounded-full animate-spin" />
        ) : (
          <span className="material-symbols-outlined text-xs" style={{ fontFamily: 'Material Symbols Outlined' }}>
            auto_fix_high
          </span>
        )}
        {loading === 'generating' ? 'Starting...' : 'Generate Fix'}
      </button>
    </div>
  );

  const renderProgressSection = () => (
    <div className="flex items-center gap-3 py-2">
      <div className="w-5 h-5 border-2 border-slate-700 border-t-emerald-500 rounded-full animate-spin" />
      <div>
        <div className="text-[11px] text-slate-300">
          {fixStatus === 'generating' && 'Generating fix...'}
          {fixStatus === 'verification_in_progress' && 'Verifying generated fix...'}
          {fixStatus === 'pr_creating' && 'Creating pull request...'}
          {fixStatus === 'human_feedback' && 'Processing your feedback...'}
        </div>
        {fixData?.target_file && (
          <div className="text-[10px] font-mono text-slate-500 mt-0.5">{fixData.target_file}</div>
        )}
      </div>
    </div>
  );

  const renderReviewSection = () => (
    <div className="space-y-3">
      {/* Target file + explanation */}
      {fixData?.target_file && (
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-xs text-slate-500" style={{ fontFamily: 'Material Symbols Outlined' }}>
            description
          </span>
          <span className="text-[11px] font-mono text-blue-400">{fixData.target_file}</span>
        </div>
      )}
      {fixData?.fix_explanation && (
        <p className="text-[11px] text-slate-300 leading-relaxed">{fixData.fix_explanation}</p>
      )}

      {/* Verification Result */}
      {verification && renderVerificationResult(verification)}

      {/* Diff */}
      {fixData?.diff && (
        <div>
          <div className="flex items-center gap-2 mb-1.5">
            <button
              onClick={() => setShowDiff(!showDiff)}
              className="flex items-center gap-1.5 text-[10px] text-slate-400 hover:text-slate-300"
              aria-expanded={showDiff}
              aria-label={`${showDiff ? 'Hide' : 'Show'} diff`}
            >
              <span
                className={`material-symbols-outlined text-xs transition-transform duration-200 ${showDiff ? 'rotate-90' : ''}`}
                style={{ fontFamily: 'Material Symbols Outlined' }}
              >
                chevron_right
              </span>
              <span className="font-bold uppercase tracking-wider">Diff</span>
            </button>
            {showDiff && fixData?.diff && <CopyButton text={fixData.diff} size={11} />}
          </div>
          {showDiff && <DiffViewer diff={fixData.diff} />}
        </div>
      )}

      {/* Human Feedback History */}
      {(fixData?.human_feedback?.length ?? 0) > 0 && (
        <div className="space-y-1.5">
          <span className="text-[9px] font-bold text-slate-500 uppercase tracking-wider">Previous Feedback</span>
          {fixData!.human_feedback.map((fb, i) => (
            <div key={i} className="text-[10px] text-slate-400 bg-slate-800/30 rounded px-2.5 py-1.5 border border-slate-700/30 font-mono">
              {fb}
            </div>
          ))}
        </div>
      )}

      {/* Action Buttons — only when awaiting_review */}
      {fixStatus === 'awaiting_review' && (
        <div className="space-y-2 pt-1 border-t border-slate-800/50">
          <div className="flex items-center gap-2">
            {loading === 'approving' ? (
              <button
                disabled
                className="text-[10px] font-bold px-3 py-1.5 rounded bg-green-500/20 text-green-400 border border-green-500/30 disabled:opacity-50 disabled:cursor-not-allowed disabled:saturate-0 flex items-center gap-1.5"
              >
                <div className="w-3 h-3 border-2 border-green-400/30 border-t-green-400 rounded-full animate-spin" />
                Approving...
              </button>
            ) : (
              <HoldToConfirm
                onConfirm={handleApprove}
                label="Approve & Create PR"
                holdLabel="Hold to confirm..."
                icon="check_circle"
                disabled={!!loading}
                className="text-[10px] font-bold px-3 py-1.5 rounded bg-green-500/20 text-green-400 border border-green-500/30 hover:bg-green-500/30"
              />
            )}
            <button
              onClick={handleReject}
              disabled={!!loading}
              className="text-[10px] font-bold px-3 py-1.5 rounded bg-red-500/20 text-red-400 border border-red-500/30 hover:bg-red-500/30 disabled:opacity-50 disabled:cursor-not-allowed disabled:saturate-0 flex items-center gap-1.5"
            >
              {loading === 'rejecting' ? (
                <div className="w-3 h-3 border-2 border-red-400/30 border-t-red-400 rounded-full animate-spin" />
              ) : (
                <span className="material-symbols-outlined text-xs" style={{ fontFamily: 'Material Symbols Outlined' }}>
                  cancel
                </span>
              )}
              {loading === 'rejecting' ? 'Rejecting...' : 'Reject'}
            </button>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="text"
              placeholder="Send feedback for revision..."
              value={feedbackText}
              onChange={(e) => setFeedbackText(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleFeedback()}
              className="flex-1 text-[11px] bg-slate-800/60 border border-slate-700/50 rounded px-2.5 py-1.5 text-slate-200 placeholder-slate-600 font-mono focus:outline-none focus:border-violet-500/50"
            />
            <button
              onClick={handleFeedback}
              disabled={!feedbackText.trim() || !!loading}
              className="text-[10px] font-bold px-3 py-1.5 rounded bg-violet-500/20 text-violet-400 border border-violet-500/30 hover:bg-violet-500/30 disabled:opacity-50 disabled:cursor-not-allowed disabled:saturate-0"
            >
              {loading === 'feedback' ? 'Sending...' : 'Send Feedback'}
            </button>
          </div>
        </div>
      )}
    </div>
  );

  const renderPRSuccess = () => {
    const prData = fixData?.pr_data;
    return (
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-emerald-400 text-base" style={{ fontFamily: 'Material Symbols Outlined' }}>
            check_circle
          </span>
          <span className="text-[11px] font-bold text-emerald-400">Pull Request Created Successfully</span>
        </div>

        {fixData?.pr_url && (
          <a
            href={fixData.pr_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[11px] text-[#07b6d5] hover:underline font-mono block"
          >
            {fixData.pr_url}
          </a>
        )}

        <div className="grid grid-cols-2 gap-2 text-[10px]">
          {fixData?.pr_number && (
            <div className="bg-slate-800/40 rounded px-2.5 py-1.5 border border-slate-700/30">
              <span className="text-slate-500">PR #</span>
              <span className="text-slate-200 font-mono ml-1">{fixData.pr_number}</span>
            </div>
          )}
          {prData?.branch_name && (
            <div className="bg-slate-800/40 rounded px-2.5 py-1.5 border border-slate-700/30">
              <span className="text-slate-500">Branch</span>
              <span className="text-slate-200 font-mono ml-1 truncate">{prData.branch_name}</span>
            </div>
          )}
          {prData?.commit_sha && (
            <div className="bg-slate-800/40 rounded px-2.5 py-1.5 border border-slate-700/30">
              <span className="text-slate-500">Commit</span>
              <span className="text-slate-200 font-mono ml-1">{prData.commit_sha.slice(0, 8)}</span>
            </div>
          )}
          {prData?.pr_title && (
            <div className="bg-slate-800/40 rounded px-2.5 py-1.5 border border-slate-700/30 col-span-2">
              <span className="text-slate-500">Title</span>
              <span className="text-slate-200 ml-1">{prData.pr_title}</span>
            </div>
          )}
        </div>

        {/* Show diff in PR success too */}
        {fixData?.diff && (
          <div>
            <button
              onClick={() => setShowDiff(!showDiff)}
              className="flex items-center gap-1.5 text-[10px] text-slate-400 hover:text-slate-300 mb-1.5"
            >
              <span
                className={`material-symbols-outlined text-xs transition-transform ${showDiff ? 'rotate-90' : ''}`}
                style={{ fontFamily: 'Material Symbols Outlined' }}
              >
                chevron_right
              </span>
              <span className="font-bold uppercase tracking-wider">Diff</span>
            </button>
            {showDiff && <DiffViewer diff={fixData.diff} />}
          </div>
        )}
      </div>
    );
  };

  const renderTerminalSection = () => {
    const maxReached = fixData && fixData.attempt_count >= fixData.max_attempts;
    return (
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-red-400 text-base" style={{ fontFamily: 'Material Symbols Outlined' }}>
            {fixStatus === 'rejected' ? 'block' : 'error'}
          </span>
          <span className="text-[11px] font-bold text-red-400">
            {fixStatus === 'rejected' ? 'Fix Rejected' : 'Fix Generation Failed'}
          </span>
        </div>
        {fixData?.fix_explanation && (
          <p className="text-[10px] text-slate-400">{fixData.fix_explanation}</p>
        )}
        {maxReached ? (
          <span className="text-[10px] text-slate-500 italic">Max attempts reached ({fixData!.max_attempts}). No further retries available.</span>
        ) : (
          <button
            onClick={handleGenerateFix}
            disabled={loading === 'generating'}
            className="text-[10px] font-bold px-3 py-1.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/30 disabled:opacity-50 disabled:cursor-not-allowed disabled:saturate-0 flex items-center gap-2"
          >
            <span className="material-symbols-outlined text-xs" style={{ fontFamily: 'Material Symbols Outlined' }}>
              refresh
            </span>
            {loading === 'generating' ? 'Starting...' : 'Retry Fix Generation'}
          </button>
        )}
      </div>
    );
  };

  const renderVerifiedReadOnly = () => (
    <div className="space-y-3">
      {fixData?.target_file && (
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-xs text-slate-500" style={{ fontFamily: 'Material Symbols Outlined' }}>
            description
          </span>
          <span className="text-[11px] font-mono text-blue-400">{fixData.target_file}</span>
        </div>
      )}
      {fixData?.fix_explanation && (
        <p className="text-[11px] text-slate-300 leading-relaxed">{fixData.fix_explanation}</p>
      )}
      {verification && renderVerificationResult(verification)}
      {fixData?.diff && (
        <div>
          <div className="flex items-center gap-2 mb-1.5">
            <button
              onClick={() => setShowDiff(!showDiff)}
              className="flex items-center gap-1.5 text-[10px] text-slate-400 hover:text-slate-300"
              aria-expanded={showDiff}
              aria-label={`${showDiff ? 'Hide' : 'Show'} diff`}
            >
              <span
                className={`material-symbols-outlined text-xs transition-transform duration-200 ${showDiff ? 'rotate-90' : ''}`}
                style={{ fontFamily: 'Material Symbols Outlined' }}
              >
                chevron_right
              </span>
              <span className="font-bold uppercase tracking-wider">Diff</span>
            </button>
            {showDiff && fixData?.diff && <CopyButton text={fixData.diff} size={11} />}
          </div>
          {showDiff && <DiffViewer diff={fixData.diff} />}
        </div>
      )}
    </div>
  );

  // ── Content by Status ────────────────────────────────────────────────

  const renderContent = () => {
    // Fallback: phase says fix_in_progress but no fix_data yet
    if (!fixData && phase === 'fix_in_progress') {
      return (
        <div className="flex items-center gap-3 py-2">
          <div className="w-5 h-5 border-2 border-slate-700 border-t-emerald-500 rounded-full animate-spin" />
          <span className="text-[11px] text-slate-300">Fix pipeline initializing...</span>
        </div>
      );
    }

    switch (fixStatus) {
      case 'not_started':
        return renderGenerateSection();
      case 'generating':
      case 'verification_in_progress':
      case 'pr_creating':
      case 'human_feedback':
        return renderProgressSection();
      case 'awaiting_review':
        return renderReviewSection();
      case 'verified':
      case 'verification_failed':
        return renderVerifiedReadOnly();
      case 'pr_created':
        return renderPRSuccess();
      case 'rejected':
      case 'failed':
        return renderTerminalSection();
      case 'approved':
        return renderProgressSection(); // brief transition state before PR creation
      default:
        return renderGenerateSection();
    }
  };

  return (
    <AgentFindingCard agent="D" title="Fix Pipeline">
      {/* Header row: status badge + attempt counter */}
      <div className="flex items-center gap-2 mb-3">
        <span className="material-symbols-outlined text-emerald-400 text-sm" style={{ fontFamily: 'Material Symbols Outlined' }}>
          build_circle
        </span>
        <FixStatusBadge status={fixStatus} />
        {renderAttemptCounter()}
      </div>

      {/* Error banner */}
      {error && (
        <div className="text-[10px] text-red-400 bg-red-500/10 border border-red-500/20 rounded px-3 py-1.5 mb-3">
          {error}
        </div>
      )}

      {renderContent()}
    </AgentFindingCard>
  );
};

export default FixPipelinePanel;
