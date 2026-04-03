import React, { useState } from 'react';
import { useWorkflowRuns } from './useWorkflowRuns';
import WorkflowRunCard from './WorkflowRunCard';
import WorkflowRunDetail from './WorkflowRunDetail';
import type { WorkflowRun } from './useWorkflowRuns';

const WorkflowRunsView: React.FC = () => {
  const { runs, loading, refresh } = useWorkflowRuns();
  const [selected, setSelected] = useState<WorkflowRun | null>(null);

  return (
    <div className="flex h-full" style={{ background: '#0a1214' }}>
      <div className="flex flex-col border-r" style={{ width: selected ? 320 : '100%', borderColor: '#1e2a2e', transition: 'width 0.2s' }}>
        <div className="flex items-center justify-between px-5 py-4 border-b flex-shrink-0" style={{ borderColor: '#1e2a2e' }}>
          <div>
            <h1 className="text-base font-display font-bold" style={{ color: '#e8e0d4' }}>Workflow Runs</h1>
            <p className="text-xs font-sans mt-0.5" style={{ color: '#64748b' }}>
              {runs.length} run{runs.length !== 1 ? 's' : ''}
            </p>
          </div>
          <div className="flex items-center gap-2">
<button onClick={refresh} style={{ color: '#64748b' }}>
              <span className="material-symbols-outlined" style={{ fontSize: 16 }}>refresh</span>
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-auto">
          {loading && (
            <div className="flex items-center justify-center h-32 text-xs font-sans" style={{ color: '#64748b' }}>
              Loading...
            </div>
          )}
          {!loading && runs.length === 0 && (
            <div className="flex flex-col items-center justify-center h-48 gap-3">
              <span className="material-symbols-outlined" style={{ fontSize: 36, color: '#1e2a2e' }}>play_circle</span>
              <div className="text-xs font-sans text-center" style={{ color: '#64748b' }}>
                No workflow runs yet.<br />
                <span style={{ color: '#3d4a50' }}>Start an investigation from App Diagnostics.</span>
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
          <WorkflowRunDetail run={selected} onClose={() => setSelected(null)} />
        </div>
      )}
    </div>
  );
};

export default WorkflowRunsView;
