import React, { useState, useCallback, useRef, useEffect } from 'react';
import { APP_DIAGNOSTICS_TEMPLATE } from './workflowParser';
import { useWorkflowState } from './useWorkflowState';
import WorkflowCanvas from './WorkflowCanvas';
import WorkflowList from './WorkflowList';
import WorkflowCodeView from './WorkflowCodeView';
import WorkflowLibraryView from './WorkflowLibraryView';
import { t } from '../../../styles/tokens';
import type { WorkflowStep } from './workflowParser';

// ── Constants ─────────────────────────────────────────────────────────────────

const LS_KEY = 'platform_workflow_builder_yaml';

const BLANK_TEMPLATE = `id: new_workflow
name: New Workflow
version: "1.0"
trigger: [api]

steps:
  - id: step_1
    agent: log_analysis_agent
    depends_on: []
`;

// ── Types ─────────────────────────────────────────────────────────────────────

type Mode = 'library' | 'editor';
type View = 'canvas' | 'list' | 'code';

// ── View switcher tab labels ───────────────────────────────────────────────────

const VIEW_TABS: { id: View; label: string; icon: string }[] = [
  { id: 'canvas', label: 'Canvas', icon: 'account_tree' },
  { id: 'list',   label: 'List',   icon: 'list_alt' },
  { id: 'code',   label: 'Code',   icon: 'code' },
];

// ── Main component ─────────────────────────────────────────────────────────────

