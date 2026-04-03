import React, { useState, useMemo } from 'react';
import { parseWorkflowYaml, APP_DIAGNOSTICS_TEMPLATE } from './workflowParser';
import WorkflowDagPreview from './WorkflowDagPreview';

const LS_KEY = 'platform_workflow_builder_yaml';

const WorkflowBuilderView: React.FC = () => {
  const [yaml, setYaml] = useState<string>(() =>
    localStorage.getItem(LS_KEY) || APP_DIAGNOSTICS_TEMPLATE
  );
  const [saved, setSaved] = useState(false);

  const parsed = useMemo(() => parseWorkflowYaml(yaml), [yaml]);

  const handleSave = () => {
    localStorage.setItem(LS_KEY, yaml);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="flex flex-col h-full" style={{ background: '#0a1214' }}>
      {/* Toolbar */}
      <div className="flex items-center justify-between px-5 py-3 border-b flex-shrink-0" style={{ borderColor: '#1e2a2e' }}>
        <div>
          <h1 className="text-base font-display font-bold" style={{ color: '#e8e0d4' }}>
            {parsed.name || 'Untitled Workflow'}
          </h1>
          {parsed.id && (
            <div className="text-[10px] font-mono mt-0.5" style={{ color: '#64748b' }}>id: {parsed.id}</div>
          )}
        </div>
        <div className="flex items-center gap-2">
          {parsed.errors.length > 0 ? (
            <span className="flex items-center gap-1 text-[10px] font-sans px-2 py-1 rounded"
              style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', color: '#ef4444' }}>
              <span className="material-symbols-outlined" style={{ fontSize: 12 }}>error</span>
              {parsed.errors.length} error{parsed.errors.length !== 1 ? 's' : ''}
            </span>
          ) : (
            <span className="flex items-center gap-1 text-[10px] font-sans px-2 py-1 rounded"
              style={{ background: 'rgba(34,197,94,0.1)', border: '1px solid rgba(34,197,94,0.3)', color: '#22c55e' }}>
              <span className="material-symbols-outlined" style={{ fontSize: 12 }}>check_circle</span>
              Valid
            </span>
          )}

          <button onClick={handleSave}
            className="flex items-center gap-1 px-3 py-1.5 rounded text-xs font-sans"
            style={{ background: 'rgba(7,182,213,0.1)', border: '1px solid rgba(7,182,213,0.3)', color: saved ? '#22c55e' : '#07b6d5' }}>
            <span className="material-symbols-outlined" style={{ fontSize: 13 }}>{saved ? 'check' : 'save'}</span>
            {saved ? 'Saved' : 'Save'}
          </button>

        </div>
      </div>

      {/* Split: YAML editor left, DAG preview right */}
      <div className="flex flex-1 overflow-hidden">
        {/* YAML Editor */}
        <div className="flex flex-col border-r" style={{ width: '50%', borderColor: '#1e2a2e' }}>
          <div className="px-4 py-2 border-b flex-shrink-0 flex items-center justify-between" style={{ borderColor: '#1e2a2e' }}>
            <span className="text-[10px] font-sans uppercase tracking-widest" style={{ color: '#3d4a50' }}>Workflow YAML</span>
            <span className="text-[10px] font-sans" style={{ color: '#3d4a50' }}>{parsed.steps.length} steps</span>
          </div>
          <textarea
            value={yaml}
            onChange={e => setYaml(e.target.value)}
            spellCheck={false}
            className="flex-1 resize-none outline-none p-4 text-xs font-mono"
            style={{ background: '#080f12', color: '#e8e0d4', lineHeight: 1.6 }}
          />
          {parsed.errors.length > 0 && (
            <div className="border-t px-4 py-2 flex-shrink-0 space-y-1" style={{ borderColor: '#1e2a2e', background: '#0c1214' }}>
              {parsed.errors.map((e, i) => (
                <div key={i} className="flex items-start gap-1.5 text-[10px] font-sans" style={{ color: '#ef4444' }}>
                  <span className="material-symbols-outlined flex-shrink-0" style={{ fontSize: 12 }}>error</span>
                  {e}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* DAG Preview */}
        <div className="flex flex-col" style={{ width: '50%' }}>
          <div className="px-4 py-2 border-b flex-shrink-0 flex items-center justify-between" style={{ borderColor: '#1e2a2e' }}>
            <span className="text-[10px] font-sans uppercase tracking-widest" style={{ color: '#3d4a50' }}>DAG Preview</span>
          </div>
          <div className="flex-1">
            <WorkflowDagPreview workflow={parsed} />
          </div>
        </div>
      </div>
    </div>
  );
};

export default WorkflowBuilderView;
