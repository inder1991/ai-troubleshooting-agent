import React, { useEffect, useState } from 'react';
import { fetchAddressBlockUtilization } from '../../services/api';

interface Props {
  blockId: string;
}

interface BlockSegment {
  cidr: string;
  name: string;
  utilization_pct: number;
  size: number;
}

function utilizationGradient(pct: number): string {
  if (pct >= 80) return 'bg-red-500';
  if (pct >= 50) return 'bg-amber-500';
  return 'bg-emerald-500';
}

export default function IPAMAddressSpaceMap({ blockId }: Props) {
  const [data, setData] = useState<{ block_cidr: string; total_hosts: number; subnets: BlockSegment[] } | null>(null);
  const [loading, setLoading] = useState(true);
  const [hovered, setHovered] = useState<BlockSegment | null>(null);

  useEffect(() => {
    setLoading(true);
    fetchAddressBlockUtilization(blockId)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [blockId]);

  if (loading) {
    return <div className="text-center text-slate-400 py-8 text-sm">Loading address space map...</div>;
  }
  if (!data) {
    return <div className="text-center text-slate-400 py-8 text-sm">No data available.</div>;
  }

  const totalSize = data.total_hosts || 1;
  const subnets = data.subnets || [];
  const allocatedSize = subnets.reduce((sum, s) => sum + s.size, 0);
  const freeSize = totalSize - allocatedSize;
  const freePct = (freeSize / totalSize) * 100;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-200">
          Address Space: {data.block_cidr}
        </h3>
        <span className="text-xs text-slate-400">
          {allocatedSize.toLocaleString()} / {totalSize.toLocaleString()} allocated ({Math.round((allocatedSize / totalSize) * 100)}%)
        </span>
      </div>

      {/* Stacked bar */}
      <div className="flex h-10 rounded-lg overflow-hidden border border-[#3d3528]">
        {subnets.map((seg, i) => {
          const widthPct = (seg.size / totalSize) * 100;
          if (widthPct < 0.5) return null;
          return (
            <div
              key={i}
              className={`${utilizationGradient(seg.utilization_pct)} flex items-center justify-center text-xs text-white font-medium cursor-pointer transition-opacity hover:opacity-80 border-r border-black/20`}
              style={{ width: `${widthPct}%` }}
              onMouseEnter={() => setHovered(seg)}
              onMouseLeave={() => setHovered(null)}
              title={`${seg.cidr} - ${seg.name || 'unnamed'} (${seg.utilization_pct}%)`}
            >
              {widthPct > 8 ? seg.cidr.split('/')[1] && `/${seg.cidr.split('/')[1]}` : ''}
            </div>
          );
        })}
        {freePct > 0.5 && (
          <div
            className="bg-slate-800 flex items-center justify-center text-xs text-slate-400"
            style={{ width: `${freePct}%` }}
          >
            {freePct > 10 ? 'Free' : ''}
          </div>
        )}
      </div>

      {/* Hover detail */}
      {hovered && (
        <div className="flex items-center gap-4 px-3 py-2 bg-[#1a1814] border border-[#3d3528] rounded text-xs">
          <span className="font-mono text-amber-300">{hovered.cidr}</span>
          <span className="text-slate-400">{hovered.name || 'unnamed'}</span>
          <span className="ml-auto text-slate-300">{hovered.utilization_pct}% utilized</span>
          <span className="text-slate-400">{hovered.size.toLocaleString()} hosts</span>
        </div>
      )}

      {/* Subnet list */}
      <div className="space-y-1">
        {subnets.map((seg, i) => (
          <div key={i} className="flex items-center gap-3 text-xs">
            <div className={`w-3 h-3 rounded-sm ${utilizationGradient(seg.utilization_pct)}`} />
            <span className="font-mono text-slate-300 w-32">{seg.cidr}</span>
            <span className="text-slate-400 flex-1 truncate">{seg.name || '-'}</span>
            <div className="w-16 h-1.5 bg-slate-700 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full ${utilizationGradient(seg.utilization_pct)}`}
                style={{ width: `${Math.min(seg.utilization_pct, 100)}%` }}
              />
            </div>
            <span className="text-slate-400 w-8 text-right">{seg.utilization_pct}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}
