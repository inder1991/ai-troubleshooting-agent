import React, { useState, useCallback, useEffect } from 'react';
import ReactFlow, {
  Node,
  Edge,
  Background,
  Controls,
  useNodesState,
  useEdgesState,
  BackgroundVariant,
  NodeProps,
  Handle,
  Position,
  MarkerType,
} from 'reactflow';
import 'reactflow/dist/style.css';

import { t } from '../../../styles/tokens';
import type { ParsedWorkflow, WorkflowStep } from './workflowParser';
import AgentPickerModal from './AgentPickerModal';
import StepConfigSidebar from './StepConfigSidebar';

// ── Props ────────────────────────────────────────────────────────────────────

interface Props {
  workflow: ParsedWorkflow;
  onAddStep: (agentId: string) => void;
  onUpdateStep: (updated: WorkflowStep) => void;
  onDeleteStep: (stepId: string) => void;
}

// ── WorkflowNode data shape ───────────────────────────────────────────────────

interface WorkflowNodeData {
  step: WorkflowStep;
  selected: boolean;
}

// ── Custom node renderer ──────────────────────────────────────────────────────

const WorkflowNode: React.FC<NodeProps<WorkflowNodeData>> = ({ data, selected }) => {
  const { step } = data;
  const isHumanGate = !!step.human_gate;

  return (
    <div
      style={{
        minWidth: 180,
        padding: '12px 14px',
        background: t.bgSurface,
        border: selected
          ? `2px solid ${t.cyan}`
          : isHumanGate
          ? `1px solid ${t.borderDefault}`
          : `1px solid ${t.borderDefault}`,
        borderLeft: isHumanGate ? `3px solid ${t.amber}` : undefined,
        borderRadius: 8,
        boxShadow: selected
          ? `0 0 0 2px ${t.cyanBorder}, 0 4px 16px rgba(0,0,0,0.4)`
          : '0 2px 8px rgba(0,0,0,0.3)',
        cursor: 'pointer',
        transition: 'border-color 0.12s, box-shadow 0.12s',
        position: 'relative',
      }}
    >
      {/* Top handle (target) */}
      <Handle
        type="target"
        position={Position.Top}
        style={{ background: t.cyanBorder, width: 8, height: 8, border: 'none' }}
      />

      {/* Step label / id */}
      <div
        style={{
          fontSize: 13,
          fontFamily: 'var(--font-display, inherit)',
          fontWeight: 600,
          color: t.textPrimary,
          marginBottom: 4,
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          maxWidth: 200,
        }}
      >
        {step.label || step.id}
      </div>

      {/* Agent ID */}
      <div
        style={{
          fontSize: 10,
          fontFamily: 'monospace',
          color: t.textMuted,
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          maxWidth: 200,
        }}
      >
        {step.agent || <span style={{ color: t.textFaint }}>no agent</span>}
      </div>

      {/* Placeholder status */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 5,
          marginTop: 8,
        }}
      >
        <span
          style={{
            width: 6,
            height: 6,
            borderRadius: '50%',
            background: t.textFaint,
            flexShrink: 0,
            display: 'inline-block',
          }}
        />
        <span style={{ fontSize: 9, fontFamily: 'inherit', color: t.textFaint }}>
          idle
        </span>
      </div>

      {/* Human gate badge */}
      {isHumanGate && (
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 3,
            marginTop: 6,
            fontSize: 9,
            fontFamily: 'inherit',
            color: t.amber,
            background: t.amberBg,
            border: `1px solid ${t.amberBorder}`,
            borderRadius: 4,
            padding: '2px 6px',
          }}
        >
          ⏸ Gate
        </div>
      )}

      {/* Bottom handle (source) */}
      <Handle
        type="source"
        position={Position.Bottom}
        style={{ background: t.cyanBorder, width: 8, height: 8, border: 'none' }}
      />
    </div>
  );
};

// ── Memoized node types (defined outside component to avoid re-registration) ──

const nodeTypes = { workflowNode: WorkflowNode };

// ── Convert ParsedWorkflow → ReactFlow nodes/edges ───────────────────────────

function workflowToFlow(workflow: ParsedWorkflow): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = workflow.steps.map((step, index) => ({
    id: step.id,
    type: 'workflowNode',
    position: { x: 0, y: index * 120 },
    data: { step, selected: false } as WorkflowNodeData,
    draggable: true,
  }));

  const edges: Edge[] = [];
  workflow.steps.forEach(step => {
    step.depends_on.forEach(depId => {
      edges.push({
        id: `${depId}->${step.id}`,
        source: depId,
        target: step.id,
        type: 'smoothstep',
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: 'rgba(7,182,213,0.3)',
        },
        style: { stroke: 'rgba(7,182,213,0.3)', strokeWidth: 1.5 },
      });
    });
  });

  return { nodes, edges };
}

// ── Simple vertical auto-layout (no dagre) ────────────────────────────────────

