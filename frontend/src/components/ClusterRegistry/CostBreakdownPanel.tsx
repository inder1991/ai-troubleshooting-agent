import React from 'react';
import type { ClusterCostSummaryDTO } from '../../types';

interface CostBreakdownPanelProps {
  cost: ClusterCostSummaryDTO;
}

const CostBreakdownPanel: React.FC<CostBreakdownPanelProps> = ({ cost }) => {
  const savingsPct = cost.current_monthly_cost > 0
    ? ((cost.projected_savings_usd / cost.current_monthly_cost) * 100).toFixed(1)
    : '0';

  return (
    <div className="bg-[#1e1b15] border border-[#3d3528]/50 rounded-lg p-5">
      <h3 className="text-sm font-display font-bold text-slate-200 flex items-center gap-2 mb-4">
        <span className="material-symbols-outlined text-[#e09f3e] text-[18px]">payments</span>
        Cost Breakdown
      </h3>

      {/* Before / After summary */}
      <div className="grid grid-cols-3 gap-4 mb-5">
        <div className="bg-[#13110d] rounded-lg p-3 text-center">
          <div className="text-body-xs text-slate-400 mb-1">Current</div>
          <div className="text-lg font-bold text-slate-200">
            ${cost.current_monthly_cost.toLocaleString(undefined, { maximumFractionDigits: 0 })}
          </div>
          <div className="text-body-xs text-slate-400">/month</div>
        </div>
        <div className="bg-[#13110d] rounded-lg p-3 text-center">
          <div className="text-body-xs text-slate-400 mb-1">Projected</div>
          <div className="text-lg font-bold text-green-400">
            ${cost.projected_monthly_cost.toLocaleString(undefined, { maximumFractionDigits: 0 })}
          </div>
          <div className="text-body-xs text-slate-400">/month</div>
        </div>
        <div className="bg-[#13110d] rounded-lg p-3 text-center">
          <div className="text-body-xs text-slate-400 mb-1">Savings</div>
          <div className="text-lg font-bold text-[#e09f3e]">
            ${cost.projected_savings_usd.toLocaleString(undefined, { maximumFractionDigits: 0 })}
          </div>
          <div className="text-body-xs text-[#e09f3e]/70">{savingsPct}% reduction</div>
        </div>
      </div>

      {/* Idle capacity bars */}
      <div className="mb-5">
        <div className="text-body-xs uppercase tracking-wider text-slate-400 font-medium mb-3">Idle Capacity</div>
        <div className="space-y-3">
          {/* CPU bar */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <span className="text-body-xs text-slate-400">CPU</span>
              <span className={`text-body-xs font-medium ${cost.idle_cpu_pct > 40 ? 'text-[#e09f3e]' : 'text-slate-300'}`}>
                {cost.idle_cpu_pct.toFixed(1)}% idle
              </span>
            </div>
            <div className="h-2 bg-[#13110d] rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{
                  width: `${Math.min(cost.idle_cpu_pct, 100)}%`,
                  background: cost.idle_cpu_pct > 40 ? '#e09f3e' : '#22c55e',
                }}
              />
            </div>
          </div>

          {/* Memory bar */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <span className="text-body-xs text-slate-400">Memory</span>
              <span className={`text-body-xs font-medium ${cost.idle_memory_pct > 40 ? 'text-[#e09f3e]' : 'text-slate-300'}`}>
                {cost.idle_memory_pct.toFixed(1)}% idle
              </span>
            </div>
            <div className="h-2 bg-[#13110d] rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{
                  width: `${Math.min(cost.idle_memory_pct, 100)}%`,
                  background: cost.idle_memory_pct > 40 ? '#e09f3e' : '#22c55e',
                }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Instance breakdown table */}
      {cost.instance_breakdown.length > 0 && (
        <div className="mb-5">
          <div className="text-body-xs uppercase tracking-wider text-slate-400 font-medium mb-2">Instance Types</div>
          <div className="overflow-x-auto">
            <table className="w-full text-body-xs">
              <thead>
                <tr className="text-slate-400 border-b border-[#3d3528]/30">
                  <th className="text-left py-1.5 font-medium">Type</th>
                  <th className="text-right py-1.5 font-medium">Count</th>
                  <th className="text-right py-1.5 font-medium">Unit Cost</th>
                  <th className="text-right py-1.5 font-medium">Total</th>
                </tr>
              </thead>
              <tbody>
                {cost.instance_breakdown.map((inst, i) => (
                  <tr key={i} className="border-b border-[#3d3528]/15">
                    <td className="py-1.5 text-slate-300 font-mono">{inst.instance_type}</td>
                    <td className="py-1.5 text-right text-slate-400">{inst.count}</td>
                    <td className="py-1.5 text-right text-slate-400">${inst.unit_cost.toFixed(2)}</td>
                    <td className="py-1.5 text-right text-slate-200">${inst.total_cost.toFixed(0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Top idle namespaces */}
      {cost.namespace_costs.length > 0 && (
        <div>
          <div className="text-body-xs uppercase tracking-wider text-slate-400 font-medium mb-2">Top Namespaces by Cost</div>
          <div className="space-y-1.5">
            {cost.namespace_costs.slice(0, 8).map((ns, i) => (
              <div key={i} className="flex items-center gap-2">
                <span className="text-body-xs text-slate-400 font-mono flex-1 truncate">{ns.namespace}</span>
                <span className="text-body-xs text-slate-400">{ns.pod_count} pods</span>
                <span className="text-body-xs text-slate-300 font-medium w-16 text-right">
                  ${ns.estimated_cost.toFixed(0)}
                </span>
                <span className="text-body-xs text-slate-400 w-10 text-right">{ns.cost_pct.toFixed(1)}%</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default CostBreakdownPanel;
