import React, { useRef, useState, useEffect, useCallback } from 'react';
import { ParsedWorkflow, WorkflowStep } from './workflowParser';
import StepConfigSidebar from './StepConfigSidebar';
import AgentPickerModal from './AgentPickerModal';
import { t } from '../../../styles/tokens';

// ── Props ─────────────────────────────────────────────────────────────────────
interface Props {
  workflow: ParsedWorkflow;
  onAddStep: (agentId: string) => void;
  onUpdateStep: (updated: WorkflowStep) => void;
  onDeleteStep: (stepId: string) => void;
  onMoveStep: (fromIndex: number, toIndex: number) => void;
}

// ── Step dependency label ─────────────────────────────────────────────────────
function depLabel(depId: string, steps: WorkflowStep[]): string {
  const found = steps.find(s => s.id === depId);
  return found?.label || found?.id || depId;
}

// ── Human gate badge ──────────────────────────────────────────────────────────
const GateBadge: React.FC = () => (
  <span
    style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: 3,
      fontSize: 9,
      fontFamily: 'inherit',
      color: t.amber,
      background: t.amberBg,
      border: `1px solid ${t.amberBorder}`,
      borderRadius: 4,
      padding: '2px 6px',
      fontWeight: 600,
      letterSpacing: '0.04em',
      flexShrink: 0,
    }}
    title="Human approval required before this step runs"
  >
    ⏸ Gate
  </span>
);

// ── Overflow menu ─────────────────────────────────────────────────────────────
interface OverflowMenuProps {
  onDuplicate: () => void;
  onDelete: () => void;
}

const OverflowMenu: React.FC<OverflowMenuProps> = ({ onDuplicate, onDelete }) => {
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  return (
    <div
      ref={menuRef}
      style={{ position: 'relative', flexShrink: 0 }}
      onClick={e => e.stopPropagation()}
    >
      <button
        onClick={() => setOpen(v => !v)}
        aria-label="Step options"
        aria-haspopup="true"
        aria-expanded={open}
        style={{
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          color: t.textMuted,
          fontSize: 14,
          lineHeight: 1,
          padding: '2px 4px',
          borderRadius: 3,
          fontFamily: 'inherit',
          letterSpacing: '0.1em',
          transition: 'color 0.12s',
        }}
        onMouseEnter={e => { e.currentTarget.style.color = t.textPrimary; }}
        onMouseLeave={e => { e.currentTarget.style.color = t.textMuted; }}
        onFocus={e => { e.currentTarget.style.outline = `2px solid ${t.cyanBorder}`; }}
        onBlur={e => { e.currentTarget.style.outline = 'none'; }}
      >
        ···
      </button>

      {open && (
        <div
          style={{
            position: 'absolute',
            top: 'calc(100% + 4px)',
            right: 0,
            zIndex: 40,
            background: t.bgSurface,
            border: `1px solid ${t.borderDefault}`,
            borderRadius: 6,
            minWidth: 130,
            boxShadow: t.shadowModal,
            overflow: 'hidden',
          }}
          role="menu"
        >
          <button
            role="menuitem"
            onClick={() => { onDuplicate(); setOpen(false); }}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              width: '100%',
              textAlign: 'left',
              padding: '8px 12px',
              fontSize: 11,
              fontFamily: 'inherit',
              color: t.textPrimary,
              background: 'none',
              border: 'none',
              borderBottom: `1px solid ${t.borderFaint}`,
              cursor: 'pointer',
              transition: 'background 0.1s',
            }}
            onMouseEnter={e => { e.currentTarget.style.background = t.cyanHover; }}
            onMouseLeave={e => { e.currentTarget.style.background = 'none'; }}
            onFocus={e => { e.currentTarget.style.background = t.cyanHover; }}
            onBlur={e => { e.currentTarget.style.background = 'none'; }}
          >
            <span className="material-symbols-outlined" style={{ fontSize: 13 }}>content_copy</span>
            Duplicate
          </button>
          <button
            role="menuitem"
            onClick={() => { onDelete(); setOpen(false); }}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              width: '100%',
              textAlign: 'left',
              padding: '8px 12px',
              fontSize: 11,
              fontFamily: 'inherit',
              color: t.red,
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              transition: 'background 0.1s',
            }}
            onMouseEnter={e => { e.currentTarget.style.background = t.redBg; }}
            onMouseLeave={e => { e.currentTarget.style.background = 'none'; }}
            onFocus={e => { e.currentTarget.style.background = t.redBg; }}
            onBlur={e => { e.currentTarget.style.background = 'none'; }}
          >
            <span className="material-symbols-outlined" style={{ fontSize: 13 }}>delete</span>
            Delete
          </button>
        </div>
      )}
    </div>
  );
};

