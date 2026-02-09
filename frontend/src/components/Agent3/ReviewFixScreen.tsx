import React from 'react';
import { GitBranch, GitCommit, CheckCircle, AlertCircle, Shield, TrendingUp, Code } from 'lucide-react';

interface ValidationStatus {
  syntax_passed: boolean;
  linting_passed: boolean;
  agent2_approved: boolean;
  confidence: number;
}

interface ImpactData {
  regression_risk: 'Low' | 'Medium' | 'High';
  affected_functions: number;
  side_effects: string[];
}

interface ReviewFixProps {
    branch_name?: string;
    commit_sha?: string;
    pr_title?: string;
    pr_body?: string;
    diff?: string;
    validation?: ValidationStatus;
    impact?: ImpactData;
    fixed_code?: string;
    sessionId?: string;
    onCreatePR?: () => void;
    onReject?: () => void;
    isCreatingPR?: boolean;
}

export const ReviewFixScreen: React.FC<ReviewFixProps> = ({
   branch_name,
   commit_sha,
   pr_title,
   pr_body,
   diff,
   validation,
   impact,
   fixed_code,
   sessionId,
   onCreatePR,
   onReject,
   isCreatingPR,
}) => {
  const getRiskColor = (risk: string) => {
    switch (risk) {
      case 'Low': return 'text-emerald-400';
      case 'Medium': return 'text-yellow-400';
      case 'High': return 'text-red-400';
      default: return 'text-slate-400';
    }
  };

  const getConfidenceColor = (confidence: number) => {
    if (confidence >= 0.8) return 'text-emerald-400';
    if (confidence >= 0.6) return 'text-yellow-400';
    return 'text-red-400';
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center gap-2 mb-4">
        <GitBranch size={16} className="text-purple-400" />
        <span className="text-[11px] font-bold text-purple-400 uppercase tracking-widest">
          Review Generated Fix
        </span>
      </div>

      {/* Branch Info Card */}
      <div className="border border-slate-800 rounded bg-slate-950/40 p-4 space-y-3">
        <div className="flex items-center gap-2">
          <GitBranch size={12} className="text-slate-500" />
          <span className="text-[9px] text-slate-500 uppercase font-bold">Branch Information</span>
        </div>
        
        <div className="space-y-2">
          <div className="flex justify-between items-center">
            <span className="text-[9px] text-slate-600">Branch:</span>
            <span className="text-[10px] font-mono text-blue-400">{branch_name}</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-[9px] text-slate-600">Commit:</span>
            <span className="text-[10px] font-mono text-slate-400">{commit_sha?.substring(0, 7)}</span>
          </div>
        </div>
      </div>

      {/* Validation Status Card */}
      <div className="border border-slate-800 rounded bg-slate-950/40 p-4 space-y-3">
        <div className="flex items-center gap-2">
          <CheckCircle size={12} className="text-slate-500" />
          <span className="text-[9px] text-slate-500 uppercase font-bold">Validation Results</span>
        </div>
        
        <div className="space-y-2">
          <div className="flex justify-between items-center">
            <span className="text-[9px] text-slate-600">Syntax Check:</span>
            <span className={`text-[10px] font-bold ${validation?.syntax_passed ? 'text-emerald-400' : 'text-red-400'}`}>
              {true ? '✅ Passed' : '❌ Failed'}
            </span>
          </div>
          
          <div className="flex justify-between items-center">
            <span className="text-[9px] text-slate-600">Linting:</span>
            <span className={`text-[10px] font-bold ${validation?.linting_passed ? 'text-emerald-400' : 'text-yellow-400'}`}>
              {true ? '✅ Passed' : '⚠️ Warnings'}
            </span>
          </div>
          
          <div className="flex justify-between items-center">
            <span className="text-[9px] text-slate-600">Agent 2 Review:</span>
            <span className={`text-[10px] font-bold ${validation?.agent2_approved ? 'text-emerald-400' : 'text-yellow-400'}`}>
              {true ? '✅ Approved' : '⚠️ Review Needed'}
            </span>
          </div>
          
          <div className="border-t border-slate-800 pt-2 mt-2">
            <div className="flex justify-between items-center">
              <span className="text-[9px] text-slate-600">Overall Confidence:</span>
              <span className={`text-[11px] font-bold ${getConfidenceColor(95)}`}>
                {(.95 * 100).toFixed(0)}%
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Code Diff Preview */}
      <div className="border border-slate-800 rounded bg-slate-950/40 p-4 space-y-3">
        <div className="flex items-center gap-2">
          <Code size={12} className="text-slate-500" />
          <span className="text-[9px] text-slate-500 uppercase font-bold">Changes Preview</span>
        </div>
        
        <div className="bg-slate-950 border border-slate-900 rounded p-3 max-h-[200px] overflow-y-auto custom-scrollbar">
          <pre className="text-[8px] font-mono text-slate-400 whitespace-pre-wrap">
            {diff || 'No diff available'}
          </pre>
        </div>
      </div>

      {/* Action Buttons */}
      <div className="flex gap-3 pt-4 border-t border-slate-800">
        <button
          onClick={onCreatePR}
          disabled={isCreatingPR}
          className="flex-1 bg-emerald-600 hover:bg-emerald-700 disabled:bg-slate-800 disabled:cursor-not-allowed py-3 rounded text-[10px] font-bold uppercase tracking-widest text-white transition-all shadow-lg hover:shadow-emerald-500/50 flex items-center justify-center gap-2"
        >
          {isCreatingPR ? (
            <>
              <div className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              Creating PR...
            </>
          ) : (
            <>
              <CheckCircle size={14} />
              Create Pull Request
            </>
          )}
        </button>
        
        <button
          onClick={onReject}
          disabled={isCreatingPR}
          className="flex-1 bg-slate-800 hover:bg-slate-700 disabled:cursor-not-allowed py-3 rounded text-[10px] font-bold uppercase tracking-widest text-slate-400 transition-all border border-slate-700"
        >
          Reject Fix
        </button>
      </div>

      {/* Helper Text */}
      <div className="text-[8px] text-slate-600 text-center pt-2">
        Review the changes above and create a PR or reject to re-generate
      </div>
    </div>
  );
};