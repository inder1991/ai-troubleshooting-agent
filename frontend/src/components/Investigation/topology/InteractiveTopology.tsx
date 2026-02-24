import React, { useState, useRef, useEffect, useMemo, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import type { V4Findings } from '../../../types';
import { useTopologyData } from './useTopologyData';
import { useForceLayout } from './useForceLayout';
import {
  NODE_RADIUS,
  NODE_COLORS,
  EDGE_COLORS,
  type ResolvedNode,
  type ResolvedEdge,
} from './topology.types';

// ─── Props ───────────────────────────────────────────────────────────────────

interface InteractiveTopologyProps {
  findings: V4Findings;
  selectedService: string | null;
  onSelectService: (id: string | null) => void;
}

// ─── Abbreviation helper ─────────────────────────────────────────────────────

function abbreviate(name: string): string {
  return name.substring(0, 3).toUpperCase();
}

// ─── Main Component ──────────────────────────────────────────────────────────

const InteractiveTopology: React.FC<InteractiveTopologyProps> = ({
  findings,
  selectedService,
  onSelectService,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [isVisible, setIsVisible] = useState(true);

  // IntersectionObserver guard — pause layout computation when scrolled away
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => setIsVisible(entry.isIntersecting),
      { threshold: 0 },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // ResizeObserver for responsive dimensions
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => {
      const { width } = entry.contentRect;
      // Height proportional to width, capped
      setDimensions({ width, height: Math.min(Math.max(width * 0.65, 180), 300) });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Derive graph data
  const { nodes, edges, causalPath } = useTopologyData(findings);

  // Force layout (only runs when visible and dimensions are set)
  const layout = useForceLayout(
    isVisible ? nodes : [],
    isVisible ? edges : [],
    dimensions.width,
    dimensions.height,
  );

  // Compute connected node/edge sets for hover/selection dimming
  const causalPathSet = useMemo(() => new Set(causalPath), [causalPath]);

  const connectedNodeIds = useMemo(() => {
    const active = hoveredNode || selectedService;
    if (!active) return null;
    const set = new Set<string>([active]);
    for (const edge of layout.edges) {
      if (edge.source.id === active) set.add(edge.target.id);
      if (edge.target.id === active) set.add(edge.source.id);
    }
    return set;
  }, [hoveredNode, selectedService, layout.edges]);

  const isNodeDimmed = useCallback(
    (id: string) => connectedNodeIds !== null && !connectedNodeIds.has(id),
    [connectedNodeIds],
  );

  const isEdgeDimmed = useCallback(
    (edge: ResolvedEdge) =>
      connectedNodeIds !== null &&
      !connectedNodeIds.has(edge.source.id) &&
      !connectedNodeIds.has(edge.target.id),
    [connectedNodeIds],
  );

  const { width, height } = dimensions;

  return (
    <div ref={containerRef} className="relative w-full" style={{ minHeight: 180 }}>
      {/* Tactical dot grid overlay */}
      <div
        className="absolute inset-0 pointer-events-none opacity-20"
        style={{
          backgroundImage: 'radial-gradient(circle, rgba(7,182,213,0.15) 1px, transparent 1px)',
          backgroundSize: '16px 16px',
        }}
      />

      {width > 0 && layout.nodes.length > 0 && (
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="w-full"
          style={{ minHeight: 180, maxHeight: 300 }}
          role="img"
          aria-label="Interactive service topology"
        >
          <defs>
            {/* Glow filters */}
            <filter id="glow-red-v2" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="4" result="coloredBlur" />
              <feMerge>
                <feMergeNode in="coloredBlur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            <filter id="glow-cyan-v2" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="3" result="coloredBlur" />
              <feMerge>
                <feMergeNode in="coloredBlur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            <filter id="glow-amber-v2" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="3" result="coloredBlur" />
              <feMerge>
                <feMergeNode in="coloredBlur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>

            {/* Arrowhead markers */}
            <marker id="arrow-normal-v2" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
              <polygon points="0 0, 8 3, 0 6" fill="#475569" />
            </marker>
            <marker id="arrow-error-v2" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
              <polygon points="0 0, 8 3, 0 6" fill="#ef4444" />
            </marker>

            {/* Edge path definitions (for animateMotion) */}
            {layout.edges.map((edge) => (
              <path key={edge.pathId} id={edge.pathId} d={edge.pathD} fill="none" />
            ))}
          </defs>

          {/* Layer 1: Edge lines */}
          {layout.edges.map((edge) => (
            <TopologyEdge
              key={edge.pathId}
              edge={edge}
              dimmed={isEdgeDimmed(edge)}
            />
          ))}

          {/* Layer 2: Data packets */}
          {layout.edges.map((edge) => (
            <DataPacket
              key={`packet-${edge.pathId}`}
              edge={edge}
              dimmed={isEdgeDimmed(edge)}
            />
          ))}

          {/* Layer 3: Nodes */}
          <AnimatePresence>
            {layout.nodes.map((node) => (
              <TopologyNode
                key={node.id}
                node={node}
                dimmed={isNodeDimmed(node.id)}
                isSelected={selectedService === node.id}
                isHovered={hoveredNode === node.id}
                isCausal={causalPathSet.has(node.id)}
                onHoverStart={() => setHoveredNode(node.id)}
                onHoverEnd={() => setHoveredNode(null)}
                onClick={() => onSelectService(node.id)}
              />
            ))}
          </AnimatePresence>
        </svg>
      )}

      {/* "Filtering" label when a service is selected */}
      {selectedService && (
        <div className="absolute bottom-2 left-2 flex items-center gap-1.5 px-2 py-1 rounded bg-cyan-500/10 border border-cyan-500/20">
          <span className="w-1.5 h-1.5 rounded-full bg-cyan-400" />
          <span className="text-[9px] text-cyan-400 font-mono">Filtering: {selectedService}</span>
        </div>
      )}
    </div>
  );
};

// ─── TopologyEdge ────────────────────────────────────────────────────────────

const TopologyEdge: React.FC<{
  edge: ResolvedEdge;
  dimmed: boolean;
}> = ({ edge, dimmed }) => {
  const colors = EDGE_COLORS[edge.type];
  const isCausal = edge.type === 'causal_path';
  const marker = edge.type === 'error' || edge.type === 'causal_path'
    ? 'url(#arrow-error-v2)'
    : 'url(#arrow-normal-v2)';

  return (
    <use
      href={`#${edge.pathId}`}
      stroke={colors.stroke}
      strokeWidth={colors.width}
      opacity={dimmed ? 0.08 : colors.opacity}
      markerEnd={marker}
      className={isCausal ? 'topology-causal-edge' : undefined}
      style={{ transition: 'opacity 0.3s ease' }}
    />
  );
};

// ─── DataPacket ──────────────────────────────────────────────────────────────

const DataPacket: React.FC<{
  edge: ResolvedEdge;
  dimmed: boolean;
}> = ({ edge, dimmed }) => {
  if (dimmed) return null;

  const isError = edge.type === 'error' || edge.type === 'causal_path';
  const dur = isError ? '1.5s' : '3s';
  const r = isError ? 3 : 2;
  const fill = isError ? '#ef4444' : '#06b6d4';
  const glowFilter = isError ? 'url(#glow-red-v2)' : 'url(#glow-cyan-v2)';

  return (
    <circle r={r} fill={fill} opacity={0.8} filter={glowFilter}>
      <animateMotion dur={dur} repeatCount="indefinite">
        <mpath href={`#${edge.pathId}`} />
      </animateMotion>
    </circle>
  );
};

// ─── TopologyNode ────────────────────────────────────────────────────────────

const TopologyNode: React.FC<{
  node: ResolvedNode;
  dimmed: boolean;
  isSelected: boolean;
  isHovered: boolean;
  isCausal: boolean;
  onHoverStart: () => void;
  onHoverEnd: () => void;
  onClick: () => void;
}> = ({ node, dimmed, isSelected, isHovered, isCausal, onHoverStart, onHoverEnd, onClick }) => {
  const colors = NODE_COLORS[node.role];
  const isP0 = node.role === 'patient_zero';
  const showCrashRing = node.isCrashloop || node.isOomKilled;

  const filter = isP0 || showCrashRing
    ? 'url(#glow-red-v2)'
    : isCausal
      ? 'url(#glow-amber-v2)'
      : undefined;

  // Use SVG transform for positioning (reliable), Framer Motion only for entrance/opacity
  return (
    <motion.g
      initial={{ opacity: 0 }}
      animate={{
        opacity: dimmed ? 0.2 : 1,
        scale: isHovered ? 1.12 : 1,
      }}
      exit={{ opacity: 0 }}
      transition={{ type: 'spring', stiffness: 300, damping: 25 }}
      transform={`translate(${node.x}, ${node.y})`}
      style={{ cursor: 'pointer', transformOrigin: `${node.x}px ${node.y}px` }}
      onPointerEnter={onHoverStart}
      onPointerLeave={onHoverEnd}
      onClick={onClick}
    >
      {/* Crashloop pulsing outer ring */}
      {showCrashRing && (
        <circle
          r={NODE_RADIUS + 5}
          fill="none"
          stroke="#ef4444"
          strokeWidth={2}
          className="animate-pulse-red"
          opacity={0.6}
        />
      )}

      {/* Selected breathing ring */}
      {isSelected && (
        <circle
          r={NODE_RADIUS + 5}
          fill="none"
          stroke="#06b6d4"
          strokeWidth={2}
          className="topology-select-ring"
        />
      )}

      {/* Main node circle */}
      <circle
        r={NODE_RADIUS}
        fill={showCrashRing ? '#7f1d1d' : colors.fill}
        stroke={showCrashRing ? '#ef4444' : colors.stroke}
        strokeWidth={isP0 || showCrashRing ? 2.5 : 1.5}
        filter={filter}
      />

      {/* Inner label: P0 or 3-letter abbreviation */}
      <text
        textAnchor="middle"
        dy="4"
        fill={isP0 ? '#ef4444' : '#94a3b8'}
        fontSize={isP0 ? 10 : 8}
        fontWeight={isP0 ? 'bold' : 'normal'}
        fontFamily="monospace"
        style={{ pointerEvents: 'none' }}
      >
        {isP0 ? 'P0' : abbreviate(node.id)}
      </text>

      {/* Service name below */}
      <text
        y={NODE_RADIUS + 14}
        textAnchor="middle"
        fill="#94a3b8"
        fontSize="9"
        fontFamily="monospace"
        style={{ pointerEvents: 'none' }}
      >
        {node.id.length > 14 ? node.id.slice(0, 12) + '..' : node.id}
      </text>
    </motion.g>
  );
};

export default InteractiveTopology;
