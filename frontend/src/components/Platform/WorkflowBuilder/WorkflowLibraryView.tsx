import React, { useState, useEffect } from 'react';
import { WORKFLOW_TEMPLATES } from './workflowParser';
import type { WorkflowTemplate } from './workflowParser';
import { t } from '../../../styles/tokens';

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

function timeAgo(date: string): string {
  const now = Date.now();
  const then = new Date(date).getTime();
  const diffMs = now - then;
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHr = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHr / 24);

  if (diffSec < 60) return 'just now';
  if (diffMin < 60) return `${diffMin} minute${diffMin === 1 ? '' : 's'} ago`;
  if (diffHr < 24) return `${diffHr} hour${diffHr === 1 ? '' : 's'} ago`;
  if (diffDay < 7) return `${diffDay} day${diffDay === 1 ? '' : 's'} ago`;
  return new Date(date).toLocaleDateString();
}

interface Props {
  onOpen: (yaml: string) => void;
  onNew: () => void;
}

const WorkflowLibraryView: React.FC<Props> = ({ onOpen, onNew }) => {
  const [saved, setSaved] = useState<SavedWorkflow[]>([]);
  const [query, setQuery] = useState('');

  useEffect(() => {
    setSaved(loadSaved());
  }, []);

  const handleDeleteSaved = (id: string) => {
    const updated = saved.filter(w => w.id !== id);
    setSaved(updated);
    localStorage.setItem(LS_SAVED_KEY, JSON.stringify(updated));
  };

  const q = query.trim().toLowerCase();

  const filteredTemplates = WORKFLOW_TEMPLATES.filter(tmpl => {
    if (!q) return true;
    return (
      tmpl.name.toLowerCase().includes(q) ||
      tmpl.description.toLowerCase().includes(q)
    );
  });

  const filteredSaved = saved.filter(w => {
    if (!q) return true;
    return w.name.toLowerCase().includes(q);
  });

  const [heroTemplate, ...restTemplates] = filteredTemplates;

  return (
    <div
      className="flex flex-col h-full overflow-auto"
      style={{ background: t.bgBase }}
    >
      {/* Header */}
      <div
        className="flex items-end justify-between px-8 pt-8 pb-4 flex-shrink-0"
      >
        <div>
          <h1
            className="text-2xl font-display font-bold"
            style={{ color: t.textPrimary }}
          >
            Workflows
          </h1>
          <p className="text-sm font-sans mt-1" style={{ color: t.textMuted }}>
            Start from a template or open a saved workflow.
          </p>
        </div>
        <button
          onClick={onNew}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-sans font-medium transition-colors focus:outline-none focus:ring-2"
          style={{
            background: t.cyanBg,
            border: `1px solid ${t.cyanBorder}`,
            color: t.cyan,
          }}
          onFocus={e => {
            (e.currentTarget as HTMLElement).style.outline = `2px solid ${t.cyan}`;
            (e.currentTarget as HTMLElement).style.outlineOffset = '2px';
          }}
          onBlur={e => {
            (e.currentTarget as HTMLElement).style.outline = 'none';
          }}
        >
          <span className="material-symbols-outlined" aria-hidden="true" style={{ fontSize: 16 }}>
            add
          </span>
          New Workflow
        </button>
      </div>

      {/* Search bar */}
      <div className="px-8 pb-6 flex-shrink-0">
        <div className="relative" style={{ maxWidth: 820 }}>
          <span
            className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none"
            style={{ fontSize: 16, color: t.textFaint }}
          >
            search
          </span>
          <input
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Search workflows and templates..."
            aria-label="Search workflows and templates"
            className="w-full pl-9 pr-4 py-2 rounded-lg text-sm font-sans"
            style={{
              background: t.bgSurface,
              border: `1px solid ${t.borderDefault}`,
              color: t.textPrimary,
              outline: 'none',
            }}
            onFocus={e => {
              e.currentTarget.style.borderColor = t.cyanBorder;
            }}
            onBlur={e => {
              e.currentTarget.style.borderColor = t.borderDefault;
            }}
          />
        </div>
      </div>

      <div className="flex-1 px-8 pb-8 space-y-8">
        {/* Templates section */}
        {filteredTemplates.length > 0 && (
          <section>
            <h2
              className="text-xs font-sans uppercase tracking-widest mb-4"
              style={{ color: t.textFaint }}
            >
              Templates
            </h2>

            <div className="space-y-2" style={{ maxWidth: 820 }}>
              {/* Hero card — first template */}
              {heroTemplate && (
                <HeroTemplateCard
                  template={heroTemplate}
                  onOpen={() => onOpen(heroTemplate.yaml)}
                />
              )}

              {/* Compact rows — remaining templates */}
              {restTemplates.map(tmpl => (
                <CompactTemplateRow
                  key={tmpl.id}
                  template={tmpl}
                  onOpen={() => onOpen(tmpl.yaml)}
                />
              ))}

              {/* Request a template placeholder */}
              <div
                role="button"
                tabIndex={0}
                className="flex items-center gap-3 px-4 py-3 rounded-lg cursor-pointer"
                style={{
                  border: `1px dashed ${t.borderDefault}`,
                  color: t.textFaint,
                }}
                onKeyDown={e => {
                  if (e.key === 'Enter' || e.key === ' ') e.preventDefault();
                }}
                onFocus={e => {
                  (e.currentTarget as HTMLElement).style.outline = `2px solid ${t.cyanBorder}`;
                  (e.currentTarget as HTMLElement).style.outlineOffset = '2px';
                }}
                onBlur={e => {
                  (e.currentTarget as HTMLElement).style.outline = 'none';
                }}
              >
                <span
                  className="material-symbols-outlined flex-shrink-0"
                  aria-hidden="true"
                  style={{ fontSize: 16 }}
                >
                  add_circle
                </span>
                <span className="text-sm font-sans">Request a template</span>
              </div>
            </div>
          </section>
        )}

        {/* Saved workflows section */}
        {saved.length === 0 ? (
          <p className="text-xs font-sans" style={{ color: t.textFaint }}>
            No saved workflows yet — open a template and click Save.
          </p>
        ) : (
          <section>
            <h2
              className="text-xs font-sans uppercase tracking-widest mb-4"
              style={{ color: t.textFaint }}
            >
              My Workflows
            </h2>

            {filteredSaved.length > 0 ? (
              <div className="space-y-px" style={{ maxWidth: 820 }}>
                {filteredSaved.map(workflow => (
                  <SavedRow
                    key={workflow.id}
                    workflow={workflow}
                    onOpen={() => onOpen(workflow.yaml)}
                    onDelete={() => handleDeleteSaved(workflow.id)}
                  />
                ))}
              </div>
            ) : (
              <p className="text-xs font-sans" style={{ color: t.textFaint }}>
                No saved workflows match your search.
              </p>
            )}
          </section>
        )}
      </div>
    </div>
  );
};

