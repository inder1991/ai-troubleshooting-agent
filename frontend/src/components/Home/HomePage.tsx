import React, { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { CapabilityType, V4Session } from '../../types';
import { listSessionsV4 } from '../../services/api';
import CapabilityLauncher from './CapabilityLauncher';
import LiveIntelligenceFeed from './LiveIntelligenceFeed';
import { MetricRibbon } from './MetricRibbon';
import { QuickActionsPanel } from './QuickActionsPanel';
import { EnvironmentHealth } from './EnvironmentHealth';
import { AgentFleetPulse } from './AgentFleetPulse';
import { TimeRangeSelector } from '../shared';

interface HomePageProps {
  onSelectCapability: (capability: CapabilityType) => void;
  onSelectSession: (session: V4Session) => void;
  wsConnected: boolean;
}

const ACTIVE_PHASES = ['complete', 'diagnosis_complete', 'error'];

const HomePage: React.FC<HomePageProps> = ({
  onSelectCapability,
  onSelectSession,
  wsConnected,
}) => {
  const [feedTab, setFeedTab] = useState<'global' | 'mine'>('global');
  const [timeRange, setTimeRange] = useState<string>('1h');

  // Read from the shared live-sessions cache for the "My Investigations" count
  const { data: sessions = [] } = useQuery({
    queryKey: ['live-sessions'],
    queryFn: listSessionsV4,
    refetchInterval: 10000,
    staleTime: 5000,
  });

  const myActiveCount = useMemo(
    () => sessions.filter((s) => !ACTIVE_PHASES.includes(s.status)).length,
    [sessions]
  );

  return (
    <div className="flex-1 flex flex-col min-w-0 overflow-hidden bg-duck-bg">
      {/* Top Header */}
      <header className="h-16 border-b border-duck-border flex items-center justify-between px-8 shrink-0 bg-duck-panel/50 backdrop-blur-md">
        <div className="flex items-center gap-6 flex-1">
          {/* System Health Badge */}
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/20">
            <div className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse" />
            <span className="text-xs font-bold text-emerald-500 uppercase tracking-tighter">
              System Health: {wsConnected ? 'Online' : 'Offline'}
            </span>
          </div>

          {/* Global Search */}
          <div className="relative max-w-md w-full">
            <span
              className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 text-xl"
              aria-hidden="true"
            >search</span>
            <input
              className="w-full rounded-lg pl-11 py-2 text-sm text-white placeholder:text-slate-500 transition-all duration-200 ease-in-out outline-none bg-duck-card/40 border border-duck-border focus-visible:outline focus-visible:outline-2 focus-visible:outline-duck-accent"
              placeholder="Search logs, agents, or PRs (⌘ + K)"
              type="text"
            />
          </div>
        </div>

        <div className="flex items-center gap-4">
          {/* Notifications */}
          <button className="relative p-2 text-slate-400 hover:text-white transition-all duration-200 ease-in-out focus-visible:outline focus-visible:outline-2 focus-visible:outline-duck-accent" aria-label="View Notifications">
            <span className="material-symbols-outlined" aria-hidden="true">notifications</span>
            <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-duck-accent shadow-[0_0_0_2px_#0f2023]" />
          </button>

          <div className="h-8 w-px bg-duck-border" />

          {/* User Profile */}
          <div className="flex items-center gap-3 cursor-pointer group focus-visible:outline focus-visible:outline-2 focus-visible:outline-duck-accent" role="button" tabIndex={0} aria-label="User Profile">
            <div className="text-right hidden sm:block">
              <p className="text-xs font-bold text-white leading-none">SRE Admin</p>
              <p className="text-micro text-slate-500 mt-1">Platform Engineer</p>
            </div>
            <div className="w-9 h-9 rounded-lg border border-duck-border shadow-md flex items-center justify-center bg-duck-accent/20">
              <span className="material-symbols-outlined text-lg text-duck-accent" aria-hidden="true">person</span>
            </div>
          </div>
        </div>
      </header>

      {/* Main Scrolling Content */}
      <div className="flex-1 overflow-y-auto p-8 custom-scrollbar">

        {/* ROW 1: Triage & Health */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 mb-6">
          <div className="lg:col-span-8">
            <MetricRibbon />
          </div>
          <div className="lg:col-span-4">
            <EnvironmentHealth />
          </div>
        </div>

        {/* ROW 2: Core Workspace (locked 500px) */}
        <div className="grid grid-cols-1 lg:grid-cols-12 lg:grid-rows-[1fr] gap-6 mb-8 lg:h-[500px] overflow-hidden">

          {/* Left Column: Feed with tab bar */}
          <div className="lg:col-span-8 flex flex-col min-h-0 bg-duck-panel border border-duck-border rounded-lg overflow-hidden">
            {/* Tab bar */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-duck-border bg-duck-card/30 shrink-0">
              <div className="flex gap-6">
                <button
                  onClick={() => setFeedTab('global')}
                  className={`text-sm font-bold pb-1 -mb-[13px] transition-colors ${
                    feedTab === 'global'
                      ? 'text-white border-b-2 border-duck-accent'
                      : 'text-duck-muted hover:text-slate-300'
                  }`}
                >
                  Global Feed
                </button>
                <button
                  onClick={() => setFeedTab('mine')}
                  className={`text-sm font-bold pb-1 -mb-[13px] transition-colors ${
                    feedTab === 'mine'
                      ? 'text-white border-b-2 border-duck-accent'
                      : 'text-duck-muted hover:text-slate-300'
                  }`}
                >
                  My Investigations ({myActiveCount})
                </button>
              </div>
              <TimeRangeSelector selected={timeRange} onChange={setTimeRange} />
            </div>

            {/* Scrollable feed */}
            <div className="flex-1 min-h-0 overflow-y-auto custom-scrollbar">
              <LiveIntelligenceFeed
                onSelectSession={onSelectSession}
                filterActive={feedTab === 'mine'}
              />
            </div>
          </div>

          {/* Right Column: QuickActions + AgentFleetPulse */}
          <div className="lg:col-span-4 flex flex-col gap-5 min-h-0 overflow-hidden">
            <div className="h-[240px] shrink-0">
              <QuickActionsPanel
                onSelectCapability={onSelectCapability}
                wsConnected={wsConnected}
              />
            </div>
            <div className="h-[240px] shrink-0">
              <AgentFleetPulse />
            </div>
          </div>
        </div>

        {/* ROW 3: Capabilities (full width) */}
        <section>
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-lg font-bold text-white tracking-tight">Capabilities</h2>
              <p className="text-xs text-duck-muted mt-0.5">Deploy automated diagnostics and remediations</p>
            </div>
          </div>
          <CapabilityLauncher onSelectCapability={onSelectCapability} />
        </section>
      </div>
    </div>
  );
};

export default HomePage;
