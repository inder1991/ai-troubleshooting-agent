import React from 'react';
import { Loader2, CheckCircle, AlertCircle } from 'lucide-react';

interface ProgressStage {
  stage: 'validation' | 'review' | 'assessment' | 'staging';
  message: string;
  status: 'pending' | 'in_progress' | 'complete' | 'error';
}

interface Agent3ProgressProps {
  currentStage: string;
  stages: ProgressStage[];
}

const STAGE_LABELS = {
  validation: 'Static Validation',
  review: 'Peer Review',
  assessment: 'Impact Assessment',
  staging: 'PR Staging'
};

const STAGE_ICONS = {
  validation: '🔍',
  review: '👥',
  assessment: '📊',
  staging: '🌳'
};

export const Agent3ProgressCard: React.FC<Agent3ProgressProps> = ({
  currentStage,
  stages
}) => {
  const getStageStatus = (stageName: string) => {
    const stage = stages.find(s => s.stage === stageName);
    return stage?.status || 'pending';
  };

  const renderStageIcon = (stageName: string) => {
    const status = getStageStatus(stageName);
    
    switch (status) {
      case 'complete':
        return <CheckCircle size={12} className="text-emerald-400" />;
      case 'in_progress':
        return <Loader2 size={12} className="text-blue-400 animate-spin" />;
      case 'error':
        return <AlertCircle size={12} className="text-red-400" />;
      default:
        return <div className="w-3 h-3 rounded-full border-2 border-slate-700" />;
    }
  };

  return (
    <div className="border border-slate-800 rounded bg-slate-950/40 p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center gap-2">
        <Loader2 size={14} className="text-purple-400 animate-spin" />
        <span className="text-[10px] font-bold text-purple-400 uppercase tracking-widest">
          Agent 3: Phase 1 - Verification
        </span>
      </div>

      {/* Progress Stages */}
      <div className="space-y-3">
        {Object.entries(STAGE_LABELS).map(([key, label]) => {
          const status = getStageStatus(key);
          const stage = stages.find(s => s.stage === key);
          
          return (
            <div
              key={key}
              className={`flex items-start gap-3 transition-all ${
                status === 'in_progress' ? 'opacity-100' : 
                status === 'complete' ? 'opacity-60' : 
                'opacity-30'
              }`}
            >
              <div className="mt-0.5">
                {renderStageIcon(key)}
              </div>
              
              <div className="flex-1 space-y-1">
                <div className="flex items-center gap-2">
                  <span className="text-[9px] font-mono text-slate-400">
                    {STAGE_ICONS[key as keyof typeof STAGE_ICONS]} {label}
                  </span>
                  {status === 'in_progress' && (
                    <span className="text-[8px] text-blue-400 animate-pulse">
                      In Progress...
                    </span>
                  )}
                </div>
                
                {stage?.message && (
                  <div className="text-[8px] text-slate-600">
                    {stage.message}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Progress Bar */}
      <div className="pt-3 border-t border-slate-800">
        <div className="flex justify-between items-center mb-2">
          <span className="text-[8px] text-slate-600 uppercase">Progress</span>
          <span className="text-[8px] text-slate-500">
            {stages.filter(s => s.status === 'complete').length} / {Object.keys(STAGE_LABELS).length}
          </span>
        </div>
        <div className="h-1 bg-slate-900 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-purple-600 to-blue-600 transition-all duration-500"
            style={{
              width: `${(stages.filter(s => s.status === 'complete').length / Object.keys(STAGE_LABELS).length) * 100}%`
            }}
          />
        </div>
      </div>
    </div>
  );
};