function computeAutoLayout(
  steps: WorkflowStep[],
): Record<string, { x: number; y: number }> {
  // Topological sort using Kahn's algorithm, then assign rows
  const inDegree: Record<string, number> = {};
  const adjList: Record<string, string[]> = {};

  steps.forEach(s => {
    inDegree[s.id] = 0;
    adjList[s.id] = [];
  });

  steps.forEach(s => {
    s.depends_on.forEach(dep => {
      if (adjList[dep]) {
        adjList[dep].push(s.id);
        inDegree[s.id] = (inDegree[s.id] || 0) + 1;
      }
    });
  });

  const queue: string[] = steps.filter(s => inDegree[s.id] === 0).map(s => s.id);
  const levels: Record<string, number> = {};
  const colCount: Record<number, number> = {};

  while (queue.length > 0) {
    const id = queue.shift()!;
    const level = levels[id] ?? 0;
    const col = colCount[level] ?? 0;
    colCount[level] = col + 1;

    adjList[id].forEach(nextId => {
      levels[nextId] = Math.max(levels[nextId] ?? 0, level + 1);
      inDegree[nextId]--;
      if (inDegree[nextId] === 0) queue.push(nextId);
    });
  }

  // Now assign positions: row per level, column within level
  const positions: Record<string, { x: number; y: number }> = {};

  // Group steps by level
  const stepsByLevel: Record<number, string[]> = {};
  steps.forEach(s => {
    const level = levels[s.id] ?? 0;
    if (!stepsByLevel[level]) stepsByLevel[level] = [];
    stepsByLevel[level].push(s.id);
  });

  const NODE_W = 220;
  const NODE_H = 120;
  const H_GAP = 40;
  const V_GAP = 40;

  Object.entries(stepsByLevel).forEach(([levelStr, ids]) => {
    const level = parseInt(levelStr);
    const totalWidth = ids.length * NODE_W + (ids.length - 1) * H_GAP;
    const startX = -(totalWidth / 2);
    ids.forEach((id, col) => {
      positions[id] = {
        x: startX + col * (NODE_W + H_GAP),
        y: level * (NODE_H + V_GAP),
      };
    });
  });

  return positions;
}

// ── Main component ────────────────────────────────────────────────────────────

