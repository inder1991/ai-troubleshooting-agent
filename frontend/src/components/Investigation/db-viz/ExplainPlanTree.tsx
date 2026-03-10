import React, { useState } from 'react';

interface PlanNode {
  'Node Type': string;
  'Relation Name'?: string;
  'Startup Cost'?: number;
  'Total Cost'?: number;
  'Plan Rows'?: number;
  'Plan Width'?: number;
  'Actual Startup Time'?: number;
  'Actual Total Time'?: number;
  'Actual Rows'?: number;
  'Actual Loops'?: number;
  'Index Name'?: string;
  'Filter'?: string;
  Plans?: PlanNode[];
  [key: string]: any;
}

interface ExplainPlanTreeProps {
  plan: PlanNode;
  depth?: number;
}

function nodeColor(nodeType: string): string {
  if (nodeType.includes('Seq Scan')) return '#ef4444';
  if (nodeType.includes('Index')) return '#10b981';
  if (nodeType.includes('Sort')) return '#f59e0b';
  if (nodeType.includes('Hash')) return '#8b5cf6';
  if (nodeType.includes('Nested Loop') || nodeType.includes('Merge')) return '#06b6d4';
  return '#64748b';
}

function formatCost(cost?: number): string {
  if (cost === undefined) return '-';
  if (cost > 1000000) return `${(cost / 1000000).toFixed(1)}M`;
  if (cost > 1000) return `${(cost / 1000).toFixed(1)}K`;
  return cost.toFixed(1);
}

const ExplainPlanNode: React.FC<ExplainPlanTreeProps> = ({ plan, depth = 0 }) => {
  const [expanded, setExpanded] = useState(depth < 3);
  const hasChildren = plan.Plans && plan.Plans.length > 0;
  const color = nodeColor(plan['Node Type']);

  return (
    <div style={{ marginLeft: depth > 0 ? 16 : 0 }}>
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-start gap-2 w-full text-left py-1 hover:bg-duck-card/20 rounded px-1 transition-colors group"
      >
        {/* Expand icon */}
        {hasChildren ? (
          <span className={`material-symbols-outlined text-xs text-slate-500 mt-0.5 transition-transform ${expanded ? 'rotate-90' : ''}`}>
            chevron_right
          </span>
        ) : (
          <span className="w-4" />
        )}

        {/* Node type badge */}
        <span
          className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold"
          style={{
            backgroundColor: `${color}15`,
            color,
            border: `1px solid ${color}30`,
          }}
        >
          {plan['Node Type']}
        </span>

        {/* Relation name */}
        {plan['Relation Name'] && (
          <span className="text-[11px] text-slate-300 font-mono">
            on {plan['Relation Name']}
          </span>
        )}

        {/* Index name */}
        {plan['Index Name'] && (
          <span className="text-[10px] text-emerald-400/70 font-mono">
            using {plan['Index Name']}
          </span>
        )}

        {/* Cost / Rows */}
        <span className="text-[9px] text-slate-600 ml-auto flex items-center gap-2">
          <span>cost={formatCost(plan['Total Cost'])}</span>
          <span>rows={plan['Plan Rows'] ?? '-'}</span>
          {plan['Actual Total Time'] !== undefined && (
            <span className="text-cyan-500/70">{plan['Actual Total Time'].toFixed(1)}ms</span>
          )}
        </span>
      </button>

      {/* Filter line */}
      {expanded && plan['Filter'] && (
        <div className="ml-8 text-[9px] text-slate-500 font-mono mb-0.5">
          Filter: {plan['Filter']}
        </div>
      )}

      {/* Children */}
      {expanded && hasChildren && (
        <div className="border-l border-slate-800 ml-2">
          {plan.Plans!.map((child, i) => (
            <ExplainPlanNode key={i} plan={child} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  );
};

const ExplainPlanTree: React.FC<{ plan: PlanNode | null }> = ({ plan }) => {
  if (!plan) {
    return (
      <div className="text-center py-4">
        <span className="material-symbols-outlined text-2xl text-slate-700 block mb-1">account_tree</span>
        <p className="text-[10px] text-slate-600">No explain plan available</p>
      </div>
    );
  }

  return (
    <div className="bg-duck-card/30 border border-duck-border rounded-lg p-3 font-mono text-xs overflow-x-auto">
      <div className="flex items-center gap-2 mb-2 pb-2 border-b border-slate-800">
        <span className="material-symbols-outlined text-violet-400 text-sm">account_tree</span>
        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Query Plan</span>
      </div>
      <ExplainPlanNode plan={plan} />
    </div>
  );
};

export default ExplainPlanTree;
