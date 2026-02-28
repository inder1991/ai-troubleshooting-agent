import React from 'react';

interface ClusterHeaderProps {
  sessionId: string;
  confidence: number;
  platformHealth: string;
  wsConnected: boolean;
  onGoHome: () => void;
}

const healthColor = (health: string) =>
  health === 'HEALTHY' ? '#10b981'
    : health === 'DEGRADED' ? '#f59e0b'
    : health === 'CRITICAL' ? '#ef4444'
    : '#6b7280';

const ClusterHeader: React.FC<ClusterHeaderProps> = ({
  sessionId, confidence, platformHealth, wsConnected, onGoHome,
}) => {
  const color = healthColor(platformHealth);

  return (
    <header className="h-14 border-b border-[#1f3b42] bg-[#152a2f] flex items-center justify-between px-6 z-50 shadow-md shrink-0">
      <div className="flex items-center gap-4">
        <button onClick={onGoHome} className="text-slate-400 hover:text-white transition-colors">
          <span className="material-symbols-outlined" style={{ fontFamily: 'Material Symbols Outlined' }}>arrow_back</span>
        </button>
        <div className="flex items-center gap-2">
          <span className={`w-3 h-3 rounded-full ${wsConnected ? 'bg-emerald-500 animate-pulse' : 'bg-slate-600'}`} />
          <h1 className="text-xl font-bold tracking-tight text-white">
            DebugDuck <span className="text-[#13b6ec]">Cluster War Room</span>
          </h1>
        </div>
        <div className="px-3 py-1 bg-[#0f2023] border border-[#1f3b42] rounded text-xs font-mono flex items-center gap-2">
          <span className="text-slate-500 uppercase tracking-widest text-[10px]">Session:</span>
          <span className="text-[#13b6ec]">#{sessionId.slice(0, 8).toUpperCase()}</span>
        </div>
      </div>

      <div className="flex items-center gap-8">
        <div className="flex flex-col items-end">
          <span className="text-[10px] uppercase tracking-tighter text-slate-500">Global Confidence</span>
          <div className="w-48 h-2 bg-[#0f2023] border border-[#1f3b42] rounded-full mt-1 overflow-hidden">
            <div
              className="h-full bg-[#13b6ec] transition-all duration-700"
              style={{ width: `${confidence}%`, boxShadow: '0 0 8px #13b6ec' }}
            />
          </div>
        </div>

        <div className="flex items-center gap-2 font-mono font-bold text-sm" style={{ color }}>
          <span className={`w-2 h-2 rounded-full animate-pulse`} style={{ backgroundColor: color }} />
          {platformHealth || 'ANALYZING'}
        </div>
      </div>
    </header>
  );
};

export default ClusterHeader;
