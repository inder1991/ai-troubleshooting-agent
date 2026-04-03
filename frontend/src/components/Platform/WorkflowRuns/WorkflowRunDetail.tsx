import React, { useState, useEffect } from 'react';
import { API_BASE_URL } from '../../../services/api';
import type { WorkflowRun } from './useWorkflowRuns';
import { t } from '../../../styles/tokens';

const KNOWN_AGENTS = [
  'log_analysis_agent', 'metrics_agent', 'k8s_agent',
  'tracing_agent', 'code_navigator_agent', 'change_agent',
  'critic_agent', 'fix_generator',
];

type StepStatus = 'completed' | 'running' | 'pending' | 'failed' | 'skipped';

interface Step { id: string; status: StepStatus; }

const STATUS_CONFIG: Record<StepStatus, { color: string; icon: string }> = {
  completed: { color: t.green,     icon: 'check_circle' },
  running:   { color: t.cyan,      icon: 'progress_activity' },
  pending:   { color: t.textFaint, icon: 'radio_button_unchecked' },
  failed:    { color: t.red,       icon: 'error' },
  skipped:   { color: '#4a5568',   icon: 'remove_circle' },
};

function buildSteps(run: WorkflowRun): Step[] {
  return KNOWN_AGENTS.map(id => ({
    id,
    status: run.agents_completed.includes(id)
      ? 'completed'
      : run.agents_pending.includes(id)
      ? 'running'
      : 'pending',
  }));
}

interface Props { run: WorkflowRun; onClose: () => void; onNavigate?: (view: string) => void; }