const WorkflowCanvas: React.FC<Props> = ({
  workflow,
  onAddStep,
  onUpdateStep,
  onDeleteStep,
}) => {
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  // Track whether picker was opened from the sidebar's "Change agent" button
  const [pickerForSidebar, setPickerForSidebar] = useState(false);

  // Derive initial nodes/edges from workflow
  const { nodes: initNodes, edges: initEdges } = workflowToFlow(workflow);
  const [nodes, setNodes, onNodesChange] = useNodesState(initNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initEdges);

  // Sync nodes/edges when workflow prop changes (YAML edit, add/remove step)
  useEffect(() => {
    const { nodes: newNodes, edges: newEdges } = workflowToFlow(workflow);
    // Preserve existing positions where the step still exists
    setNodes(prev => {
      const posMap: Record<string, { x: number; y: number }> = {};
      prev.forEach(n => { posMap[n.id] = n.position; });
      return newNodes.map(n => ({
        ...n,
        position: posMap[n.id] ?? n.position,
      }));
    });
    setEdges(newEdges);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workflow]);

  // Keep selectedStepId valid — clear if the step was deleted
  useEffect(() => {
    if (selectedStepId && !workflow.steps.find(s => s.id === selectedStepId)) {
      setSelectedStepId(null);
    }
  }, [workflow.steps, selectedStepId]);

  const selectedStep = selectedStepId
    ? workflow.steps.find(s => s.id === selectedStepId) ?? null
    : null;

  // ── Handlers ────────────────────────────────────────────────────────────

  const handleNodeClick = useCallback(
    (_event: React.MouseEvent, node: Node) => {
      setSelectedStepId(node.id);
    },
    [],
  );

  const handlePaneClick = useCallback(() => {
    setSelectedStepId(null);
  }, []);

  // Auto-layout: recompute positions using topological sort
  const handleAutoLayout = useCallback(() => {
    const positions = computeAutoLayout(workflow.steps);
    setNodes(prev =>
      prev.map(n => ({
        ...n,
        position: positions[n.id] ?? n.position,
      })),
    );
  }, [workflow.steps, setNodes]);

  // Add Step: open agent picker (not from sidebar)
  const handleAddStepClick = useCallback(() => {
    setPickerForSidebar(false);
    setPickerOpen(true);
  }, []);

  // Agent picked from toolbar "+ Add Step"
  const handleAgentSelected = useCallback(
    (agentId: string) => {
      if (pickerForSidebar && selectedStepId) {
        // Update agent on the currently selected step
        const step = workflow.steps.find(s => s.id === selectedStepId);
        if (step) {
          onUpdateStep({ ...step, agent: agentId });
        }
      } else {
        onAddStep(agentId);
      }
      setPickerOpen(false);
      setPickerForSidebar(false);
    },
    [pickerForSidebar, selectedStepId, workflow.steps, onUpdateStep, onAddStep],
  );

  // Sidebar "Change agent" button
  const handleOpenAgentPickerForSidebar = useCallback(() => {
    setPickerForSidebar(true);
    setPickerOpen(true);
  }, []);

  // ── Render ───────────────────────────────────────────────────────────────

  const isEmpty = workflow.steps.length === 0;

  return (
    <div
      style={{
        display: 'flex',
        width: '100%',
        height: '100%',
        background: t.bgBase,
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      {/* ── ReactFlow canvas ────────────────────────────────────────────────── */}
      <div style={{ flex: 1, position: 'relative', overflow: 'hidden' }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={handleNodeClick}
          onPaneClick={handlePaneClick}
          nodeTypes={nodeTypes}
          nodesDraggable={true}
          nodesConnectable={false}
          fitView
          fitViewOptions={{ padding: 0.3 }}
          style={{ background: t.bgBase }}
          proOptions={{ hideAttribution: true }}
        >
          <Background
            variant={BackgroundVariant.Dots}
            gap={20}
            size={1}
            color={t.borderSubtle}
          />
          <Controls
            style={{
              background: t.bgSurface,
              border: `1px solid ${t.borderDefault}`,
              borderRadius: 6,
            }}
          />
        </ReactFlow>

        {/* ── Floating mini toolbar (top-left) ──────────────────────────────── */}
        <div
          style={{
            position: 'absolute',
            top: 14,
            left: 14,
            display: 'flex',
            gap: 8,
            zIndex: 10,
          }}
        >
          <button
            onClick={handleAddStepClick}
            style={{
              fontSize: 12,
              fontFamily: 'inherit',
              color: t.cyan,
              background: t.cyanBg,
              border: `1px solid ${t.cyanBorder}`,
              borderRadius: 6,
              padding: '6px 12px',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 5,
              fontWeight: 600,
              transition: 'background 0.12s, box-shadow 0.12s',
            }}
            onMouseEnter={e => {
              e.currentTarget.style.background = t.cyanBg;
            }}
            onMouseLeave={e => {
              e.currentTarget.style.background = 'transparent';
            }}
            onFocus={e => {
              e.currentTarget.style.boxShadow = `0 0 0 2px ${t.cyanBorder}`;
            }}
            onBlur={e => {
              e.currentTarget.style.boxShadow = 'none';
            }}
            aria-label="Add step"
          >
            + Add Step
          </button>

          <button
            onClick={handleAutoLayout}
            disabled={isEmpty}
            style={{
              fontSize: 12,
              fontFamily: 'inherit',
              color: isEmpty ? t.textFaint : t.textSecondary,
              background: t.bgSurface,
              border: `1px solid ${t.borderDefault}`,
              borderRadius: 6,
              padding: '6px 12px',
              cursor: isEmpty ? 'default' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 5,
              transition: 'background 0.12s, box-shadow 0.12s',
            }}
            onMouseEnter={e => {
              if (!isEmpty) e.currentTarget.style.background = t.bgTrack;
            }}
            onMouseLeave={e => {
              e.currentTarget.style.background = t.bgSurface;
            }}
            onFocus={e => {
              if (!isEmpty)
                e.currentTarget.style.boxShadow = `0 0 0 2px ${t.cyanBorder}`;
            }}
            onBlur={e => {
              e.currentTarget.style.boxShadow = 'none';
            }}
            aria-label="Auto-layout steps"
          >
            ⚡ Auto-layout
          </button>
        </div>

        {/* ── Empty state ──────────────────────────────────────────────────── */}
        {isEmpty && (
          <div
            style={{
              position: 'absolute',
              inset: 0,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 16,
              pointerEvents: 'none',
            }}
          >
            <div
              style={{
                fontSize: 13,
                fontFamily: 'inherit',
                color: t.textMuted,
              }}
            >
              No steps yet
            </div>
            <button
              onClick={handleAddStepClick}
              style={{
                fontSize: 12,
                fontFamily: 'inherit',
                color: t.cyan,
                background: t.cyanBg,
                border: `1px solid ${t.cyanBorder}`,
                borderRadius: 6,
                padding: '8px 18px',
                cursor: 'pointer',
                fontWeight: 600,
                pointerEvents: 'all',
              }}
              onFocus={e => {
                e.currentTarget.style.boxShadow = `0 0 0 2px ${t.cyanBorder}`;
              }}
              onBlur={e => {
                e.currentTarget.style.boxShadow = 'none';
              }}
              aria-label="Add first step"
            >
              + Add Step
            </button>
          </div>
        )}
      </div>

      {/* ── Step config sidebar ──────────────────────────────────────────────── */}
      {selectedStep && (
        <StepConfigSidebar
          step={selectedStep}
          allSteps={workflow.steps}
          onUpdate={onUpdateStep}
          onDelete={(stepId) => {
            onDeleteStep(stepId);
            setSelectedStepId(null);
          }}
          onClose={() => setSelectedStepId(null)}
          onOpenAgentPicker={handleOpenAgentPickerForSidebar}
        />
      )}

      {/* ── Agent picker modal ───────────────────────────────────────────────── */}
      {pickerOpen && (
        <AgentPickerModal
          onSelect={handleAgentSelected}
          onClose={() => {
            setPickerOpen(false);
            setPickerForSidebar(false);
          }}
        />
      )}
    </div>
  );
};

export default WorkflowCanvas;