// ── Drop indicator line ───────────────────────────────────────────────────────
const DropIndicator: React.FC = () => (
  <div
    style={{
      height: 2,
      margin: '0 12px',
      borderRadius: 1,
      background: t.cyan,
      opacity: 0.8,
      boxShadow: `0 0 6px ${t.cyan}`,
      pointerEvents: 'none',
    }}
    aria-hidden="true"
  />
);

// ── Step card ─────────────────────────────────────────────────────────────────
interface StepCardProps {
  step: WorkflowStep;
  index: number;
  allSteps: WorkflowStep[];
  isSelected: boolean;
  isDragging: boolean;
  dragOverIndex: number | null;
  onSelect: () => void;
  onDuplicate: () => void;
  onDelete: () => void;
  onDragStart: (index: number) => void;
  onDragOver: (e: React.DragEvent, index: number) => void;
  onDrop: (e: React.DragEvent, index: number) => void;
  onDragEnd: () => void;
}

const StepCard: React.FC<StepCardProps> = ({
  step,
  index,
  allSteps,
  isSelected,
  isDragging,
  dragOverIndex,
  onSelect,
  onDuplicate,
  onDelete,
  onDragStart,
  onDragOver,
  onDrop,
  onDragEnd,
}) => {
  const [hovered, setHovered] = useState(false);

  const depLabels = step.depends_on
    .map(id => depLabel(id, allSteps))
    .filter(Boolean);

  const showDropAbove = dragOverIndex === index;

  return (
    <>
      {showDropAbove && <DropIndicator />}
      <div
        draggable
        onDragStart={() => onDragStart(index)}
        onDragOver={e => onDragOver(e, index)}
        onDrop={e => onDrop(e, index)}
        onDragEnd={onDragEnd}
        onClick={onSelect}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        role="button"
        tabIndex={0}
        aria-pressed={isSelected}
        onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(); } }}
        style={{
          position: 'relative',
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          padding: '10px 14px',
          borderRadius: 6,
          cursor: 'pointer',
          border: `1px solid ${isSelected ? t.cyanBorder : t.borderSubtle}`,
          borderLeft: `3px solid ${isSelected ? t.cyan : 'transparent'}`,
          background: isSelected
            ? t.cyanSelected
            : hovered
            ? t.cyanHover
            : t.bgSurface,
          opacity: isDragging ? 0.4 : 1,
          transition: 'background 0.12s, border-color 0.12s, opacity 0.12s',
          userSelect: 'none',
          outline: 'none',
        }}
        onFocus={e => {
          e.currentTarget.style.boxShadow = `0 0 0 2px ${t.cyanBorder}`;
        }}
        onBlur={e => {
          e.currentTarget.style.boxShadow = 'none';
        }}
      >
        {/* Drag handle */}
        <span
          title="Drag to reorder"
          aria-hidden="true"
          style={{
            flexShrink: 0,
            fontSize: 14,
            color: hovered ? t.textMuted : t.textFaint,
            cursor: 'grab',
            lineHeight: 1,
            transition: 'color 0.12s',
            userSelect: 'none',
          }}
        >
          ⠿
        </span>

        {/* Step number */}
        <span
          style={{
            flexShrink: 0,
            width: 20,
            height: 20,
            borderRadius: '50%',
            background: isSelected ? t.cyanBg : t.bgTrack,
            border: `1px solid ${isSelected ? t.cyanBorder : t.borderDefault}`,
            color: isSelected ? t.cyan : t.textMuted,
            fontSize: 10,
            fontFamily: 'monospace',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontWeight: 600,
            lineHeight: 1,
          }}
          aria-label={`Step ${index + 1}`}
        >
          {index + 1}
        </span>

        {/* Agent icon placeholder */}
        <span
          aria-hidden="true"
          className="material-symbols-outlined"
          style={{
            flexShrink: 0,
            fontSize: 16,
            color: isSelected ? t.cyan : t.textMuted,
            transition: 'color 0.12s',
          }}
        >
          radio_button_checked
        </span>

        {/* Labels area */}
        <div style={{ flex: 1, minWidth: 0 }}>
          {/* Human label */}
          <div
            style={{
              fontSize: 13,
              fontFamily: 'var(--font-display, inherit)',
              fontWeight: 600,
              color: t.textPrimary,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              lineHeight: 1.3,
            }}
          >
            {step.label || step.id}
          </div>

          {/* Agent ID + dependency summary row */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              marginTop: 2,
              flexWrap: 'wrap',
            }}
          >
            <span
              style={{
                fontSize: 10,
                fontFamily: 'monospace',
                color: t.textMuted,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {step.agent || <span style={{ color: t.textFaint }}>no agent</span>}
            </span>

            {depLabels.length > 0 && (
              <span
                style={{
                  fontSize: 10,
                  fontFamily: 'inherit',
                  color: t.textFaint,
                  whiteSpace: 'nowrap',
                }}
              >
                After: {depLabels.join(', ')}
              </span>
            )}

            {depLabels.length === 0 && index === 0 && (
              <span
                style={{
                  fontSize: 10,
                  fontFamily: 'inherit',
                  color: t.textFaint,
                  whiteSpace: 'nowrap',
                }}
              >
                First step
              </span>
            )}
          </div>
        </div>

        {/* Gate badge */}
        {step.human_gate && <GateBadge />}

        {/* Overflow menu */}
        <OverflowMenu
          onDuplicate={onDuplicate}
          onDelete={onDelete}
        />

        {/* Chevron */}
        <span
          className="material-symbols-outlined"
          aria-hidden="true"
          style={{
            flexShrink: 0,
            fontSize: 16,
            color: isSelected ? t.cyan : hovered ? t.textSecondary : t.textFaint,
            transition: 'color 0.12s, opacity 0.12s',
            opacity: isSelected || hovered ? 1 : 0.4,
          }}
        >
          chevron_right
        </span>
      </div>
    </>
  );
};

