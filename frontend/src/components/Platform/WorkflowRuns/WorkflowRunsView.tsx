import React, { useState } from 'react';
import { useWorkflowRuns } from './useWorkflowRuns';
import WorkflowRunCard from './WorkflowRunCard';
import WorkflowRunDetail from './WorkflowRunDetail';
import type { WorkflowRun } from './useWorkflowRuns';
import { t } from '../../../styles/tokens';

interface Props { onNavigate?: (view: string) => void; }

const WorkflowRunsView: React.FC<Props> = ({ onNavigate }) => {
  const { runs, loading, refresh } = useWorkflowRuns();
  const [selected, setSelected] = useState<WorkflowRun | null>(null);

  return (
    <div className="flex h-full" style={{ background: t.bgBase }}>
      <div
        className="flex flex-col border-r"
        style={{ width: selected ? 320 : '100%', borderColor: t.borderDefault, transition: 'width 0.2s' }}
      >
        <div
          className="flex items-center justify-between px-5 py-4 border-b flex-shrink-0"
          style={{ borderColor: t.borderDefault }}
        >
          <div>
            <h1 className="text-base font-display font-bold" style={{ color: t.textPrimary }}>Workflow Runs</h1>
            <p className="text-xs font-sans mt-0.5" style={{ color: t.textMuted }}>
              {runs.length} run{runs.length !== 1 ? 's' : ''}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={refresh} aria-label="Refresh workflow runs" style={{ color: t.textMuted }}>
              <span className="material-symbols-outlined" style={{ fontSize: 16 }}>refresh</span>
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-auto">
          {loading && (
            <div className="flex items-center justify-center h-32 text-xs font-sans" style={{ color: t.textMuted }}>
              Loading...
            </div>
          )}
          {!loading && runs.length === 0 && (
            <div className="flex flex-col items-center justify-center h-48 gap-3">
              <span className="material-symbols-outlined" style={{ fontSize: 36, color: t.borderDefault }}>play_circle</span>
              <div className="text-xs font-sans text-center" style={{ color: t.textMuted }}>
                No workflow runs yet.<br />
                <span style={{ color: t.textFaint }}>Start an investigation from App Diagnostics.</span>
              </div>
            </div>
          )}
          {!loading && runs.map(run => (
            <WorkflowRunCard
              key={run.id}
              run={run}
              selected={selected?.id === run.id}
              onClick={() => setSelected(selected?.id === run.id ? null : run)}
            />
          ))}
        </div>
      </div>

      {selected && (
        <div className="flex-1 overflow-hidden">
          <WorkflowRunDetail run={selected} onClose={() => setSelected(null)} onNavigate={onNavigate} />
        </div>
      )}
    </div>
  );
};

export default WorkflowRunsView;
