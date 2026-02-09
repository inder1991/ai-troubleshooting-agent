import React from 'react';
import { TrendingUp, AlertTriangle, Shield, Lock, Code } from 'lucide-react';

interface ImpactAssessmentProps {
  data: {
    regression_risk?: 'Low' | 'Medium' | 'High';
    affected_functions?: string[];
    side_effects?: string[];
    security_review?: string;
    diff_lines?: number;
    analysis: string;
    confidence: number;
  };
}

export const ImpactAssessmentCard: React.FC<ImpactAssessmentProps> = ({ data }) => {
  const getRiskColor = (risk: string) => {
    switch (risk) {
      case 'Low': return 'text-emerald-400 bg-emerald-950/20 border-emerald-900/30';
      case 'Medium': return 'text-yellow-400 bg-yellow-950/20 border-yellow-900/30';
      case 'High': return 'text-red-400 bg-red-950/20 border-red-900/30';
      default: return 'text-slate-400 bg-slate-950/20 border-slate-900/30';
    }
  };

  const getRiskIcon = (risk: string) => {
    switch (risk) {
      case 'Low': return '🟢';
      case 'Medium': return '🟡';
      case 'High': return '🔴';
      default: return '⚪';
    }
  };

  return (
    <div className="border border-slate-800 rounded bg-slate-950/40 p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center gap-2">
        <TrendingUp size={14} className="text-purple-400" />
        <span className="text-[10px] font-bold text-purple-400 uppercase tracking-widest">
          Impact Assessment
        </span>
      </div>

      {/* Regression Risk */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Shield size={12} className="text-slate-500" />
            <span className="text-[9px] text-slate-500 uppercase font-bold">Regression Risk</span>
          </div>
          <div className={`text-[10px] font-bold px-2 py-1 rounded border ${getRiskColor(data.regression_risk)}`}>
            {getRiskIcon(data.regression_risk)} {data.regression_risk}
          </div>
        </div>
        
        <div className="text-[8px] text-slate-600 bg-slate-950 border border-slate-900 rounded p-2">
          Based on code complexity, affected functions, and change scope
        </div>
      </div>

      {/* Affected Functions */}
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <Code size={12} className="text-slate-500" />
          <span className="text-[9px] text-slate-500 uppercase font-bold">
            Affected Functions ({data.affected_functions.length})
          </span>
        </div>
        
        {data.affected_functions.length > 0 ? (
          <div className="space-y-1">
            {data.affected_functions.slice(0, 5).map((func, idx) => (
              <div key={idx} className="flex items-center gap-2 bg-slate-950 border border-slate-900 rounded p-2">
                <span className="text-[8px] font-mono text-blue-400">{func}</span>
              </div>
            ))}
            {data.affected_functions.length > 5 && (
              <div className="text-[7px] text-slate-600 italic pl-2">
                ... and {data.affected_functions.length - 5} more functions
              </div>
            )}
          </div>
        ) : (
          <div className="text-[8px] text-slate-600 bg-slate-950 border border-slate-900 rounded p-2">
            No specific functions identified
          </div>
        )}
      </div>

      {/* Side Effects */}
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <AlertTriangle size={12} className="text-slate-500" />
          <span className="text-[9px] text-slate-500 uppercase font-bold">
            Potential Side Effects ({data.side_effects.length})
          </span>
        </div>
        
        {data.side_effects.length > 0 ? (
          <div className="space-y-1.5">
            {data.side_effects.map((effect, idx) => (
              <div key={idx} className="flex items-start gap-2 bg-yellow-950/10 border border-yellow-900/30 rounded p-2">
                <AlertTriangle size={10} className="text-yellow-500 mt-0.5 flex-shrink-0" />
                <span className="text-[8px] text-slate-400">{effect}</span>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-[8px] text-emerald-400 bg-emerald-950/20 border border-emerald-900/30 rounded p-2">
            ✅ No significant side effects identified
          </div>
        )}
      </div>

      {/* Security Review */}
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <Lock size={12} className="text-slate-500" />
          <span className="text-[9px] text-slate-500 uppercase font-bold">Security Review</span>
        </div>
        
        <div className="text-[8px] text-slate-400 bg-slate-950 border border-slate-900 rounded p-3">
          {data.security_review}
        </div>
      </div>

      {/* Code Change Stats */}
      <div className="pt-3 border-t border-slate-800">
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-slate-950 border border-slate-900 rounded p-3 text-center">
            <div className="text-[8px] text-slate-600 uppercase mb-1">Diff Size</div>
            <div className="text-[14px] font-bold text-blue-400">{data.diff_lines}</div>
            <div className="text-[7px] text-slate-600">lines changed</div>
          </div>
          
          <div className="bg-slate-950 border border-slate-900 rounded p-3 text-center">
            <div className="text-[8px] text-slate-600 uppercase mb-1">Impact Scope</div>
            <div className="text-[14px] font-bold text-purple-400">{data.affected_functions.length}</div>
            <div className="text-[7px] text-slate-600">functions</div>
          </div>
        </div>
      </div>
    </div>
  );
};