// ── Add Step button ───────────────────────────────────────────────────────────
interface AddStepButtonProps {
  onClick: () => void;
}

const AddStepButton: React.FC<AddStepButtonProps> = ({ onClick }) => {
  const [hovered, setHovered] = useState(false);

  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      aria-label="Add step"
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 6,
        width: '100%',
        padding: '10px 14px',
        borderRadius: 6,
        border: `1px dashed ${hovered ? t.cyanBorder : t.borderDefault}`,
        background: hovered ? t.cyanHover : 'none',
        color: hovered ? t.cyan : t.textMuted,
        fontSize: 12,
        fontFamily: 'inherit',
        cursor: 'pointer',
        transition: 'background 0.12s, border-color 0.12s, color 0.12s',
      }}
      onFocus={e => {
        e.currentTarget.style.outline = `2px solid ${t.cyanBorder}`;
        e.currentTarget.style.outlineOffset = '2px';
      }}
      onBlur={e => {
        e.currentTarget.style.outline = 'none';
      }}
    >
      <span className="material-symbols-outlined" style={{ fontSize: 15 }}>add</span>
      Add Step
    </button>
  );
};

// ── Empty state ───────────────────────────────────────────────────────────────
interface EmptyStateProps {
  onAddStep: () => void;
}

const EmptyState: React.FC<EmptyStateProps> = ({ onAddStep }) => (
  <div
    style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 16,
      flex: 1,
      padding: 40,
      textAlign: 'center',
    }}
  >
    <span
      className="material-symbols-outlined"
      style={{ fontSize: 40, color: t.textFaint }}
    >
      list_alt
    </span>
    <div>
      <div
        style={{
          fontSize: 14,
          fontFamily: 'var(--font-display, inherit)',
          fontWeight: 600,
          color: t.textSecondary,
          marginBottom: 6,
        }}
      >
        No steps yet
      </div>
      <div
        style={{
          fontSize: 12,
          fontFamily: 'inherit',
          color: t.textFaint,
          maxWidth: 260,
          lineHeight: 1.5,
        }}
      >
        Add your first step to get started.
      </div>
    </div>
    <button
      onClick={onAddStep}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        padding: '8px 18px',
        borderRadius: 6,
        border: `1px solid ${t.cyanBorder}`,
        background: t.cyanBg,
        color: t.cyan,
        fontSize: 12,
        fontFamily: 'inherit',
        cursor: 'pointer',
        fontWeight: 600,
      }}
      onFocus={e => {
        e.currentTarget.style.outline = `2px solid ${t.cyanBorder}`;
        e.currentTarget.style.outlineOffset = '2px';
      }}
      onBlur={e => {
        e.currentTarget.style.outline = 'none';
      }}
    >
      <span className="material-symbols-outlined" style={{ fontSize: 15 }}>add</span>
      Add Step
    </button>
  </div>
);

