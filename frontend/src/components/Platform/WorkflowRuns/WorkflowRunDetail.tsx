import React, { useState, useEffect } from 'react';
import { API_BASE_URL } from '../../../services/api';
import type { WorkflowRun } from './useWorkflowRuns';

const KNOWN_AGENTS = [
  'log_analysis_agent', 'metrics_agent', 'k8s_agent',
  'tracing_agent', 'code_navigator_agent', 'change_agent',
  'critic_agent', 'fix_generator',
];

type StepStatus = 'completed' | 'running' | 'pending' | 'failed' | 'skipped';

interface Step { id: string; status: StepStatus; }

const STATUS_CONFIG: Record<StepStatus, { color: string; icon: string }> = {
  completed: { color: '#22c55e', icon: 'check_circle' },
  running:   { color: '#07b6d5', icon: 'progress_activity' },
  pending:   { color: '#3d4a50', icon: 'radio_button_unchecked' },
  failed:    { color: '#ef4444', icon: 'error' },
  skipped:   { color: '#4a5568', icon: 'remove_circle' },
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
    await window.fetch(`${API_BASE_URL}/api/v4/session/${run.id}/fix/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ approved: false }),
    });
  };

  return (
    <div className="h-full flex flex-col overflow-hidden" style={{ background: '#0c1a1f' }}>
      <div className="flex items-center justify-between px-5 py-4 border-b flex-shrink-0" style={{ borderColor: '#1e2a2e' }}>
        <div>
          <div className="text-sm font-display font-bold" style={{ color: '#e8e0d4' }}>{run.service_name}</div>
          <div className="text-[10px] font-sans mt-0.5" style={{ color: '#64748b' }}>
            {run.workflow_name} · {new Date(run.started_at).toLocaleString()}
          </div>
        </div>
        <div className="flex items-center">
          {run.status === 'failed' && onNavigate && (
            <button
              onClick={() => onNavigate('workflow-builder')}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-sans mr-2"
              style={{
                background: 'rgba(239,68,68,0.08)',
                border: '1px solid rgba(239,68,68,0.3)',
                color: '#ef4444',
              }}
              title="Open this workflow in the builder to debug"
            >
              <span className="material-symbols-outlined" style={{ fontSize: 13 }}>bug_report</span>
              Debug in Builder
            </button>
          )}
          <button onClick={onClose}>
            <span className="material-symbols-outlined" style={{ fontSize: 18, color: '#64748b' }}>close</span>
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-auto px-5 py-4 space-y-4">
        {/* Steps */}
        <div>
          <div className="text-[10px] font-sans uppercase tracking-widest mb-2" style={{ color: '#3d4a50' }}>Steps</div>
          <div className="divide-y" style={{ borderColor: '#1a2428' }}>
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
                    <div className="text-[11px] font-mono" style={{ color: '#e8e0d4' }}>{step.id}</div>
                    {finding && (
                      <div className="text-[10px] font-sans mt-0.5 truncate" style={{ color: '#9a9080' }}>
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
          <div className="rounded-lg p-4" style={{ background: 'rgba(245,158,11,0.06)', border: '1px solid rgba(245,158,11,0.3)' }}>
            <div className="flex items-center gap-2 mb-2">
              <span className="material-symbols-outlined" style={{ fontSize: 16, color: '#f59e0b' }}>pending_actions</span>
              <span className="text-xs font-display font-semibold" style={{ color: '#f59e0b' }}>Awaiting Approval</span>
            </div>
            <div className="text-[11px] font-sans mb-3" style={{ color: '#9a9080' }}>
              fix_generator has proposed a fix. Review and approve to create a PR.
            </div>
            <div className="flex gap-2">
              <button onClick={handleApprove} disabled={approving}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-sans"
                style={{ background: 'rgba(34,197,94,0.1)', border: '1px solid rgba(34,197,94,0.4)', color: '#22c55e' }}>
                <span className="material-symbols-outlined" style={{ fontSize: 13 }}>check</span>
                {approving ? 'Approving...' : 'Approve & Create PR'}
              </button>
              <button onClick={handleReject}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-sans"
                style={{ background: 'transparent', border: '1px solid rgba(239,68,68,0.4)', color: '#ef4444' }}>
                <span className="material-symbols-outlined" style={{ fontSize: 13 }}>close</span>
                Reject
              </button>
            </div>
          </div>
        )}

        {/* Confidence bar */}
        {run.overall_confidence !== undefined && (
          <div className="pt-1">
            <div className="text-[10px] font-sans uppercase tracking-widest mb-2" style={{ color: '#3d4a50' }}>Overall Confidence</div>
            <div className="flex items-center gap-3">
              <div className="flex-1 h-1.5 rounded-full overflow-hidden" style={{ background: '#1a2428' }}>
                <div className="h-full rounded-full transition-all" style={{
                  width: `${run.overall_confidence * 100}%`,
                  background: run.overall_confidence > 0.8 ? '#22c55e' : run.overall_confidence > 0.5 ? '#f59e0b' : '#ef4444',
                }} />
              </div>
              <span className="text-sm font-mono font-bold" style={{ color: '#e8e0d4' }}>
                {Math.round(run.overall_confidence * 100)}%
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default WorkflowRunDetail;
