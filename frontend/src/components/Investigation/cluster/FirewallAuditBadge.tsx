import React, { useState } from 'react';
import type { CausalSearchSpace } from '../../../types';

interface FirewallAuditBadgeProps {
  searchSpace: CausalSearchSpace | null;
}

export default function FirewallAuditBadge({ searchSpace }: FirewallAuditBadgeProps) {
  const [expanded, setExpanded] = useState(false);

  if (!searchSpace) return null;

  const { total_evaluated, total_blocked, total_annotated, blocked_links } = searchSpace;

  return (
    <div className="bg-slate-900/40 border border-slate-700/30 rounded-lg overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full px-3 py-2 flex items-center gap-2 text-left hover:bg-slate-800/30 transition-colors"
      >
        <span className="material-symbols-outlined text-cyan-400 text-base">shield</span>
        <span className="text-xs text-slate-300">Causal Firewall</span>
        <div className="ml-auto flex items-center gap-2 text-[10px] font-mono text-slate-500">
          <span>{total_evaluated} evaluated</span>
          <span className="text-red-400">{total_blocked} blocked</span>
          <span className="text-amber-400">{total_annotated} annotated</span>
        </div>
        <span className="material-symbols-outlined text-slate-500 text-sm">
          {expanded ? 'expand_less' : 'expand_more'}
        </span>
      </button>
      {expanded && blocked_links.length > 0 && (
        <div className="border-t border-slate-700/30 px-3 py-2 space-y-1.5">
          {blocked_links.map((link, i) => (
            <div key={i} className="flex items-start gap-2 text-[10px]">
              <span className="text-red-400 font-mono shrink-0">{link.invariant_id}</span>
              <span className="text-slate-400">{link.invariant_description}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