// ── Main component ─────────────────────────────────────────────────────────────
const WorkflowList: React.FC<Props> = ({
  workflow,
  onAddStep,
  onUpdateStep,
  onDeleteStep,
  onMoveStep,
}) => {
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  // Whether the picker was opened from the sidebar (to change agent) vs. adding a new step
  const [pickerForSidebar, setPickerForSidebar] = useState(false);

  // Drag state
  const dragFromIndex = useRef<number | null>(null);
  const [draggingIndex, setDraggingIndex] = useState<number | null>(null);
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null);

  // Reset selected step if it gets deleted from workflow
  useEffect(() => {
    if (selectedStepId && !workflow.steps.find(s => s.id === selectedStepId)) {
      setSelectedStepId(null);
    }
  }, [workflow.steps, selectedStepId]);

  // Cleanup drag state on unmount
  useEffect(() => {
    return () => {
      setDraggingIndex(null);
      setDragOverIndex(null);
    };
  }, []);

  // ── Drag handlers ─────────────────────────────────────────────────────────
  const handleDragStart = useCallback((index: number) => {
    dragFromIndex.current = index;
    setDraggingIndex(index);
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent, index: number) => {
    e.preventDefault();
    setDragOverIndex(index);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent, toIndex: number) => {
    e.preventDefault();
    const fromIndex = dragFromIndex.current;
    if (fromIndex !== null && fromIndex !== toIndex) {
      onMoveStep(fromIndex, toIndex);
    }
    dragFromIndex.current = null;
    setDraggingIndex(null);
    setDragOverIndex(null);
  }, [onMoveStep]);

  const handleDragEnd = useCallback(() => {
    dragFromIndex.current = null;
    setDraggingIndex(null);
    setDragOverIndex(null);
  }, []);

  // Handle drop on the container for the "after last item" case
  const handleContainerDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    const fromIndex = dragFromIndex.current;
    const toIndex = workflow.steps.length - 1;
    if (fromIndex !== null && fromIndex !== toIndex && toIndex < workflow.steps.length) {
      onMoveStep(fromIndex, toIndex);
    }
    dragFromIndex.current = null;
    setDraggingIndex(null);
    setDragOverIndex(null);
  }, [workflow.steps, onMoveStep]);

  // ── Duplicate step ────────────────────────────────────────────────────────
  const handleDuplicate = useCallback((step: WorkflowStep) => {
    const baseId = step.id.replace(/_copy\d*$/, '');
    const existingIds = new Set(workflow.steps.map(s => s.id));
    let newId = `${baseId}_copy`;
    let counter = 1;
    while (existingIds.has(newId)) {
      newId = `${baseId}_copy${counter++}`;
    }
    const duplicated: WorkflowStep = {
      ...step,
      id: newId,
      label: step.label ? `${step.label} (copy)` : undefined,
      depends_on: [...step.depends_on],
    };
    onUpdateStep(duplicated);
  }, [workflow.steps, onUpdateStep]);

  // ── Picker select ─────────────────────────────────────────────────────────
  const handlePickerSelect = useCallback((agentId: string) => {
    if (pickerForSidebar && selectedStepId) {
      const step = workflow.steps.find(s => s.id === selectedStepId);
      if (step) {
        onUpdateStep({ ...step, agent: agentId });
      }
    } else {
      onAddStep(agentId);
    }
    setPickerOpen(false);
    setPickerForSidebar(false);
  }, [pickerForSidebar, selectedStepId, workflow.steps, onUpdateStep, onAddStep]);

  const selectedStep = selectedStepId
    ? workflow.steps.find(s => s.id === selectedStepId) ?? null
    : null;

  return (
    <div
      style={{
        display: 'flex',
        height: '100%',
        overflow: 'hidden',
        background: t.bgBase,
      }}
    >
      {/* ── Step list area ─────────────────────────────────────────────────── */}
      <div
        style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          minWidth: 0,
        }}
      >
        {workflow.steps.length === 0 ? (
          <EmptyState onAddStep={() => setPickerOpen(true)} />
        ) : (
          <>
            {/* Scrollable list */}
            <div
              style={{
                flex: 1,
                overflowY: 'auto',
                padding: '12px 16px',
                display: 'flex',
                flexDirection: 'column',
                gap: 6,
              }}
              // Handle drop on the container for the "after last item" case
              onDragOver={e => {
                e.preventDefault();
                // If dragging over the empty area below all cards, set to end
                setDragOverIndex(workflow.steps.length);
              }}
              onDrop={handleContainerDrop}
            >
              {workflow.steps.map((step, index) => (
                <StepCard
                  key={step.id}
                  step={step}
                  index={index}
                  allSteps={workflow.steps}
                  isSelected={selectedStepId === step.id}
                  isDragging={draggingIndex === index}
                  dragOverIndex={dragOverIndex}
                  onSelect={() =>
                    setSelectedStepId(prev => (prev === step.id ? null : step.id))
                  }
                  onDuplicate={() => handleDuplicate(step)}
                  onDelete={() => {
                    onDeleteStep(step.id);
                    if (selectedStepId === step.id) setSelectedStepId(null);
                  }}
                  onDragStart={handleDragStart}
                  onDragOver={handleDragOver}
                  onDrop={handleDrop}
                  onDragEnd={handleDragEnd}
                />
              ))}

              {/* Drop indicator after the last item */}
              {dragOverIndex === workflow.steps.length && <DropIndicator />}
            </div>

            {/* Add Step button footer */}
            <div
              style={{
                padding: '10px 16px 14px',
                flexShrink: 0,
                borderTop: `1px solid ${t.borderSubtle}`,
              }}
            >
              <AddStepButton onClick={() => setPickerOpen(true)} />
            </div>
          </>
        )}
      </div>

      {/* ── Right sidebar ──────────────────────────────────────────────────── */}
      {selectedStep && (
        <StepConfigSidebar
          step={selectedStep}
          allSteps={workflow.steps}
          onUpdate={onUpdateStep}
          onDelete={stepId => {
            onDeleteStep(stepId);
            setSelectedStepId(null);
          }}
          onClose={() => setSelectedStepId(null)}
          onOpenAgentPicker={() => {
            setPickerForSidebar(true);
            setPickerOpen(true);
          }}
        />
      )}

      {/* ── Agent picker modal ─────────────────────────────────────────────── */}
      {pickerOpen && (
        <AgentPickerModal
          onSelect={handlePickerSelect}
          onClose={() => {
            setPickerOpen(false);
            setPickerForSidebar(false);
          }}
        />
      )}
    </div>
  );
};

export default WorkflowList;