/* ── Hero card (first / recommended template) ──────────────────────────── */

const HeroTemplateCard: React.FC<{
  template: WorkflowTemplate;
  onOpen: () => void;
}> = ({ template, onOpen }) => {
  const [hovered, setHovered] = useState(false);

  return (
    <div
      className="flex items-start justify-between gap-4 p-5 rounded-lg"
      style={{
        background: hovered ? t.bgSurface : t.bgDeep,
        border: `1px solid ${hovered ? t.cyanBorder : t.borderDefault}`,
        borderLeft: `4px solid ${t.cyan}`,
        transition: 'background 0.15s, border-color 0.15s',
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <div className="flex-1 min-w-0">
        {/* Recommended badge */}
        <div className="flex items-center gap-2 mb-2">
          <span
            className="text-body-xs font-mono font-semibold uppercase tracking-wider px-2 py-0.5 rounded"
            style={{
              background: t.amberBg,
              border: `1px solid ${t.amberBorder}`,
              color: t.amber,
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
            }}
          >
            ⭐ Recommended
          </span>
        </div>

        <div
          className="text-base font-display font-bold mb-1"
          style={{ color: t.textPrimary }}
        >
          {template.name}
        </div>

        <p
          className="text-sm font-sans leading-relaxed mb-3"
          style={{ color: t.textMuted }}
        >
          {template.description}
        </p>

        <div className="flex items-center gap-2">
          <span
            className="material-symbols-outlined"
            style={{ fontSize: 14, color: t.textFaint }}
          >
            schema
          </span>
          <span
            className="text-xs font-mono"
            style={{ color: t.textFaint }}
          >
            {template.stepCount} steps
          </span>
          <span
            className="text-xs font-mono"
            style={{ color: t.textFaint, marginLeft: 8 }}
          >
            · 94% success rate
          </span>
        </div>
      </div>

      <button
        onClick={onOpen}
        className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-sans font-medium flex-shrink-0 transition-colors"
        style={{
          background: t.cyanBg,
          border: `1px solid ${t.cyanBorder}`,
          color: t.cyan,
        }}
        onFocus={e => {
          e.currentTarget.style.outline = `2px solid ${t.cyan}`;
          e.currentTarget.style.outlineOffset = '2px';
        }}
        onBlur={e => {
          e.currentTarget.style.outline = 'none';
        }}
      >
        Open
        <span
          className="material-symbols-outlined"
          style={{ fontSize: 15 }}
        >
          arrow_forward
        </span>
      </button>
    </div>
  );
};

/* ── Compact template row ──────────────────────────────────────────────── */

const CompactTemplateRow: React.FC<{
  template: WorkflowTemplate;
  onOpen: () => void;
}> = ({ template, onOpen }) => {
  const [hovered, setHovered] = useState(false);

  return (
    <div
      className="flex items-center gap-3 px-4 py-3 rounded-lg"
      style={{
        background: hovered ? t.bgSurface : 'transparent',
        border: `1px solid ${hovered ? t.borderDefault : t.borderFaint}`,
        transition: 'background 0.12s, border-color 0.12s',
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {/* Icon */}
      <div
        className="w-8 h-8 rounded flex items-center justify-center flex-shrink-0"
        style={{
          background: t.cyanBg,
          border: `1px solid ${t.cyanBorder}`,
        }}
      >
        <span
          className="material-symbols-outlined"
          style={{ fontSize: 16, color: t.cyan }}
        >
          {template.icon}
        </span>
      </div>

      {/* Name + description */}
      <div className="flex-1 min-w-0">
        <div
          className="text-sm font-display font-semibold"
          style={{ color: t.textPrimary }}
        >
          {template.name}
        </div>
        <div
          className="text-xs font-sans mt-0.5 truncate"
          style={{ color: t.textMuted }}
        >
          {template.description}
        </div>
      </div>

      {/* Step count */}
      <span
        className="text-xs font-mono flex-shrink-0"
        style={{ color: t.textFaint }}
      >
        {template.stepCount} steps
      </span>

      {/* Open button */}
      <button
        onClick={onOpen}
        className="flex items-center gap-1 px-3 py-1.5 rounded text-xs font-sans font-medium flex-shrink-0 transition-colors"
        style={{
          background: hovered ? t.cyanBg : 'transparent',
          border: `1px solid ${hovered ? t.cyanBorder : t.borderDefault}`,
          color: hovered ? t.cyan : t.textMuted,
          transition: 'all 0.12s',
        }}
        onFocus={e => {
          e.currentTarget.style.outline = `2px solid ${t.cyan}`;
          e.currentTarget.style.outlineOffset = '2px';
        }}
        onBlur={e => {
          e.currentTarget.style.outline = 'none';
        }}
      >
        Open
        <span
          className="material-symbols-outlined"
          style={{ fontSize: 13 }}
        >
          arrow_forward
        </span>
      </button>
    </div>
  );
};

/* ── Saved workflow row ─────────────────────────────────────────────────── */

interface SavedRowProps {
  workflow: SavedWorkflow;
  onOpen: () => void;
  onDelete: () => void;
}

const SavedRow: React.FC<SavedRowProps> = ({ workflow, onOpen, onDelete }) => {
  const [hovered, setHovered] = useState(false);

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={e => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onOpen();
        }
      }}
      className="flex items-center gap-3 px-4 py-3 rounded-lg cursor-pointer"
      style={{
        background: hovered ? t.bgSurface : 'transparent',
        border: `1px solid ${hovered ? t.borderDefault : t.borderFaint}`,
        transition: 'background 0.12s, border-color 0.12s',
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onFocus={e => {
        e.currentTarget.style.outline = `2px solid ${t.cyanBorder}`;
        e.currentTarget.style.outlineOffset = '2px';
      }}
      onBlur={e => {
        e.currentTarget.style.outline = 'none';
      }}
    >
      <span
        className="material-symbols-outlined flex-shrink-0"
        style={{ fontSize: 16, color: t.textFaint }}
      >
        description
      </span>

      <div className="flex-1 min-w-0">
        <div
          className="text-sm font-display font-medium truncate"
          style={{ color: t.textPrimary }}
        >
          {workflow.name}
        </div>
        <div
          className="text-body-xs font-sans mt-0.5"
          style={{ color: t.textMuted }}
        >
          Modified {timeAgo(workflow.savedAt)}
        </div>
      </div>

      {/* Delete button — visible on hover or focus */}
      <button
        onClick={e => {
          e.stopPropagation();
          onDelete();
        }}
        className="p-1 rounded transition-opacity"
        aria-label={`Delete ${workflow.name}`}
        tabIndex={0}
        style={{
          color: t.red,
          opacity: hovered ? 1 : 0,
          transition: 'opacity 0.15s',
        }}
        onFocus={e => {
          e.currentTarget.style.opacity = '1';
          e.currentTarget.style.outline = `2px solid ${t.red}`;
          e.currentTarget.style.outlineOffset = '2px';
        }}
        onBlur={e => {
          if (!hovered) e.currentTarget.style.opacity = '0';
          e.currentTarget.style.outline = 'none';
        }}
      >
        <span className="material-symbols-outlined" style={{ fontSize: 14 }}>
          delete
        </span>
      </button>

      {/* Arrow icon — visible on hover */}
      <span
        className="material-symbols-outlined flex-shrink-0"
        aria-hidden="true"
        style={{
          fontSize: 16,
          color: t.cyan,
          opacity: hovered ? 1 : 0,
          transition: 'opacity 0.15s',
        }}
      >
        arrow_forward
      </span>
    </div>
  );
};

export default WorkflowLibraryView;
