import React, { useState, useMemo } from 'react';
import { VIZ_COLORS } from '../db-board/constants';

interface IndexInfo {
  name: string;
  table: string;
  scans: number;
  size_mb: number;
  unused: boolean;
}

interface IndexUsageMatrixProps {
  indexes: IndexInfo[];
}

function scanColor(scans: number, unused: boolean): string {
  if (unused) return VIZ_COLORS.critical;
  if (scans > 10000) return VIZ_COLORS.excellent;
  if (scans > 1000) return VIZ_COLORS.good;
  if (scans > 100) return VIZ_COLORS.warning;
  return VIZ_COLORS.danger;
}

function formatScans(scans: number): string {
  if (scans >= 1_000_000) return `${(scans / 1_000_000).toFixed(1)}M`;
  if (scans >= 1_000) return `${(scans / 1_000).toFixed(1)}K`;
  return String(scans);
}

function formatSize(mb: number): string {
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
  return `${mb.toFixed(1)} MB`;
}

const IndexUsageMatrix: React.FC<IndexUsageMatrixProps> = ({ indexes }) => {
  const [showAll, setShowAll] = useState(false);

  if (indexes.length === 0) {
    return (
      <div className="text-center py-4">
        <span className="material-symbols-outlined text-2xl text-slate-700 block mb-1">list_alt</span>
        <p className="text-[10px] text-slate-400">No index usage data</p>
      </div>
    );
  }

  const sorted = useMemo(() => [...indexes].sort((a, b) => {
    if (a.unused !== b.unused) return a.unused ? -1 : 1;
    return b.scans - a.scans;
  }), [indexes]);

  const displayed = showAll ? sorted : sorted.slice(0, 20);

  const unusedCount = sorted.filter((idx) => idx.unused).length;
  const totalWastedMb = sorted
    .filter((idx) => idx.unused)
    .reduce((sum, idx) => sum + idx.size_mb, 0);

  return (
    <div className="bg-duck-card/30 border border-duck-border rounded-lg p-3">
      {/* Header */}
      <div className="flex items-center gap-2 mb-2 pb-2 border-b border-slate-800">
        <span className="material-symbols-outlined text-emerald-400 text-sm">list_alt</span>
        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Index Usage Matrix</span>
        <span className="text-[9px] text-slate-400 ml-auto font-mono">{indexes.length} indexes</span>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-3 mb-2">
        {[
          { label: '>10K scans', color: VIZ_COLORS.excellent },
          { label: '>1K', color: VIZ_COLORS.good },
          { label: '>100', color: VIZ_COLORS.warning },
          { label: 'Low', color: VIZ_COLORS.danger },
          { label: 'Unused', color: VIZ_COLORS.critical },
        ].map(({ label, color }) => (
          <div key={label} className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-sm" style={{ backgroundColor: color }} />
            <span className="text-[9px] text-slate-400">{label}</span>
          </div>
        ))}
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-slate-800">
              {['Index', 'Table', 'Scans', 'Size', 'Status'].map((h) => (
                <th
                  key={h}
                  className="text-[9px] text-slate-400 uppercase tracking-wider font-medium py-2 md:py-1.5 px-2"
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {displayed.map((idx) => {
              const color = scanColor(idx.scans, idx.unused);
              return (
                <tr
                  key={idx.name}
                  className="border-b border-slate-800/50 hover:bg-duck-card/20 transition-colors"
                  style={
                    idx.unused
                      ? { backgroundColor: '#ef444408' }
                      : undefined
                  }
                >
                  {/* Index name */}
                  <td className="py-1.5 px-2">
                    <span className="text-[10px] font-mono text-slate-300">{idx.name}</span>
                  </td>
                  {/* Table */}
                  <td className="py-1.5 px-2">
                    <span className="text-[10px] font-mono text-slate-400">{idx.table}</span>
                  </td>
                  {/* Scans with color-coded bar */}
                  <td className="py-1.5 px-2">
                    <div className="flex items-center gap-2">
                      <span
                        className="text-[10px] font-mono font-bold"
                        style={{ color }}
                      >
                        {formatScans(idx.scans)}
                      </span>
                    </div>
                  </td>
                  {/* Size */}
                  <td className="py-1.5 px-2">
                    <span className="text-[10px] font-mono text-slate-400">
                      {formatSize(idx.size_mb)}
                    </span>
                  </td>
                  {/* Status badge */}
                  <td className="py-1.5 px-2">
                    {idx.unused ? (
                      <span
                        className="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-bold"
                        style={{
                          backgroundColor: '#ef444415',
                          color: '#ef4444',
                          border: '1px solid #ef444430',
                        }}
                      >
                        UNUSED
                      </span>
                    ) : (
                      <span
                        className="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-bold"
                        style={{
                          backgroundColor: `${color}15`,
                          color,
                          border: `1px solid ${color}30`,
                        }}
                      >
                        ACTIVE
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {indexes.length > 20 && !showAll && (
        <button
          onClick={() => setShowAll(true)}
          className="text-[10px] text-duck-accent hover:text-amber-300 mt-2 transition-colors"
        >
          Show all {indexes.length} indexes
        </button>
      )}

      {/* Summary */}
      {unusedCount > 0 && (
        <p className="text-[10px] text-red-400/80 mt-2">
          {unusedCount} unused index{unusedCount !== 1 ? 'es' : ''} wasting {formatSize(totalWastedMb)}
        </p>
      )}
    </div>
  );
};

export default IndexUsageMatrix;
