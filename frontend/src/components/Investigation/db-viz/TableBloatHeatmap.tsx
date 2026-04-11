import React, { useState, useMemo } from 'react';
import { VIZ_COLORS } from '../db-board/constants';

interface TableBloat {
  name: string;
  bloat_ratio: number;
  dead_tuples: number;
  size_mb: number;
}

interface TableBloatHeatmapProps {
  tables: TableBloat[];
}

function bloatColor(ratio: number): string {
  if (ratio > 0.7) return VIZ_COLORS.critical;
  if (ratio > 0.4) return VIZ_COLORS.warning;
  if (ratio > 0.15) return VIZ_COLORS.good;
  return VIZ_COLORS.excellent;
}

function bloatOpacity(ratio: number): number {
  return Math.max(0.2, Math.min(ratio, 1));
}

function formatTuples(count: number): string {
  if (count >= 1_000_000) return `${(count / 1_000_000).toFixed(1)}M`;
  if (count >= 1_000) return `${(count / 1_000).toFixed(1)}K`;
  return String(count);
}

function formatSize(mb: number): string {
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
  return `${mb.toFixed(1)} MB`;
}

const TableBloatHeatmap: React.FC<TableBloatHeatmapProps> = ({ tables }) => {
  const [showAll, setShowAll] = useState(false);
  const [expandedTable, setExpandedTable] = useState<string | null>(null);

  if (tables.length === 0) {
    return (
      <div className="text-center py-4">
        <span className="material-symbols-outlined text-2xl text-slate-700 block mb-1">grid_view</span>
        <p className="text-body-xs text-slate-400">No table bloat data</p>
      </div>
    );
  }

  const sorted = useMemo(() => [...tables].sort((a, b) => b.bloat_ratio - a.bloat_ratio), [tables]);
  const displayed = showAll ? sorted : sorted.slice(0, 20);

  return (
    <div className="bg-duck-card/30 border border-duck-border rounded-lg p-3">
      {/* Header */}
      <div className="flex items-center gap-2 mb-2 pb-2 border-b border-slate-800">
        <span className="material-symbols-outlined text-amber-400 text-sm">grid_view</span>
        <span className="text-body-xs font-bold text-slate-400 uppercase tracking-wider">Table Bloat Heatmap</span>
        <span className="text-body-xs text-slate-400 ml-auto font-mono">{tables.length} tables</span>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-3 mb-2">
        {[
          { label: '>70%', color: VIZ_COLORS.critical },
          { label: '>40%', color: VIZ_COLORS.warning },
          { label: '>15%', color: VIZ_COLORS.good },
          { label: '<15%', color: VIZ_COLORS.excellent },
        ].map(({ label, color }) => (
          <div key={label} className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-sm" style={{ backgroundColor: color }} />
            <span className="text-body-xs text-slate-400">{label}</span>
          </div>
        ))}
      </div>

      {/* Heatmap grid */}
      <div
        className="grid gap-1"
        style={{
          gridTemplateColumns: `repeat(${Math.min(Math.ceil(Math.sqrt(displayed.length + 1)), 5)}, 1fr)`,
        }}
      >
        {displayed.map((table) => {
          const color = bloatColor(table.bloat_ratio);
          const opacity = bloatOpacity(table.bloat_ratio);
          const isExpanded = expandedTable === table.name;
          return (
            <button
              key={table.name}
              type="button"
              onClick={() => setExpandedTable(isExpanded ? null : table.name)}
              aria-label={`${table.name}: ${(table.bloat_ratio * 100).toFixed(1)}% bloat`}
              aria-expanded={isExpanded}
              className="group relative rounded border p-2 text-left transition-colors hover:border-slate-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-duck-accent"
              style={{
                backgroundColor: `${color}${Math.round(opacity * 25).toString(16).padStart(2, '0')}`,
                borderColor: `${color}30`,
              }}
            >
              {/* Tooltip (visible on hover or when expanded) */}
              <div className={`absolute left-1/2 -translate-x-1/2 bottom-full mb-1 z-10 ${isExpanded ? 'block' : 'hidden group-hover:block'}`}>
                <div className="bg-slate-900 border border-slate-700 rounded px-2 py-1 shadow-lg whitespace-nowrap">
                  <p className="text-body-xs text-white font-mono">{table.name}</p>
                  <p className="text-body-xs text-slate-400">
                    Bloat: {(table.bloat_ratio * 100).toFixed(1)}% | Dead: {formatTuples(table.dead_tuples)} | Size: {formatSize(table.size_mb)}
                  </p>
                </div>
              </div>

              <p className="text-body-xs text-slate-300 font-mono truncate">{table.name}</p>
              <p className="text-body-xs font-bold font-mono" style={{ color }}>
                {(table.bloat_ratio * 100).toFixed(0)}%
              </p>
              <p className="text-chrome text-slate-400">
                {formatTuples(table.dead_tuples)} dead
              </p>
            </button>
          );
        })}
      </div>

      {tables.length > 20 && !showAll && (
        <button
          onClick={() => setShowAll(true)}
          className="text-body-xs text-duck-accent hover:text-amber-300 mt-2 transition-colors"
        >
          Show all {tables.length} tables
        </button>
      )}

      {/* Summary */}
      <p className="text-body-xs text-slate-400 mt-2">
        {sorted.filter((t) => t.bloat_ratio > 0.4).length} of {sorted.length} tables above 40% bloat
      </p>
    </div>
  );
};

export default TableBloatHeatmap;
