import React, { useState } from 'react';
import { PLAN_NODE_COLORS } from '../db-board/constants';

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
  // Check for exact match first
  if (PLAN_NODE_COLORS[nodeType]) return PLAN_NODE_COLORS[nodeType];
  // Fall back to substring matching
  if (nodeType.includes('Seq Scan')) return PLAN_NODE_COLORS['Seq Scan'];
  if (nodeType.includes('Index')) return PLAN_NODE_COLORS['Index Scan'];
  if (nodeType.includes('Sort')) return PLAN_NODE_COLORS['Sort'];
  if (nodeType.includes('Hash')) return PLAN_NODE_COLORS['Hash'];
  if (nodeType.includes('Nested Loop') || nodeType.includes('Merge')) return PLAN_NODE_COLORS['Nested Loop'];
  return PLAN_NODE_COLORS['default'];
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
        <span className="text-[9px] text-slate-400 ml-auto flex items-center gap-2">
          <span>cost={formatCost(plan['Total Cost'])}</span>
          <span>rows={plan['Plan Rows'] ?? '-'}</span>
          {plan['Actual Total Time'] !== undefined && (
            <span className="text-amber-500/70">{plan['Actual Total Time'].toFixed(1)}ms</span>
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

interface EnrichedPlan {
  plan: PlanNode;
  query?: string;
  pid?: number;
  duration_ms?: number;
  user?: string;
}

function isEnrichedPlan(obj: any): obj is EnrichedPlan {
  return obj && typeof obj === 'object' && 'plan' in obj && obj.plan && typeof obj.plan === 'object';
}

function formatMs(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`;
}

function detectWarnings(plan: PlanNode): string[] {
  const warnings: string[] = [];
  const check = (node: PlanNode) => {
    const nodeType = node['Node Type'] || '';
    if (nodeType.includes('Seq Scan') && node['Relation Name']) {
      const filter = node['Filter'] || '';
      const filterCols = filter.match(/\b([a-z_]+)\s*[>=<]/gi) || [];
      if (filterCols.length > 0) {
        warnings.push(`Seq Scan on ${node['Relation Name']} — consider adding index on filtered columns`);
      } else {
        warnings.push(`Seq Scan on ${node['Relation Name']} — full table scan`);
      }
    }
    if (nodeType.includes('Sort') && (node['Plan Rows'] ?? 0) > 10000) {
      warnings.push(`Sorting ${node['Plan Rows']?.toLocaleString()} rows — may spill to disk if work_mem is low`);
    }
    if (node.Plans) node.Plans.forEach(check);
  };
  check(plan);
  return warnings;
}

const ExplainPlanTree: React.FC<{ plan: PlanNode | EnrichedPlan | null }> = ({ plan: rawPlan }) => {
  if (!rawPlan) {
    return (
      <div className="text-center py-4">
        <span className="material-symbols-outlined text-2xl text-slate-700 block mb-1" aria-hidden="true">account_tree</span>
        <p className="text-[10px] text-slate-400">No explain plan available</p>
      </div>
    );
  }

  // Handle both formats: raw PlanNode or enriched {plan, query, pid, ...}
  const enriched = isEnrichedPlan(rawPlan);
  const planNode: PlanNode = enriched ? rawPlan.plan : rawPlan;
  const query = enriched ? rawPlan.query : undefined;
  const pid = enriched ? rawPlan.pid : undefined;
  const durationMs = enriched ? rawPlan.duration_ms : undefined;
  const queryUser = enriched ? rawPlan.user : undefined;

  const warnings = detectWarnings(planNode);

  return (
    <div className="overflow-x-auto">
      {/* Query context header */}
      {query && (
        <div className="mb-3 pb-2 border-b border-duck-border/30">
          <div className="flex items-center gap-2 mb-1.5">
            <span className="material-symbols-outlined text-duck-accent text-sm" aria-hidden="true">query_stats</span>
            <span className="text-[11px] font-display font-bold text-slate-300">
              Query Plan {pid ? `for pid:${pid}` : ''}
              {durationMs ? ` (${formatMs(durationMs)})` : ''}
            </span>
            {queryUser && <span className="text-[9px] text-slate-400 ml-auto">user: {queryUser}</span>}
          </div>
          <pre className="text-[10px] font-mono text-slate-400 leading-relaxed line-clamp-3 whitespace-pre-wrap break-all bg-duck-bg/50 rounded px-2 py-1.5">
            {query}
          </pre>
        </div>
      )}

      {/* Plan tree */}
      <ExplainPlanNode plan={planNode} />

      {/* Warnings */}
      {warnings.length > 0 && (
        <div className="mt-3 pt-2 border-t border-duck-border/30 space-y-1">
          {warnings.map((w, i) => (
            <div key={i} className="flex items-start gap-1.5">
              <span className="material-symbols-outlined text-amber-400 text-[12px] shrink-0 mt-0.5" aria-hidden="true">warning</span>
              <span className="text-[10px] text-amber-400/80">{w}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default ExplainPlanTree;