const WorkflowBuilderView: React.FC = () => {
  const [mode, setMode] = useState<Mode>('library');
  const [view, setView] = useState<View>('canvas');
  const [editingName, setEditingName] = useState(false);
  const [savedFlash, setSavedFlash] = useState(false);
  const [backHovered, setBackHovered] = useState(false);
  const savedTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const nameInputRef = useRef<HTMLInputElement>(null);

  // ── Workflow state ───────────────────────────────────────────────────────────
  const [initialYaml] = useState<string>(
    () => localStorage.getItem(LS_KEY) || APP_DIAGNOSTICS_TEMPLATE,
  );
  const {
    yaml,
    parsed,
    dirty,
    setYaml,
    updateWorkflowMeta,
    addStep,
    updateStep,
    removeStep,
    moveStep,
    save,
  } = useWorkflowState(initialYaml);

  // Clean up saved flash timer on unmount
  useEffect(() => {
    return () => {
      if (savedTimerRef.current) clearTimeout(savedTimerRef.current);
    };
  }, []);

  // Focus name input when editing starts
  useEffect(() => {
    if (editingName && nameInputRef.current) {
      nameInputRef.current.focus();
      nameInputRef.current.select();
    }
  }, [editingName]);

  // ── Adapter: child components pass the full WorkflowStep object ───────────────
  // useWorkflowState.updateStep takes (stepId, fields), so we bridge here.
  const handleUpdateStep = useCallback(
    (updated: WorkflowStep) => {
      updateStep(updated.id, updated);
    },
    [updateStep],
  );

  // ── Navigation ───────────────────────────────────────────────────────────────

  const openWorkflow = useCallback(
    (workflowYaml: string) => {
      setYaml(workflowYaml);
      localStorage.setItem(LS_KEY, workflowYaml);
      setMode('editor');
    },
    [setYaml],
  );

  const openNewWorkflow = useCallback(() => {
    openWorkflow(BLANK_TEMPLATE);
  }, [openWorkflow]);

  // ── Save ─────────────────────────────────────────────────────────────────────

  const handleSave = useCallback(() => {
    save();
    setSavedFlash(true);
    if (savedTimerRef.current) clearTimeout(savedTimerRef.current);
    savedTimerRef.current = setTimeout(() => setSavedFlash(false), 2000);
  }, [save]);

  // ── Run ──────────────────────────────────────────────────────────────────────

  const handleRun = useCallback(() => {
    // eslint-disable-next-line no-console
    console.log('Run workflow', parsed.id);
  }, [parsed.id]);

  // ── Inline name editing ───────────────────────────────────────────────────────

  const handleNameBlur = useCallback(
    (e: React.FocusEvent<HTMLInputElement>) => {
      const newName = e.currentTarget.value.trim();
      if (newName) {
        updateWorkflowMeta({ name: newName });
      }
      setEditingName(false);
    },
    [updateWorkflowMeta],
  );

  const handleNameKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === 'Enter') {
        e.currentTarget.blur();
      } else if (e.key === 'Escape') {
        setEditingName(false);
      }
    },
    [],
  );

  // ── Library mode ─────────────────────────────────────────────────────────────

  if (mode === 'library') {
    return (
      <WorkflowLibraryView
        onOpen={openWorkflow}
        onNew={openNewWorkflow}
      />
    );
  }

  // ── Editor mode ──────────────────────────────────────────────────────────────

  const hasErrors = (parsed.errors ?? []).length > 0;

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        background: t.bgBase,
      }}
    >
      {/* ── Toolbar ────────────────────────────────────────────────────────── */}
      <div
        style={{
          height: 52,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0 16px',
          flexShrink: 0,
          background: t.bgSurface,
          borderBottom: `1px solid ${t.borderDefault}`,
          gap: 12,
        }}
      >
        {/* ── Left: back button + workflow name ──────────────────────────── */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            flex: 1,
            minWidth: 0,
          }}
        >
          {/* Back button */}
          <button
            onClick={() => setMode('library')}
            onMouseEnter={() => setBackHovered(true)}
            onMouseLeave={() => setBackHovered(false)}
            aria-label="Back to workflows library"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 4,
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              color: backHovered ? t.textPrimary : t.textMuted,
              fontSize: 12,
              fontFamily: 'inherit',
              padding: '4px 6px',
              borderRadius: 4,
              flexShrink: 0,
              transition: 'color 0.12s',
              whiteSpace: 'nowrap',
            }}
            onFocus={e => {
              e.currentTarget.style.outline = `2px solid ${t.cyanBorder}`;
              e.currentTarget.style.outlineOffset = '2px';
            }}
            onBlur={e => {
              e.currentTarget.style.outline = 'none';
            }}
          >
            <span
              className="material-symbols-outlined"
              style={{ fontSize: 14 }}
            >
              arrow_back
            </span>
            Workflows
          </button>

          {/* Separator */}
          <span
            aria-hidden="true"
            style={{ color: t.borderDefault, fontSize: 14, flexShrink: 0 }}
          >
            /
          </span>

          {/* Workflow name area */}
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'center',
              minWidth: 0,
            }}
          >
            {editingName ? (
              <input
                ref={nameInputRef}
                defaultValue={parsed.name || 'Untitled Workflow'}
                onBlur={handleNameBlur}
                onKeyDown={handleNameKeyDown}
                aria-label="Workflow name"
                style={{
                  fontSize: 14,
                  fontFamily: 'inherit',
                  fontWeight: 600,
                  color: t.textPrimary,
                  background: t.bgDeep,
                  border: `1px solid ${t.cyanBorder}`,
                  borderRadius: 4,
                  padding: '2px 6px',
                  outline: 'none',
                  minWidth: 120,
                  maxWidth: 260,
                }}
              />
            ) : (
              <button
                onClick={() => setEditingName(true)}
                aria-label="Edit workflow name"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 5,
                  background: 'none',
                  border: 'none',
                  cursor: 'text',
                  padding: '2px 0',
                }}
                onFocus={e => {
                  e.currentTarget.style.outline = `2px solid ${t.cyanBorder}`;
                  e.currentTarget.style.outlineOffset = '2px';
                  e.currentTarget.style.borderRadius = '4px';
                }}
                onBlur={e => {
                  e.currentTarget.style.outline = 'none';
                }}
              >
                <span
                  style={{
                    fontSize: 14,
                    fontFamily: 'inherit',
                    fontWeight: 600,
                    color: t.textPrimary,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                    maxWidth: 240,
                  }}
                >
                  {parsed.name || 'Untitled Workflow'}
                </span>
                <span
                  className="material-symbols-outlined"
                  aria-hidden="true"
                  style={{ fontSize: 13, color: t.textMuted }}
                >
                  edit
                </span>
              </button>
            )}

            {/* Workflow ID — mono, muted, small */}
            {parsed.id && (
              <span
                style={{
                  fontSize: 10,
                  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
                  color: t.textMuted,
                  lineHeight: 1,
                  marginTop: 1,
                }}
              >
                {parsed.id}
              </span>
            )}
          </div>
        </div>

        {/* ── Center: view switcher ──────────────────────────────────────── */}
        <div
          role="tablist"
          aria-label="Editor view"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 0,
            flexShrink: 0,
          }}
        >
          {VIEW_TABS.map(tab => {
            const isActive = view === tab.id;
            return (
              <button
                key={tab.id}
                role="tab"
                aria-selected={isActive}
                onClick={() => setView(tab.id)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 5,
                  padding: '6px 14px',
                  fontSize: 13,
                  fontFamily: 'inherit',
                  background: 'none',
                  border: 'none',
                  borderBottom: isActive
                    ? `2px solid ${t.cyan}`
                    : '2px solid transparent',
                  color: isActive ? t.textPrimary : t.textMuted,
                  cursor: 'pointer',
                  transition: 'color 0.12s, border-color 0.12s',
                  fontWeight: isActive ? 600 : 400,
                  height: 52,
                  borderRadius: 0,
                  marginBottom: -1, // overlap the toolbar border-bottom
                }}
                onMouseEnter={e => {
                  if (!isActive) {
                    e.currentTarget.style.color = t.textSecondary;
                  }
                }}
                onMouseLeave={e => {
                  if (!isActive) {
                    e.currentTarget.style.color = t.textMuted;
                  }
                }}
                onFocus={e => {
                  e.currentTarget.style.outline = `2px solid ${t.cyanBorder}`;
                  e.currentTarget.style.outlineOffset = '-2px';
                }}
                onBlur={e => {
                  e.currentTarget.style.outline = 'none';
                }}
              >
                {tab.label}
              </button>
            );
          })}
        </div>

        {/* ── Right: status + save + run ─────────────────────────────────── */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            flex: 1,
            justifyContent: 'flex-end',
            minWidth: 0,
          }}
        >
          {/* Status badge */}
          {hasErrors ? (
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 4,
                fontSize: 11,
                fontFamily: 'inherit',
                padding: '3px 8px',
                borderRadius: 4,
                background: t.redBg,
                border: `1px solid ${t.redBorder}`,
                color: t.red,
                flexShrink: 0,
                whiteSpace: 'nowrap',
              }}
            >
              <span
                className="material-symbols-outlined"
                aria-hidden="true"
                style={{ fontSize: 12 }}
              >
                warning
              </span>
              {(parsed.errors ?? []).length} error{(parsed.errors ?? []).length !== 1 ? 's' : ''}
            </span>
          ) : (
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 4,
                fontSize: 11,
                fontFamily: 'inherit',
                padding: '3px 8px',
                borderRadius: 4,
                background: t.greenBg,
                border: `1px solid ${t.greenBorder}`,
                color: t.green,
                flexShrink: 0,
                whiteSpace: 'nowrap',
              }}
            >
              ● Valid
            </span>
          )}

          {/* Save button */}
          <button
            onClick={handleSave}
            aria-label="Save workflow"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 5,
              padding: '5px 12px',
              fontSize: 12,
              fontFamily: 'inherit',
              fontWeight: 500,
              background: 'transparent',
              border: `1px solid ${savedFlash ? t.greenBorder : t.borderDefault}`,
              borderRadius: 5,
              color: savedFlash ? t.green : t.textSecondary,
              cursor: 'pointer',
              transition: 'color 0.15s, border-color 0.15s',
              flexShrink: 0,
              whiteSpace: 'nowrap',
            }}
            onMouseEnter={e => {
              if (!savedFlash) {
                e.currentTarget.style.color = t.textPrimary;
                e.currentTarget.style.borderColor = t.borderDefault;
              }
            }}
            onMouseLeave={e => {
              if (!savedFlash) {
                e.currentTarget.style.color = t.textSecondary;
                e.currentTarget.style.borderColor = t.borderDefault;
              }
            }}
            onFocus={e => {
              e.currentTarget.style.outline = `2px solid ${t.cyanBorder}`;
              e.currentTarget.style.outlineOffset = '2px';
            }}
            onBlur={e => {
              e.currentTarget.style.outline = 'none';
            }}
          >
            <span
              className="material-symbols-outlined"
              aria-hidden="true"
              style={{ fontSize: 13 }}
            >
              {savedFlash ? 'check' : 'save'}
            </span>
            {savedFlash ? 'Saved ✓' : 'Save'}
            {dirty && !savedFlash && (
              <span
                title="Unsaved changes"
                aria-label="Unsaved changes"
                style={{
                  display: 'inline-block',
                  width: 5,
                  height: 5,
                  borderRadius: '50%',
                  background: t.amber,
                  flexShrink: 0,
                }}
              />
            )}
          </button>

          {/* Run button — primary CTA */}
          <button
            onClick={handleRun}
            aria-label="Run workflow"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 5,
              padding: '5px 14px',
              fontSize: 13,
              fontFamily: 'inherit',
              fontWeight: 600,
              background: t.cyan,
              border: `1px solid ${t.cyan}`,
              borderRadius: 5,
              color: t.textOnAccent,
              cursor: 'pointer',
              flexShrink: 0,
              whiteSpace: 'nowrap',
              transition: 'opacity 0.12s',
            }}
            onMouseEnter={e => {
              e.currentTarget.style.opacity = '0.88';
            }}
            onMouseLeave={e => {
              e.currentTarget.style.opacity = '1';
            }}
            onFocus={e => {
              e.currentTarget.style.outline = `2px solid ${t.cyan}`;
              e.currentTarget.style.outlineOffset = '2px';
            }}
            onBlur={e => {
              e.currentTarget.style.outline = 'none';
            }}
          >
            <span
              className="material-symbols-outlined"
              aria-hidden="true"
              style={{ fontSize: 14 }}
            >
              play_arrow
            </span>
            Run
          </button>
        </div>
      </div>

      {/* ── Editor panel ───────────────────────────────────────────────────── */}
      <div style={{ flex: 1, overflow: 'hidden', minHeight: 0 }}>
        {view === 'canvas' && (
          <>
            {/* onMoveStep not applicable for canvas — reordering is done via drag in List view */}
            <WorkflowCanvas
              workflow={parsed}
              onAddStep={addStep}
              onUpdateStep={handleUpdateStep}
              onDeleteStep={removeStep}
            />
          </>
        )}

        {view === 'list' && (
          <WorkflowList
            workflow={parsed}
            onAddStep={addStep}
            onUpdateStep={handleUpdateStep}
            onDeleteStep={removeStep}
            onMoveStep={moveStep}
          />
        )}

        {view === 'code' && (
          <div
            style={{
              height: '100%',
              padding: 16,
              display: 'flex',
              flexDirection: 'column',
              minHeight: 0,
            }}
          >
            <WorkflowCodeView
              yaml={yaml}
              parsed={parsed}
              dirty={dirty}
              onChange={setYaml}
            />
          </div>
        )}
      </div>
    </div>
  );
};

export default WorkflowBuilderView;
