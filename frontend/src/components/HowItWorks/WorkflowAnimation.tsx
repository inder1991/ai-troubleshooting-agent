import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { motion } from 'framer-motion';
import type { WorkflowConfig } from './workflowConfigs';
import type { NodeStatus } from './AnimationNode';
import type { EdgeStatus } from './AnimationEdge';
import AnimationNode from './AnimationNode';
import AnimationEdge from './AnimationEdge';
import PlaybackBar from './PlaybackBar';

interface WorkflowAnimationProps {
  config: WorkflowConfig;
}

const WorkflowAnimation: React.FC<WorkflowAnimationProps> = ({ config }) => {
  const [elapsed, setElapsed] = useState(0);
  const [isPlaying, setIsPlaying] = useState(true);
  const rafRef = useRef<number | null>(null);
  const lastTickRef = useRef<number | null>(null);
  const doneRef = useRef(false);

  // Animation loop
  useEffect(() => {
    if (!isPlaying) {
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
  }, [isPlaying, config.totalDuration]);

  const handlePlayPause = useCallback(() => {
    if (elapsed >= config.totalDuration) {
      // Reset and play
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

  // Determine current phase
  const currentPhase = useMemo(() => {
    for (let i = config.phases.length - 1; i >= 0; i--) {
      if (elapsed >= config.phases[i].startTime) return config.phases[i];
    }
    return config.phases[0];
  }, [elapsed, config.phases]);

  // Compute node statuses
  const nodeStatuses = useMemo(() => {
    const statuses: Record<string, { status: NodeStatus; progress: number }> = {};

    // Initialize all as pending
    for (const node of config.nodes) {
      statuses[node.id] = { status: 'pending', progress: 0 };
    }

    for (const phase of config.phases) {
      const phaseStart = phase.startTime;
      const phaseEnd = phase.startTime + phase.duration;

      if (elapsed < phaseStart) continue;

      const phaseElapsed = elapsed - phaseStart;
      const phasePct = Math.min(phaseElapsed / phase.duration, 1);

      if (phase.parallel) {
        // All nodes activate together
        for (const nodeId of phase.activateNodes) {
          if (elapsed >= phaseEnd) {
            statuses[nodeId] = { status: 'complete', progress: 1 };
          } else {
            statuses[nodeId] = { status: 'active', progress: phasePct };
          }
        }
      } else {
        // Sequential activation within phase
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
            const nodePct = (elapsed - nodeStart) / perNode;
            statuses[nodeId] = { status: 'active', progress: nodePct };
          }
        }
      }
    }

    return statuses;
  }, [elapsed, config]);

  // Compute edge statuses
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
          const key = `${from}->${to}`;
          statuses[key] = elapsed >= phaseEnd ? 'complete' : 'active';
        }
      } else {
        const perEdge = phase.duration / edgeCount;
        for (let i = 0; i < edgeCount; i++) {
          const [from, to] = phase.activateEdges[i];
          const key = `${from}->${to}`;
          const edgeStart = phase.startTime + i * perEdge;
          const edgeEnd = edgeStart + perEdge;

          if (elapsed >= edgeEnd) {
            statuses[key] = 'complete';
          } else if (elapsed >= edgeStart) {
            statuses[key] = 'active';
          }
        }
      }
    }

    return statuses;
  }, [elapsed, config]);

  // Compute SVG viewBox based on node positions
  const viewBox = useMemo(() => {
    const xs = config.nodes.map((n) => n.x);
    const ys = config.nodes.map((n) => n.y);
    const minX = Math.min(...xs) - 120;
    const maxX = Math.max(...xs) + 120;
    const minY = Math.min(...ys) - 50;
    const maxY = Math.max(...ys) + 60;
    return `${minX} ${minY} ${maxX - minX} ${maxY - minY}`;
  }, [config.nodes]);

  // Build node position lookup
  const nodePositions = useMemo(() => {
    const map: Record<string, { x: number; y: number }> = {};
    for (const n of config.nodes) {
      map[n.id] = { x: n.x, y: n.y };
    }
    return map;
  }, [config.nodes]);

  return (
    <div className="flex flex-col h-full">
      {/* SVG Canvas */}
      <div className="flex-1 overflow-hidden relative">
        <svg
          width="100%"
          height="100%"
          viewBox={viewBox}
          preserveAspectRatio="xMidYMid meet"
          className="w-full h-full"
        >
          {/* Global glow filter */}
          <defs>
            <filter id="node-glow" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur in="SourceAlpha" stdDeviation="4" result="blur" />
              <feFlood floodColor="#07b6d5" floodOpacity="0.3" result="color" />
              <feComposite in="color" in2="blur" operator="in" result="glow" />
              <feMerge>
                <feMergeNode in="glow" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            <linearGradient id="completion-gradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#07b6d5" stopOpacity="0" />
              <stop offset="50%" stopColor="#07b6d5" stopOpacity="0.6" />
              <stop offset="100%" stopColor="#07b6d5" stopOpacity="0" />
            </linearGradient>
          </defs>

          {/* Render edges first (behind nodes) */}
          {config.edges.map((edge) => {
            const from = nodePositions[edge.from];
            const to = nodePositions[edge.to];
            if (!from || !to) return null;
            const key = `${edge.from}->${edge.to}`;
            return (
              <AnimationEdge
                key={key}
                fromX={from.x}
                fromY={from.y}
                toX={to.x}
                toY={to.y}
                status={edgeStatuses[key] || 'pending'}
                color={edge.color}
              />
            );
          })}

          {/* Render nodes */}
          {config.nodes.map((node) => {
            const ns = nodeStatuses[node.id] || { status: 'pending' as const, progress: 0 };
            return (
              <AnimationNode
                key={node.id}
                id={node.id}
                label={node.label}
                duck={node.duck}
                x={node.x}
                y={node.y}
                status={ns.status}
                progress={ns.progress}
                subtitle={node.subtitle}
                badge={node.badge}
              />
            );
          })}

          {/* Completion pulse — subtle top-to-bottom glow when done */}
          {elapsed >= config.totalDuration && (() => {
            const [vbMinX, , vbWidth] = viewBox.split(' ').map(Number);
            return (
              <motion.rect
                x={vbMinX}
                y={0}
                width={vbWidth}
                height={4}
                fill="url(#completion-gradient)"
                initial={{ y: config.nodes[0].y - 50 }}
                animate={{ y: config.nodes[config.nodes.length - 1].y + 60 }}
                transition={{ duration: 2, ease: 'easeInOut' }}
                opacity={0.3}
              />
            );
          })()}
        </svg>
      </div>

      {/* Playback bar */}
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
  );
};

export default WorkflowAnimation;
