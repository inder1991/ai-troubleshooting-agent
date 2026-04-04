import React, { useState } from 'react';
import { StatusBadge } from '../shared/StatusBadge';
import type { SystemStatus } from '../shared/StatusBadge';
import ClusterDossierExport from './ClusterDossierExport';
import LLMCostBadge from './LLMCostBadge';
import AgentCostBreakdown from './AgentCostBreakdown';

interface ClusterHeaderProps {
  sessionId: string;
  confidence: number;
  platformHealth: string;
  wsConnected: boolean;
  onGoHome: () => void;
  phase?: string;
}

const healthToStatus = (health: string): SystemStatus =>
  !health ? 'in_progress'
    : health === 'HEALTHY' ? 'healthy'
    : health === 'DEGRADED' ? 'degraded'
    : health === 'CRITICAL' ? 'critical'
    : health === 'PARTIAL_TIMEOUT' ? 'degraded'
    : 'unknown';

const ClusterHeader: React.FC<ClusterHeaderProps> = ({
  sessionId, confidence, platformHealth, wsConnected, onGoHome, phase,
}) => {
  const [showBreakdown, setShowBreakdown] = useState(false);

  return (
    <header className="h-14 border-b border-[#1f3b42] bg-[#152a2f] flex items-center justify-between px-6 z-50 shadow-md shrink-0">
      <div className="flex items-center gap-4">
        <button onClick={onGoHome} className="text-slate-400 hover:text-white transition-colors">
          <span className="material-symbols-outlined">arrow_back</span>
        </button>
        <div className="flex items-center gap-2">
          <StatusBadge
            status={wsConnected ? 'healthy' : 'critical'}
            label={wsConnected ? 'LIVE' : 'OFFLINE'}
            pulse={wsConnected}
          />
          <h1 className="text-xl font-bold tracking-tight text-white">
            DebugDuck <span className="text-[#e09f3e]">Cluster War Room</span>
          </h1>
        </div>
        <div className="px-3 py-1 bg-[#1a1814] border border-[#1f3b42] rounded text-xs font-mono flex items-center gap-2">
          <span className="text-slate-500 uppercase tracking-widest text-[10px]">Session:</span>
          <span className="text-[#e09f3e]">#{sessionId.slice(0, 8).toUpperCase()}</span>
        </div>
      </div>

      <div className="flex items-center gap-8">
        <div className="flex flex-col items-end">
          <span className="text-[10px] uppercase tracking-tighter text-slate-500">Global Confidence</span>
          <div className="w-48 h-2 bg-[#1a1814] border border-[#1f3b42] rounded-full mt-1 overflow-hidden">
            <div
              className="h-full bg-[#e09f3e] transition-all duration-700"
              style={{ width: `${confidence}%`, boxShadow: '0 0 8px #e09f3e' }}
            />
          </div>
        </div>

        <div className="relative">
          <LLMCostBadge
            sessionId={sessionId}
            phase={phase || 'running'}
            onToggleBreakdown={() => setShowBreakdown(prev => !prev)}
          />
          <AgentCostBreakdown
            sessionId={sessionId}
            visible={showBreakdown}
            onClose={() => setShowBreakdown(false)}
          />
        </div>

        <ClusterDossierExport sessionId={sessionId} platformHealth={platformHealth} />

        <StatusBadge
          status={healthToStatus(platformHealth)}
          label={platformHealth || 'ANALYZING'}
          pulse={platformHealth === 'CRITICAL' || platformHealth === 'DEGRADED'}
        />
      </div>
    </header>
  );
};

export default ClusterHeader;
