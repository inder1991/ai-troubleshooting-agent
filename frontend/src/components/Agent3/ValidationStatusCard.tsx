import React from 'react';
import { CheckCircle, AlertCircle, XCircle, Shield } from 'lucide-react';

interface ValidationStatusProps {
  data: {
    syntax: {
      valid: boolean;
      error?: string;
    };
    linting: {
      passed: boolean;
      issues: {
        errors?: any[];
        warnings?: any[];
      };
    };
    imports: {
      valid: boolean;
      missing?: string[];
    };
    agent2_approved?: boolean;
    agent2_confidence?: number;
    passed: boolean;
  };
}

export const ValidationStatusCard: React.FC<ValidationStatusProps> = ({ data }) => {
  const renderCheckIcon = (passed: boolean) => {
    if (passed) {
      return <CheckCircle size={12} className="text-emerald-400" />;
    }
    return <XCircle size={12} className="text-red-400" />;
  };

  return (
    <div className="border border-slate-800 rounded bg-slate-950/40 p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Shield size={14} className="text-blue-400" />
          <span className="text-[10px] font-bold text-blue-400 uppercase tracking-widest">
            Validation Details
          </span>
        </div>
        <div className={`text-[10px] font-bold ${data.passed ? 'text-emerald-400' : 'text-red-400'}`}>
          {data.passed ? '✅ PASSED' : '❌ FAILED'}
        </div>
      </div>

      {/* Syntax Check */}
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          {renderCheckIcon(data.syntax.valid)}
          <span className="text-[9px] font-mono text-slate-400">Syntax Validation</span>
        </div>
        {!data.syntax.valid && data.syntax.error && (
          <div className="ml-5 pl-3 border-l-2 border-red-500/30">
            <div className="text-[8px] text-red-400 bg-red-950/20 border border-red-900/30 rounded p-2">
              {data.syntax.error}
            </div>
          </div>
        )}
      </div>

      {/* Linting Check */}
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          {renderCheckIcon(data.linting.passed)}
          <span className="text-[9px] font-mono text-slate-400">Linting Check</span>
        </div>
        
        {data.linting.issues.errors && data.linting.issues.errors.length > 0 && (
          <div className="ml-5 pl-3 border-l-2 border-red-500/30 space-y-1">
            <div className="text-[8px] text-slate-600 uppercase font-bold">Errors:</div>
            {data.linting.issues.errors.slice(0, 3).map((error: any, idx: number) => (
              <div key={idx} className="text-[8px] text-red-400 bg-red-950/20 border border-red-900/30 rounded p-2">
                {error.message || JSON.stringify(error)}
              </div>
            ))}
          </div>
        )}
        
        {data.linting.issues.warnings && data.linting.issues.warnings.length > 0 && (
          <div className="ml-5 pl-3 border-l-2 border-yellow-500/30 space-y-1">
            <div className="text-[8px] text-slate-600 uppercase font-bold">
              Warnings ({data.linting.issues.warnings.length}):
            </div>
            {data.linting.issues.warnings.slice(0, 2).map((warning: any, idx: number) => (
              <div key={idx} className="text-[8px] text-yellow-400 bg-yellow-950/20 border border-yellow-900/30 rounded p-2">
                {warning.message || JSON.stringify(warning)}
              </div>
            ))}
            {data.linting.issues.warnings.length > 2 && (
              <div className="text-[7px] text-slate-600 italic">
                ... and {data.linting.issues.warnings.length - 2} more
              </div>
            )}
          </div>
        )}
      </div>

      {/* Import Check */}
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          {renderCheckIcon(data.imports.valid)}
          <span className="text-[9px] font-mono text-slate-400">Import Validation</span>
        </div>
        {!data.imports.valid && data.imports.missing && data.imports.missing.length > 0 && (
          <div className="ml-5 pl-3 border-l-2 border-yellow-500/30">
            <div className="text-[8px] text-slate-600 uppercase font-bold mb-1">Missing:</div>
            <div className="space-y-1">
              {data.imports.missing.map((imp, idx) => (
                <div key={idx} className="text-[8px] font-mono text-yellow-400">
                  • {imp}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Agent 2 Review */}
      {typeof data.agent2_approved !== 'undefined' && (
        <div className="pt-3 border-t border-slate-800 space-y-2">
          <div className="flex items-center gap-2">
            {renderCheckIcon(data.agent2_approved)}
            <span className="text-[9px] font-mono text-slate-400">Agent 2 Peer Review</span>
          </div>
          
          {typeof data.agent2_confidence !== 'undefined' && (
            <div className="ml-5 flex items-center gap-2">
              <span className="text-[8px] text-slate-600">Confidence:</span>
              <div className="flex-1 h-1.5 bg-slate-900 rounded-full overflow-hidden">
                <div
                  className={`h-full transition-all ${
                    data.agent2_confidence >= 0.8 ? 'bg-emerald-500' :
                    data.agent2_confidence >= 0.6 ? 'bg-yellow-500' :
                    'bg-red-500'
                  }`}
                  style={{ width: `${data.agent2_confidence * 100}%` }}
                />
              </div>
              <span className="text-[8px] font-bold text-slate-400">
                {(data.agent2_confidence * 100).toFixed(0)}%
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
};