const WorkflowRunDetail: React.FC<Props> = ({ run, onClose, onNavigate }) => {
  const [steps, setSteps] = useState<Step[]>(() => buildSteps(run));
  const [findings, setFindings] = useState<any[]>([]);
  const [approving, setApproving] = useState(false);
  const [rejecting, setRejecting] = useState(false);

  useEffect(() => {
    setSteps(buildSteps(run));
    window.fetch(`${API_BASE_URL}/api/v4/session/${run.id}/findings`)
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data?.findings) setFindings(data.findings); })
      .catch(() => {});
  }, [run]);

  const handleApprove = async () => {
    setApproving(true);
    try {
      await window.fetch(`${API_BASE_URL}/api/v4/session/${run.id}/fix/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approved: true }),
      });
    } catch { /* ignore */ }
    setApproving(false);
  };

  const handleReject = async () => {
    setRejecting(true);
    try {
      await window.fetch(`${API_BASE_URL}/api/v4/session/${run.id}/fix/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approved: false }),
      });
    } catch { /* ignore */ }
    setRejecting(false);
  };

  const confidence = run.overall_confidence;
  const confidencePct = confidence !== undefined ? Math.round(confidence * 100) : 0;
  const confidenceColor = confidence !== undefined
    ? confidence > 0.8 ? t.green : confidence > 0.5 ? t.amber : t.red
    : t.textFaint;

  return (
    <div className="h-full flex flex-col overflow-hidden" style={{ background: t.bgSurface }}>
      <div
        className="flex items-center justify-between px-5 py-4 border-b flex-shrink-0"
        style={{ borderColor: t.borderDefault }}
      >
        <div>
          <div className="text-sm font-display font-bold" style={{ color: t.textPrimary }}>{run.service_name}</div>
          <div className="text-[10px] font-sans mt-0.5" style={{ color: t.textMuted }}>
            {run.workflow_name} · {new Date(run.started_at).toLocaleString()}
          </div>
        </div>
        <div className="flex items-center">
          {run.status === 'failed' && onNavigate && (
            <button
              onClick={() => onNavigate('workflow-builder')}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-sans mr-2"
              style={{
                background: t.redBg,
                border: `1px solid ${t.redBorder}`,
                color: t.red,
              }}
              title="Open this workflow in the builder to debug"
            >
              <span className="material-symbols-outlined" style={{ fontSize: 13 }}>bug_report</span>
              Debug in Builder
            </button>
          )}
          <button onClick={onClose} aria-label="Close detail panel">
            <span className="material-symbols-outlined" style={{ fontSize: 18, color: t.textMuted }}>close</span>
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-auto px-5 py-4 space-y-4">
        {/* Steps */}
        <div>
          <div className="text-[10px] font-sans uppercase tracking-widest mb-2" style={{ color: t.textFaint }}>Steps</div>
          <div className="divide-y" style={{ borderColor: t.bgTrack }}>
            {steps.map(step => {
              const cfg = STATUS_CONFIG[step.status];
              const finding = findings.find((f: any) =>
                f.source_agent === step.id || f.agent === step.id
              );
              return (
                <div key={step.id} className="flex items-start gap-3 py-2.5">
                  <span className="material-symbols-outlined flex-shrink-0 mt-0.5"
                    style={{ fontSize: 14, color: cfg.color }}>{cfg.icon}</span>
                  <div className="flex-1 min-w-0">
                    <div className="text-[11px] font-mono" style={{ color: t.textPrimary }}>{step.id}</div>
                    {finding && (
                      <div className="text-[10px] font-sans mt-0.5 truncate" style={{ color: t.textSecondary }}>
                        {finding.summary || finding.title}
                      </div>
                    )}
                  </div>
                  <span className="text-[10px] font-sans flex-shrink-0" style={{ color: cfg.color }}>
                    {step.status}
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Human gate */}
        {run.status === 'waiting_approval' && (
          <div
            className="rounded-lg p-4"
            style={{ background: t.amberBg, border: `1px solid ${t.amberBorder}` }}
          >
            <div className="flex items-center gap-2 mb-2">
              <span className="material-symbols-outlined" style={{ fontSize: 16, color: t.amber }}>pending_actions</span>
              <span className="text-xs font-display font-semibold" style={{ color: t.amber }}>Awaiting Approval</span>
            </div>
            <div className="text-[11px] font-sans mb-3" style={{ color: t.textSecondary }}>
              fix_generator has proposed a fix. Review and approve to create a PR.
            </div>
            <div className="flex gap-2">
              <button
                onClick={handleApprove}
                disabled={approving || rejecting}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-sans"
                style={{
                  background: t.greenBg,
                  border: `1px solid ${t.greenBorder}`,
                  color: t.green,
                  opacity: (approving || rejecting) ? 0.6 : 1,
                }}
              >
                <span className="material-symbols-outlined" style={{ fontSize: 13 }}>check</span>
                {approving ? 'Approving...' : 'Approve & Create PR'}
              </button>
              <button
                onClick={handleReject}
                disabled={approving || rejecting}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-sans"
                style={{
                  background: 'transparent',
                  border: `1px solid ${t.redBorder}`,
                  color: t.red,
                  opacity: (approving || rejecting) ? 0.6 : 1,
                }}
              >
                <span className="material-symbols-outlined" style={{ fontSize: 13 }}>close</span>
                {rejecting ? 'Rejecting...' : 'Reject'}
              </button>
            </div>
          </div>
        )}

        {/* Confidence bar */}
        {confidence !== undefined && (
          <div className="pt-1">
            <div className="text-[10px] font-sans uppercase tracking-widest mb-2" style={{ color: t.textFaint }}>
              Overall Confidence
            </div>
            <div className="flex items-center gap-3">
              <div
                className="flex-1 h-1.5 rounded-full overflow-hidden"
                style={{ background: t.bgTrack }}
                role="progressbar"
                aria-valuenow={confidencePct}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label={`Confidence: ${confidencePct}%`}
              >
                <div
                  className="h-full rounded-full transition-all"
                  style={{ width: `${confidencePct}%`, background: confidenceColor }}
                />
              </div>
              <span className="text-sm font-mono font-bold" style={{ color: t.textPrimary }}>
                {confidencePct}%
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default WorkflowRunDetail;
