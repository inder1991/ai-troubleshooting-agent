import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import type { WorkflowConfig, WorkflowNode } from './workflowConfigs';
import { WF_COLORS } from './workflowConfigs';
import type { NodeStatus } from './AnimationNode';
import type { EdgeStatus } from './AnimationEdge';
import AnimationNode from './AnimationNode';
import AnimationEdge from './AnimationEdge';
import PlaybackBar from './PlaybackBar';
import SpotlightPanel from './SpotlightPanel';

// Tier-based dimensions for edge connection points
const TIER_DIMS: Record<string, { width: number; height: number }> = {
  landmark: { width: 180, height: 64 },
  agent:    { width: 150, height: 56 },
  pipeline: { width: 130, height: 44 },
};

interface WorkflowAnimationProps {
  config: WorkflowConfig;
}

const WorkflowAnimation: React.FC<WorkflowAnimationProps> = ({ config }) => {
  const [elapsed, setElapsed] = useState(0);
  const [isPlaying, setIsPlaying] = useState(true);
  const rafRef = useRef<number | null>(null);
  const lastTickRef = useRef<number | null>(null);
  const doneRef = useRef(false);
  const prefersReducedMotion = useReducedMotion();

  // ─── Animation loop ───
  useEffect(() => {
    if (!isPlaying || prefersReducedMotion) {
      lastTickRef.current = null;
      return;
    }

    const tick = (timestamp: number) => {
      if (lastTickRef.current === null) {
        lastTickRef.current = timestamp;
      }
      const delta = (timestamp - lastTickRef.current) / 1000;
      lastTickRef.current = timestamp;

      setElapsed((prev) => {
        const next = prev + delta;
        if (next >= config.totalDuration) {
          doneRef.current = true;
          setIsPlaying(false);
          return config.totalDuration;
        }
        return next;
      });

      if (!doneRef.current) {
        rafRef.current = requestAnimationFrame(tick);
      }
    };

    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [isPlaying, config.totalDuration, prefersReducedMotion]);

  // If reduced motion, jump to end
  useEffect(() => {
    if (prefersReducedMotion) {
      setElapsed(config.totalDuration);
      setIsPlaying(false);
      doneRef.current = true;
    }
  }, [prefersReducedMotion, config.totalDuration]);

  const handlePlayPause = useCallback(() => {
    if (elapsed >= config.totalDuration) {
      setElapsed(0);
      doneRef.current = false;
      setIsPlaying(true);
    } else {
      setIsPlaying((p) => !p);
    }
  }, [elapsed, config.totalDuration]);

  const handleReset = useCallback(() => {
    setElapsed(0);
    setIsPlaying(false);
    lastTickRef.current = null;
    doneRef.current = false;
  }, []);

  const handleSeek = useCallback((time: number) => {
    setElapsed(Math.max(0, Math.min(time, config.totalDuration)));
    lastTickRef.current = null;
  }, [config.totalDuration]);

  // ─── Current phase ───
  const currentPhase = useMemo(() => {
    for (let i = config.phases.length - 1; i >= 0; i--) {
      if (elapsed >= config.phases[i].startTime) return config.phases[i];
    }
    return config.phases[0];
  }, [elapsed, config.phases]);

  // ─── Node statuses ───
  const nodeStatuses = useMemo(() => {
    const statuses: Record<string, { status: NodeStatus; progress: number }> = {};
    for (const node of config.nodes) {
      statuses[node.id] = { status: 'pending', progress: 0 };
    }

    for (const phase of config.phases) {
      const phaseStart = phase.startTime;
      const phaseEnd = phase.startTime + phase.duration;
      if (elapsed < phaseStart) continue;

      const phasePct = Math.min((elapsed - phaseStart) / phase.duration, 1);

      if (phase.parallel) {
        for (const nodeId of phase.activateNodes) {
          statuses[nodeId] = elapsed >= phaseEnd
            ? { status: 'complete', progress: 1 }
            : { status: 'active', progress: phasePct };
        }
      } else {
        const nodeCount = phase.activateNodes.length;
        if (nodeCount === 0) continue;
        const perNode = phase.duration / nodeCount;
        for (let i = 0; i < nodeCount; i++) {
          const nodeStart = phaseStart + i * perNode;
          const nodeEnd = nodeStart + perNode;
          const nodeId = phase.activateNodes[i];
          if (elapsed >= nodeEnd) {
            statuses[nodeId] = { status: 'complete', progress: 1 };
          } else if (elapsed >= nodeStart) {
            statuses[nodeId] = { status: 'active', progress: (elapsed - nodeStart) / perNode };
          }
        }
      }
    }
    return statuses;
  }, [elapsed, config]);

  // ─── Edge statuses ───
  const edgeStatuses = useMemo(() => {
    const statuses: Record<string, EdgeStatus> = {};
    for (const edge of config.edges) {
      statuses[`${edge.from}->${edge.to}`] = 'pending';
    }

    for (const phase of config.phases) {
      if (elapsed < phase.startTime) continue;
      const phaseEnd = phase.startTime + phase.duration;
      const edgeCount = phase.activateEdges.length;
      if (edgeCount === 0) continue;

      if (phase.parallel) {
        for (const [from, to] of phase.activateEdges) {
          statuses[`${from}->${to}`] = elapsed >= phaseEnd ? 'complete' : 'active';
        }
      } else {
        const perEdge = phase.duration / edgeCount;
        for (let i = 0; i < edgeCount; i++) {
          const [from, to] = phase.activateEdges[i];
          const edgeStart = phase.startTime + i * perEdge;
          const edgeEnd = edgeStart + perEdge;
          if (elapsed >= edgeEnd) {
            statuses[`${from}->${to}`] = 'complete';
          } else if (elapsed >= edgeStart) {
            statuses[`${from}->${to}`] = 'active';
          }
        }
      }
    }
    return statuses;
  }, [elapsed, config]);

  // ─── Node position lookup ───
  const nodeMap = useMemo(() => {
    const map: Record<string, WorkflowNode> = {};
    for (const n of config.nodes) map[n.id] = n;
    return map;
  }, [config.nodes]);

  // ─── Camera position ───
  const VIEWPORT_WIDTH = 500;
  const cameraX = useMemo(() => {
    const col = currentPhase.phaseColumn;
    if (col === undefined) return 0;
    return Math.max(0, Math.min(col - VIEWPORT_WIDTH / 2, config.viewBoxWidth - VIEWPORT_WIDTH));
  }, [currentPhase, config.viewBoxWidth]);

  // ─── Active agent for spotlight ───
  const activeAgent = useMemo(() => {
    for (const node of config.nodes) {
      const ns = nodeStatuses[node.id];
      if (ns?.status === 'active' && (node.tier === 'agent' || node.tier === 'landmark')) {
        return {
          duck: node.duck,
          name: node.label,
          subtitle: node.subtitle ?? 'Processing...',
          state: 'working' as const,
          progress: ns.progress,
        };
      }
    }
    return null;
  }, [nodeStatuses, config.nodes]);

  // ─── Finale state ───
  const isFinale = elapsed >= config.totalDuration;

  // ─── Dispatch pulse ───
  const showDispatchPulse = useMemo(() => {
    const fanPhase = config.phases.find(p => p.parallel && p.activateNodes.length > 2);
    if (!fanPhase) return null;
    const pulseStart = fanPhase.startTime;
    if (elapsed >= pulseStart && elapsed < pulseStart + 0.8) {
      const sourceEdge = fanPhase.activateEdges[0];
      if (!sourceEdge) return null;
      const sourceNode = nodeMap[sourceEdge[0]];
      if (!sourceNode) return null;
      return { x: sourceNode.x, y: sourceNode.y, progress: (elapsed - pulseStart) / 0.8 };
    }
    return null;
  }, [elapsed, config.phases, nodeMap]);

  // ─── Phase divider positions ───
  const phaseDividers = useMemo(() => {
    const dividers: { x: number; label: string }[] = [];
    const seen = new Set<number>();
    for (const phase of config.phases) {
      if (phase.phaseColumn && !seen.has(phase.phaseColumn)) {
        seen.add(phase.phaseColumn);
        dividers.push({ x: phase.phaseColumn, label: phase.name.toUpperCase() });
      }
    }
    return dividers;
  }, [config.phases]);

  const viewBox = `0 0 ${config.viewBoxWidth} ${config.viewBoxHeight}`;

  // ─── Reduced motion: static view ───
  if (prefersReducedMotion) {
    return (
      <div className="flex h-full">
        <div className="flex-1 overflow-auto p-4" style={{ backgroundColor: WF_COLORS.pageBg }}>
          <svg width="100%" height="100%" viewBox={viewBox} preserveAspectRatio="xMidYMid meet">
            {phaseDividers.map((d) => (
              <text
                key={d.x}
                x={d.x}
                y={20}
                textAnchor="middle"
                fill={WF_COLORS.mutedText}
                fontSize="9"
                fontWeight="700"
                fontFamily="DM Sans, system-ui"
                letterSpacing="0.1em"
              >
                {d.label}
              </text>
            ))}

            {config.edges.map((edge) => {
              const from = nodeMap[edge.from];
              const to = nodeMap[edge.to];
              if (!from || !to) return null;
              const fromDims = TIER_DIMS[from.tier];
              const toDims = TIER_DIMS[to.tier];
              return (
                <AnimationEdge
                  key={`${edge.from}->${edge.to}`}
                  fromX={from.x} fromY={from.y}
                  toX={to.x} toY={to.y}
                  status="complete"
                  color={edge.color ?? WF_COLORS.amber}
                  fromWidth={fromDims.width} fromHeight={fromDims.height}
                  toWidth={toDims.width} toHeight={toDims.height}
                />
              );
            })}

            {config.nodes.map((node) => (
              <AnimationNode
                key={node.id}
                id={node.id}
                label={node.label}
                duck={node.duck}
                x={node.x} y={node.y}
                tier={node.tier}
                status="complete"
                progress={1}
                subtitle={node.subtitle}
                badge={node.badge}
                accentColor={node.accentColor}
              />
            ))}

            {config.nodes
              .filter(n => n.outputLabels)
              .map(n => n.outputLabels!.map((label, i) => (
                <text
                  key={`${n.id}-out-${i}`}
                  x={n.x}
                  y={n.y + 50 + i * 18}
                  textAnchor="middle"
                  fill={WF_COLORS.amber}
                  fontSize="10"
                  fontWeight="600"
                  fontFamily="DM Sans, system-ui"
                >
                  {label}
                </text>
              )))}
          </svg>
        </div>
      </div>
    );
  }

  // ─── Animated view ───
  return (
    <div className="flex h-full">
      <SpotlightPanel activeAgent={activeAgent} isComplete={isFinale} />

      <div className="flex-1 flex flex-col overflow-hidden" style={{ backgroundColor: WF_COLORS.pageBg }}>
        <div className="flex-1 overflow-hidden relative">
          <motion.div
            className="h-full"
            animate={{ x: -cameraX }}
            transition={{ type: 'tween', duration: 0.8, ease: [0.25, 0.1, 0.25, 1] }}
            style={{ width: config.viewBoxWidth }}
          >
            <svg
              width={config.viewBoxWidth}
              height="100%"
              viewBox={viewBox}
              preserveAspectRatio="xMidYMid meet"
              className="h-full"
            >
              <defs>
                <filter id="node-glow" x="-50%" y="-50%" width="200%" height="200%">
                  <feGaussianBlur in="SourceAlpha" stdDeviation="4" result="blur" />
                  <feFlood floodColor={WF_COLORS.amber} floodOpacity="0.3" result="color" />
                  <feComposite in="color" in2="blur" operator="in" result="glow" />
                  <feMerge>
                    <feMergeNode in="glow" />
                    <feMergeNode in="SourceGraphic" />
                  </feMerge>
                </filter>
              </defs>

              {/* Phase divider lines and labels */}
              {phaseDividers.map((d, i) => {
                const nextX = phaseDividers[i + 1]?.x;
                const dividerX = nextX ? (d.x + nextX) / 2 : undefined;
                return (
                  <g key={d.x}>
                    <text
                      x={d.x}
                      y={25}
                      textAnchor="middle"
                      fill={WF_COLORS.mutedText}
                      fontSize="9"
                      fontWeight="700"
                      fontFamily="DM Sans, system-ui"
                      letterSpacing="0.1em"
                      opacity={0.6}
                    >
                      {d.label}
                    </text>
                    {dividerX && (
                      <line
                        x1={dividerX}
                        y1={35}
                        x2={dividerX}
                        y2={config.viewBoxHeight - 10}
                        stroke={WF_COLORS.border}
                        strokeWidth={1}
                        strokeDasharray="4 4"
                        opacity={0.4}
                      />
                    )}
                  </g>
                );
              })}

              {/* Dispatch pulse effect */}
              {showDispatchPulse && (
                <motion.circle
                  cx={showDispatchPulse.x}
                  cy={showDispatchPulse.y}
                  fill="none"
                  stroke={WF_COLORS.amber}
                  strokeWidth={2}
                  initial={{ r: 10, opacity: 0.8 }}
                  animate={{ r: 120, opacity: 0 }}
                  transition={{ duration: 0.8, ease: 'easeOut' }}
                />
              )}

              {/* Edges */}
              {config.edges.map((edge) => {
                const from = nodeMap[edge.from];
                const to = nodeMap[edge.to];
                if (!from || !to) return null;
                const key = `${edge.from}->${edge.to}`;
                const fromDims = TIER_DIMS[from.tier];
                const toDims = TIER_DIMS[to.tier];
                return (
                  <AnimationEdge
                    key={key}
                    fromX={from.x} fromY={from.y}
                    toX={to.x} toY={to.y}
                    status={edgeStatuses[key] || 'pending'}
                    color={edge.color}
                    fromWidth={fromDims.width} fromHeight={fromDims.height}
                    toWidth={toDims.width} toHeight={toDims.height}
                  />
                );
              })}

              {/* Nodes */}
              {config.nodes.map((node, idx) => {
                const ns = nodeStatuses[node.id] || { status: 'pending' as const, progress: 0 };
                const isDimmed = isFinale && !node.id.includes('report');
                // Stagger dimming left-to-right by x-position (100ms per step)
                const dimDelay = isDimmed ? (node.x / config.viewBoxWidth) * (config.nodes.length * 0.1) : 0;
                return (
                  <AnimationNode
                    key={node.id}
                    id={node.id}
                    label={node.label}
                    duck={node.duck}
                    x={node.x} y={node.y}
                    tier={node.tier}
                    status={ns.status}
                    progress={ns.progress}
                    subtitle={node.subtitle}
                    badge={node.badge}
                    accentColor={node.accentColor}
                    dimmed={isDimmed}
                    dimDelay={dimDelay}
                  />
                );
              })}

              {/* Finale: output labels */}
              {isFinale && config.nodes
                .filter(n => n.outputLabels)
                .map(n => n.outputLabels!.map((label, i) => (
                  <motion.text
                    key={`${n.id}-out-${i}`}
                    x={n.x}
                    y={n.y + 55 + i * 20}
                    textAnchor="middle"
                    fill={WF_COLORS.amber}
                    fontSize="10"
                    fontWeight="600"
                    fontFamily="DM Sans, system-ui"
                    initial={{ opacity: 0, y: n.y + 60 + i * 20 }}
                    animate={{ opacity: 1, y: n.y + 55 + i * 20 }}
                    transition={{ type: 'spring', stiffness: 200, delay: 0.3 + i * 0.15 }}
                  >
                    {label}
                  </motion.text>
                )))}

              {/* Finale: "Diagnosis Complete" label */}
              {isFinale && (() => {
                const reportNode = config.nodes.find(n => n.id.includes('report'));
                if (!reportNode || !reportNode.outputLabels) return null;
                const yOffset = reportNode.y + 55 + reportNode.outputLabels.length * 20 + 15;
                return (
                  <motion.text
                    x={reportNode.x}
                    y={yOffset}
                    textAnchor="middle"
                    fill={WF_COLORS.amber}
                    fontSize="12"
                    fontWeight="700"
                    fontFamily="DM Sans, system-ui"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 1.0 }}
                  >
                    Diagnosis Complete
                  </motion.text>
                );
              })()}
            </svg>
          </motion.div>
        </div>

        <PlaybackBar
          isPlaying={isPlaying}
          elapsed={elapsed}
          totalDuration={config.totalDuration}
          phaseName={currentPhase.name}
          phaseDescription={currentPhase.description}
          onPlayPause={handlePlayPause}
          onReset={handleReset}
          onSeek={handleSeek}
        />
      </div>
    </div>
  );
};

export default WorkflowAnimation;
