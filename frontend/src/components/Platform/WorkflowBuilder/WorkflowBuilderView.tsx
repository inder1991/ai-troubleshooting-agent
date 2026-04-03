import React, { useState, useMemo } from 'react';
import { parseWorkflowYaml, APP_DIAGNOSTICS_TEMPLATE } from './workflowParser';
import WorkflowDagPreview from './WorkflowDagPreview';
import WorkflowLibraryView from './WorkflowLibraryView';
import AgentBrowserPanel from './AgentBrowserPanel';

const LS_KEY = 'platform_workflow_builder_yaml';
const LS_SAVED_KEY = 'platform_saved_workflows';

interface SavedWorkflow { id: string; name: string; yaml: string; savedAt: string; }

const BLANK_TEMPLATE = `id: new_workflow
name: New Workflow
version: "1.0"
trigger: [api]

steps:
  - id: step_1
    agent: log_analysis_agent
    depends_on: []
`;

const WorkflowBuilderView: React.FC = () => {
  const [mode, setMode] = useState<'library' | 'editor'>('library');
  const [yaml, setYaml] = useState<string>(() => localStorage.getItem(LS_KEY) || APP_DIAGNOSTICS_TEMPLATE);
  const [saved, setSaved] = useState(false);
  const [showAgents, setShowAgents] = useState(true);
  const [backHovered, setBackHovered] = useState(false);

  const parsed = useMemo(() => parseWorkflowYaml(yaml), [yaml]);

  const openWorkflow = (workflowYaml: string) => {
    setYaml(workflowYaml);
    localStorage.setItem(LS_KEY, workflowYaml);
    setMode('editor');
  };

  const handleSave = () => {
    localStorage.setItem(LS_KEY, yaml);
    const id = parsed.id || `workflow_${Date.now()}`;
    const name = parsed.name || 'Untitled Workflow';
    try {
      const existing: SavedWorkflow[] = JSON.parse(localStorage.getItem(LS_SAVED_KEY) || '[]');
      const filtered = existing.filter(w => w.id !== id);
      const updated = [{ id, name, yaml, savedAt: new Date().toISOString() }, ...filtered];
      localStorage.setItem(LS_SAVED_KEY, JSON.stringify(updated));
    } catch { /* noop */ }
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  if (mode === 'library') {
    return (
      <WorkflowLibraryView
        onOpen={openWorkflow}
        onNew={() => openWorkflow(BLANK_TEMPLATE)}
      />
    );
  }

  return (
    <div className="flex flex-col h-full" style={{ background: '#0a1214' }}>
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-3 border-b flex-shrink-0" style={{ borderColor: '#1e2a2e' }}>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setMode('library')}
            onMouseEnter={() => setBackHovered(true)}
            onMouseLeave={() => setBackHovered(false)}
            className="flex items-center gap-1 text-xs font-sans transition-colors"
            style={{ color: backHovered ? '#e8e0d4' : '#64748b' }}
          >
            <span className="material-symbols-outlined" style={{ fontSize: 14 }}>arrow_back</span>
            Workflows
          </button>
          <span style={{ color: '#1e2a2e' }}>·</span>
          <div>
            <span className="text-sm font-display font-semibold" style={{ color: '#e8e0d4' }}>
              {parsed.name || 'Untitled Workflow'}
            </span>
            {parsed.id && (
              <span className="text-[10px] font-mono ml-2" style={{ color: '#64748b' }}>
                {parsed.id}
              </span>
            )}
          </div>
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
          <button
            onClick={() => setShowAgents(v => !v)}
            className="flex items-center gap-1 px-2.5 py-1.5 rounded text-xs font-sans"
            style={{
              background: showAgents ? 'rgba(7,182,213,0.08)' : 'transparent',
              border: `1px solid ${showAgents ? 'rgba(7,182,213,0.3)' : '#1e2a2e'}`,
              color: showAgents ? '#07b6d5' : '#64748b',
            }}
            title="Toggle agent browser"
          >
            <span className="material-symbols-outlined" style={{ fontSize: 13 }}>smart_toy</span>
            Agents
          </button>
          <button onClick={handleSave}
            className="flex items-center gap-1 px-3 py-1.5 rounded text-xs font-sans"
            style={{ background: 'rgba(7,182,213,0.1)', border: '1px solid rgba(7,182,213,0.3)', color: saved ? '#22c55e' : '#07b6d5' }}>
            <span className="material-symbols-outlined" style={{ fontSize: 13 }}>{saved ? 'check' : 'save'}</span>
            {saved ? 'Saved' : 'Save'}
          </button>
        </div>
      </div>

      {/* Three-panel layout: agents | yaml | dag */}
      <div className="flex flex-1 overflow-hidden">
        {showAgents && (
          <div className="flex-shrink-0 border-r overflow-hidden" style={{ width: 200, borderColor: '#1e2a2e' }}>
            <AgentBrowserPanel onInsertAgent={(agentId) => {
              navigator.clipboard.writeText(`agent: ${agentId}`).catch(() => {});
            }} />
          </div>
        )}

        {/* YAML Editor */}
        <div className="flex flex-col border-r" style={{ flex: 1, borderColor: '#1e2a2e' }}>
          <div className="px-4 py-2 border-b flex-shrink-0 flex items-center justify-between" style={{ borderColor: '#1e2a2e' }}>
            <span className="text-[10px] font-sans uppercase tracking-widest" style={{ color: '#3d4a50' }}>YAML</span>
            <span className="text-[10px] font-mono" style={{ color: '#3d4a50' }}>{parsed.steps.length} steps</span>
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
        <div className="flex flex-col" style={{ width: '40%', minWidth: 280 }}>
          <div className="px-4 py-2 border-b flex-shrink-0" style={{ borderColor: '#1e2a2e' }}>
            <span className="text-[10px] font-sans uppercase tracking-widest" style={{ color: '#3d4a50' }}>Preview</span>
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
