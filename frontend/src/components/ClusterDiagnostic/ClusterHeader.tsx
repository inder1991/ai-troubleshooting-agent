import React from 'react';
import { StatusBadge } from '../shared/StatusBadge';
import type { SystemStatus } from '../shared/StatusBadge';

interface ClusterHeaderProps {
  sessionId: string;
  confidence: number;
  platformHealth: string;
  wsConnected: boolean;
  onGoHome: () => void;
}

const healthToStatus = (health: string): SystemStatus =>
  health === 'HEALTHY' ? 'healthy'
    : health === 'DEGRADED' ? 'degraded'
    : health === 'CRITICAL' ? 'critical'
    : 'unknown';

const ClusterHeader: React.FC<ClusterHeaderProps> = ({
  sessionId, confidence, platformHealth, wsConnected, onGoHome,
}) => {
  return (
    <header className="h-14 border-b border-[#1f3b42] bg-[#152a2f] flex items-center justify-between px-6 z-50 shadow-md shrink-0">
      <div className="flex items-center gap-4">
        <button onClick={onGoHome} className="text-slate-400 hover:text-white transition-colors">
          <span className="material-symbols-outlined" style={{ fontFamily: 'Material Symbols Outlined' }}>arrow_back</span>
        </button>
        <div className="flex items-center gap-2">
          <StatusBadge
            status={wsConnected ? 'healthy' : 'critical'}
            label={wsConnected ? 'LIVE' : 'OFFLINE'}
            pulse={wsConnected}
          />
          <h1 className="text-xl font-bold tracking-tight text-white">
            DebugDuck <span className="text-[#07b6d5]">Cluster War Room</span>
          </h1>
        </div>
        <div className="px-3 py-1 bg-[#0f2023] border border-[#1f3b42] rounded text-xs font-mono flex items-center gap-2">
          <span className="text-slate-500 uppercase tracking-widest text-[10px]">Session:</span>
          <span className="text-[#07b6d5]">#{sessionId.slice(0, 8).toUpperCase()}</span>
        </div>
      </div>

      <div className="flex items-center gap-8">
        <div className="flex flex-col items-end">
          <span className="text-[10px] uppercase tracking-tighter text-slate-500">Global Confidence</span>
          <div className="w-48 h-2 bg-[#0f2023] border border-[#1f3b42] rounded-full mt-1 overflow-hidden">
            <div
              className="h-full bg-[#07b6d5] transition-all duration-700"
              style={{ width: `${confidence}%`, boxShadow: '0 0 8px #07b6d5' }}
            />
          </div>
        </div>

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
