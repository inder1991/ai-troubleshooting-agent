import { useState, useMemo, useEffect, useRef, useCallback } from 'react';
import type { StepSpec, StepRunDetail, StepRunStatus } from '../../../../types';
import type { LiveEvent } from '../StepStatusPanel';
import DagNode from './DagNode';
import DagEdge from './DagEdge';
import { buildDagModel, computeFailurePath, isEdgeOnFailurePath, edgeStatus } from './dagHelpers';
import { useElkLayout } from './useElkLayout';
import { useDagViewport } from './useDagViewport';

export interface DagViewProps {
  steps: StepSpec[];
  stepRuns: StepRunDetail[];
  liveEvents?: LiveEvent[];
  selectedNodeId?: string | null;
  onNodeClick?: (nodeId: string) => void;
}

/**
 * Merge stepRuns with live events to produce a status map.
 * Events overlay on initial statuses (same concept as StepStatusPanel).
 */
function buildStatusMap(
  stepRuns: StepRunDetail[],
  liveEvents?: LiveEvent[],
): Map<string, { status: StepRunStatus; duration_ms?: number; error?: { type?: string; message?: string } }> {
  const map = new Map<string, { status: StepRunStatus; duration_ms?: number; error?: { type?: string; message?: string } }>();

  for (const sr of stepRuns) {
    map.set(sr.step_id, {
      status: sr.status,
      duration_ms: sr.duration_ms,
      error: sr.error ? { type: sr.error.type, message: sr.error.message } : undefined,
    });
  }

  if (liveEvents) {
    for (const ev of liveEvents) {
      const stepId = ev.data.step_id ?? ev.data.node_id;
      if (stepId && ev.data.status) {
        const existing = map.get(stepId);
        map.set(stepId, {
          ...existing,
          status: ev.data.status,
          error: ev.data.error ?? existing?.error,
        });
      }
    }
  }

  return map;
}

export function DagView({ steps, stepRuns, liveEvents, selectedNodeId, onNodeClick }: DagViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const didAutoFit = useRef(false);

  // 1. Build status map
  const statusMap = useMemo(() => buildStatusMap(stepRuns, liveEvents), [stepRuns, liveEvents]);

  // 2. Build DAG model
  const dagModel = useMemo(() => buildDagModel(steps, statusMap), [steps, statusMap]);

  // 3. Compute layout via ELK
  const { layout, loading } = useElkLayout(dagModel);

  // 4. Viewport hook
  const { viewport, fitToView, handlers } = useDagViewport();

  // 5. Auto-fit on first layout
  useEffect(() => {
    if (layout && containerRef.current && !didAutoFit.current) {
      didAutoFit.current = true;
      const rect = containerRef.current.getBoundingClientRect();
      fitToView(rect.width, rect.height, layout.width, layout.height);
    }
  }, [layout, fitToView]);

  // 6. Failure path highlighting
  const { highlighted, dimmed } = useMemo(() => computeFailurePath(dagModel), [dagModel]);
  const hasFailures = highlighted.size > 0;
  const [showAll, setShowAll] = useState(false);

  // Reset showAll when failures appear/disappear
  useEffect(() => {
    if (!hasFailures) setShowAll(false);
  }, [hasFailures]);

  const handleFit = useCallback(() => {
    if (layout && containerRef.current) {
      const rect = containerRef.current.getBoundingClientRect();
      fitToView(rect.width, rect.height, layout.width, layout.height);
    }
  }, [layout, fitToView]);

  // Determine which set to use for dimming
  const effectiveDimmed = hasFailures && !showAll ? dimmed : new Set<string>();
  const effectiveHighlighted = hasFailures && !showAll ? highlighted : new Set<string>();

  return (
    <div
      data-testid="dag-view-container"
      ref={containerRef}
      className="relative w-full h-full overflow-hidden bg-wr-bg-secondary rounded-lg"
    >
      {loading && (
        <div className="absolute inset-0 flex items-center justify-center text-wr-text-secondary">
          Computing layout...
        </div>
      )}

      {layout && (
        <svg
          className="w-full h-full"
          {...handlers}
          style={{ touchAction: 'none' }}
        >
          <defs>
            <marker
              id="arrowhead"
              markerWidth="10"
              markerHeight="7"
              refX="10"
              refY="3.5"
              orient="auto"
            >
              <polygon points="0 0, 10 3.5, 0 7" fill="#71717a" />
            </marker>
          </defs>

          <g transform={`translate(${viewport.x}, ${viewport.y}) scale(${viewport.zoom})`}>
            {/* Edges first (below nodes) */}
            {layout.edges.map((edge) => {
              const sourceNode = dagModel.nodes.find((n) => n.id === edge.source);
              const eStatus = sourceNode ? edgeStatus(sourceNode.status) : 'pending';
              const onPath = isEdgeOnFailurePath(edge, effectiveHighlighted);
              const isDimmed = effectiveDimmed.has(edge.source) || effectiveDimmed.has(edge.target);

              return (
                <DagEdge
                  key={`${edge.source}-${edge.target}`}
                  edge={edge}
                  edgeStatus={eStatus}
                  dimmed={isDimmed}
                  onFailurePath={onPath}
                />
              );
            })}

            {/* Nodes */}
            {layout.nodes.map((node) => (
              <DagNode
                key={node.id}
                node={node}
                dimmed={effectiveDimmed.has(node.id)}
                highlighted={effectiveHighlighted.has(node.id)}
                selected={selectedNodeId === node.id}
                onClick={onNodeClick}
              />
            ))}
          </g>
        </svg>
      )}

      {/* Controls overlay */}
      <div className="absolute top-2 right-2 flex gap-2">
        <button
          onClick={handleFit}
          className="px-3 py-1 text-xs bg-wr-bg-tertiary text-wr-text-primary rounded hover:bg-wr-bg-hover"
          aria-label="Fit"
        >
          Fit
        </button>
        {hasFailures && (
          <button
            onClick={() => setShowAll((p) => !p)}
            className="px-3 py-1 text-xs bg-wr-bg-tertiary text-wr-text-primary rounded hover:bg-wr-bg-hover"
          >
            {showAll ? 'Show failure path' : 'Show all'}
          </button>
        )}
      </div>
    </div>
  );
}
