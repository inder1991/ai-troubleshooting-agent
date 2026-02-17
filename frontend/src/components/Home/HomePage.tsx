import React from 'react';
import type { CapabilityType, V4Session } from '../../types';
import CapabilityLauncher from './CapabilityLauncher';
import LiveIntelligenceFeed from './LiveIntelligenceFeed';

interface HomePageProps {
  onSelectCapability: (capability: CapabilityType) => void;
  sessions: V4Session[];
  onSessionsChange: (sessions: V4Session[]) => void;
  onSelectSession: (session: V4Session) => void;
  wsConnected: boolean;
}

const HomePage: React.FC<HomePageProps> = ({
  onSelectCapability,
  sessions,
  onSessionsChange,
  onSelectSession,
  wsConnected,
}) => {
  return (
    <div className="flex-1 flex flex-col min-w-0 overflow-hidden" style={{ backgroundColor: '#0f2023' }}>
      {/* Top Header */}
      <header className="h-16 border-b border-[#224349] flex items-center justify-between px-8 shrink-0" style={{ backgroundColor: 'rgba(15,32,35,0.5)', backdropFilter: 'blur(12px)' }}>
        <div className="flex items-center gap-6 flex-1">
          {/* System Health Badge */}
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full" style={{ backgroundColor: 'rgba(16,185,129,0.1)', border: '1px solid rgba(16,185,129,0.2)' }}>
            <div className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse" />
            <span className="text-xs font-bold text-emerald-500 uppercase tracking-tighter">
              System Health: {wsConnected ? 'Online' : 'Offline'}
            </span>
          </div>

          {/* Global Search */}
          <div className="relative max-w-md w-full">
            <span
              className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 text-xl"
              style={{ fontFamily: 'Material Symbols Outlined' }}
            >search</span>
            <input
              className="w-full rounded-lg pl-11 py-2 text-sm text-white placeholder:text-slate-500 transition-all outline-none"
              style={{ backgroundColor: 'rgba(30,47,51,0.4)', border: '1px solid #224349' }}
              placeholder="Search logs, agents, or PRs (⌘ + K)"
              type="text"
            />
          </div>
        </div>

        <div className="flex items-center gap-4">
          {/* Notifications */}
          <button className="relative p-2 text-slate-400 hover:text-white transition-colors">
            <span className="material-symbols-outlined" style={{ fontFamily: 'Material Symbols Outlined' }}>notifications</span>
            <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full" style={{ backgroundColor: '#07b6d5', boxShadow: '0 0 0 2px #0f2023' }} />
          </button>

          <div className="h-8 w-px" style={{ backgroundColor: '#224349' }} />

          {/* User Profile */}
          <div className="flex items-center gap-3 cursor-pointer group">
            <div className="text-right hidden sm:block">
              <p className="text-xs font-bold text-white leading-none">SRE Admin</p>
              <p className="text-[10px] text-slate-500 mt-1">Platform Engineer</p>
            </div>
            <div className="w-9 h-9 rounded-lg border border-[#224349] shadow-md flex items-center justify-center" style={{ backgroundColor: 'rgba(7,182,213,0.2)' }}>
              <span className="material-symbols-outlined text-lg" style={{ fontFamily: 'Material Symbols Outlined', color: '#07b6d5' }}>person</span>
            </div>
          </div>
        </div>
      </header>

      {/* Main Scrolling Content */}
      <div className="flex-1 overflow-y-auto p-8 custom-scrollbar">
        {/* Capability Launcher section */}
        <section className="mb-10">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h2 className="text-xl font-bold text-white tracking-tight">Capability Launcher</h2>
              <p className="text-sm text-slate-400 mt-1">Deploy automated diagnostics and remediations</p>
            </div>
          </div>
          <CapabilityLauncher onSelectCapability={onSelectCapability} />
        </section>

        {/* Live Intelligence Feed */}
        <LiveIntelligenceFeed
          sessions={sessions}
          onSessionsChange={onSessionsChange}
          onSelectSession={onSelectSession}
        />
      </div>
    </div>
  );
};

export default HomePage;
