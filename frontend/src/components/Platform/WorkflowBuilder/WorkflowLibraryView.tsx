import React, { useState, useEffect } from 'react';
import { WORKFLOW_TEMPLATES } from './workflowParser';
import type { WorkflowTemplate } from './workflowParser';

const LS_SAVED_KEY = 'platform_saved_workflows';

interface SavedWorkflow {
  id: string;
  name: string;
  yaml: string;
  savedAt: string;
}

function loadSaved(): SavedWorkflow[] {
  try {
    return JSON.parse(localStorage.getItem(LS_SAVED_KEY) || '[]');
  } catch {
    return [];
  }
}

interface Props {
  onOpen: (yaml: string) => void;
  onNew: () => void;
}

const WorkflowLibraryView: React.FC<Props> = ({ onOpen, onNew }) => {
  const [saved, setSaved] = useState<SavedWorkflow[]>([]);

  useEffect(() => {
    setSaved(loadSaved());
  }, []);

  const handleDeleteSaved = (id: string) => {
    const updated = saved.filter(w => w.id !== id);
    setSaved(updated);
    localStorage.setItem(LS_SAVED_KEY, JSON.stringify(updated));
  };

  return (
    <div className="flex flex-col h-full overflow-auto" style={{ background: '#0a1214' }}>
      {/* Header */}
      <div className="flex items-end justify-between px-8 pt-8 pb-6 flex-shrink-0">
        <div>
          <h1 className="text-2xl font-display font-bold" style={{ color: '#e8e0d4' }}>Workflows</h1>
          <p className="text-sm font-sans mt-1" style={{ color: '#64748b' }}>
            Start from a template or open a saved workflow.
          </p>
        </div>
        <button
          onClick={onNew}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-sans"
          style={{
            background: 'rgba(7,182,213,0.1)',
            border: '1px solid rgba(7,182,213,0.3)',
            color: '#07b6d5',
          }}
        >
          <span className="material-symbols-outlined" style={{ fontSize: 16 }}>add</span>
          New Workflow
        </button>
      </div>

      <div className="flex-1 px-8 pb-8 space-y-8">
        {/* Templates */}
        <section>
          <h2 className="text-xs font-sans uppercase tracking-widest mb-4" style={{ color: '#3d4a50' }}>
            Templates
          </h2>
          <div className="grid grid-cols-2 gap-4" style={{ maxWidth: 820 }}>
            {WORKFLOW_TEMPLATES.map(template => (
              <TemplateCard
                key={template.id}
                template={template}
                onOpen={() => onOpen(template.yaml)}
              />
            ))}
          </div>
        </section>

        {/* Saved workflows */}
        {saved.length > 0 && (
          <section>
            <h2 className="text-xs font-sans uppercase tracking-widest mb-4" style={{ color: '#3d4a50' }}>
              Saved
            </h2>
            <div className="space-y-px" style={{ maxWidth: 820 }}>
              {saved.map(workflow => (
                <SavedRow
                  key={workflow.id}
                  workflow={workflow}
                  onOpen={() => onOpen(workflow.yaml)}
                  onDelete={() => handleDeleteSaved(workflow.id)}
                />
              ))}
            </div>
          </section>
        )}

        {saved.length === 0 && (
          <p className="text-xs font-sans" style={{ color: '#3d4a50' }}>
            No saved workflows yet — edit a template and click Save.
          </p>
        )}
      </div>
    </div>
  );
};

const TemplateCard: React.FC<{ template: WorkflowTemplate; onOpen: () => void }> = ({ template, onOpen }) => {
  const [hovered, setHovered] = useState(false);
  return (
    <div
      className="flex flex-col gap-3 p-5 rounded-lg cursor-pointer transition-colors"
      style={{
        background: '#0c1a1f',
        border: `1px solid ${hovered ? '#07b6d540' : '#1e2a2e'}`,
      }}
      onClick={onOpen}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded flex items-center justify-center flex-shrink-0"
            style={{ background: 'rgba(7,182,213,0.08)', border: '1px solid rgba(7,182,213,0.15)' }}>
            <span className="material-symbols-outlined" style={{ fontSize: 16, color: '#07b6d5' }}>
              {template.icon}
            </span>
          </div>
          <div>
            <div className="text-sm font-display font-semibold" style={{ color: '#e8e0d4' }}>
              {template.name}
            </div>
            <div className="text-[10px] font-mono mt-0.5" style={{ color: '#64748b' }}>
              {template.stepCount} steps
            </div>
          </div>
        </div>
        <span
          className="material-symbols-outlined transition-opacity"
          style={{ fontSize: 16, color: '#07b6d5', opacity: hovered ? 1 : 0 }}
        >
          arrow_forward
        </span>
      </div>
      <p className="text-xs font-sans leading-relaxed" style={{ color: '#64748b' }}>
        {template.description}
      </p>
    </div>
  );
};

interface SavedRowProps {
  workflow: SavedWorkflow;
  onOpen: () => void;
  onDelete: () => void;
}

const SavedRow: React.FC<SavedRowProps> = ({ workflow, onOpen, onDelete }) => {
  const [hovered, setHovered] = useState(false);
  return (
    <div
      className="flex items-center gap-3 px-4 py-3 rounded cursor-pointer"
      style={{
        background: '#0c1a1f',
        border: '1px solid #1a2428',
      }}
      onClick={onOpen}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <span className="material-symbols-outlined flex-shrink-0" style={{ fontSize: 16, color: '#3d4a50' }}>
        description
      </span>
      <div className="flex-1 min-w-0">
        <div className="text-sm font-display font-medium truncate" style={{ color: '#e8e0d4' }}>{workflow.name}</div>
        <div className="text-[10px] font-sans mt-0.5" style={{ color: '#64748b' }}>
          Saved {new Date(workflow.savedAt).toLocaleDateString()}
        </div>
      </div>
      <button
        onClick={e => { e.stopPropagation(); onDelete(); }}
        className="p-1 rounded transition-opacity"
        style={{ color: '#ef4444', opacity: hovered ? 1 : 0 }}
        title="Delete"
      >
        <span className="material-symbols-outlined" style={{ fontSize: 14 }}>delete</span>
      </button>
      <span
        className="material-symbols-outlined transition-opacity"
        style={{ fontSize: 16, color: '#07b6d5', opacity: hovered ? 1 : 0 }}
      >
        arrow_forward
      </span>
    </div>
  );
};

export default WorkflowLibraryView;
