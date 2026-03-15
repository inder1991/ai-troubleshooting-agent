import React, { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { CapabilityType, V4Session } from '../../types';
import { listSessionsV4 } from '../../services/api';
import { MetricStrip } from './MetricStrip';
import { EventTicker } from './EventTicker';
import HeroCapabilities from './HeroCapabilities';
import { EnvironmentHealth } from './EnvironmentHealth';
import { RecentAlerts } from './RecentAlerts';
import { RecentFindings } from './RecentFindings';
import { WeeklyStats } from './WeeklyStats';
import { CompactAgentFleet } from './CompactAgentFleet';
import AssistantDock from '../Assistant/AssistantDock';
import LiveIntelligenceFeed from './LiveIntelligenceFeed';
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

  // Status aurora color — reflects overall system state
  const auroraClass = useMemo(() => {
    const hasCritical = sessions.some(s => (s.critical_count ?? 0) > 0);
    const hasActive = sessions.some(s => !ACTIVE_PHASES.includes(s.status));
    if (hasCritical) return 'status-aurora status-aurora--critical';
    if (hasActive) return 'status-aurora status-aurora--active';
    return 'status-aurora status-aurora--healthy';
  }, [sessions]);

  return (
    <div className="flex-1 flex flex-col min-w-0 overflow-hidden command-center-bg">
      {/* Header — Search | Event Ticker | Bell */}
      <header
        className="h-14 border-b border-duck-border flex items-center px-6 shrink-0 bg-duck-panel/40"
        style={{ animation: 'fadeSlideUp 400ms cubic-bezier(0.25, 1, 0.5, 1) 0ms both' }}
      >
        {/* Search — fixed width, left */}
        <div className="relative w-56 shrink-0">
          <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 text-[18px]" aria-hidden="true">search</span>
          <input
            className="w-full rounded-md pl-9 pr-3 py-1.5 text-[13px] font-display text-white placeholder:text-slate-500 outline-none bg-duck-card/30 border border-duck-border/50 focus-visible:border-duck-accent"
            style={{
              transition: 'border-color 200ms cubic-bezier(0.25, 1, 0.5, 1), box-shadow 200ms cubic-bezier(0.25, 1, 0.5, 1)',
            }}
            onFocus={e => { e.currentTarget.style.boxShadow = '0 0 0 2px rgba(224,159,62,0.15)'; }}
            onBlur={e => { e.currentTarget.style.boxShadow = 'none'; }}
            placeholder="Search..."
            type="text"
            aria-label="Search sessions"
          />
        </div>

        {/* Separator */}
        <div className="w-px h-6 bg-duck-border/30 mx-4 shrink-0" />

        {/* Event Ticker — fills center */}
        <div className="flex-1 min-w-0 overflow-hidden">
          <EventTicker />
        </div>

        {/* Separator */}
        <div className="w-px h-6 bg-duck-border/30 mx-4 shrink-0" />

        {/* Notification bell */}
        <button
          className="relative w-9 h-9 flex items-center justify-center rounded-md text-slate-400 hover:text-white hover:bg-duck-card/30 transition-all shrink-0 focus-visible:outline focus-visible:outline-2 focus-visible:outline-duck-accent"
          aria-label="Notifications"
        >
          <span className="material-symbols-outlined text-[20px]" aria-hidden="true">notifications</span>
          <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-duck-accent shadow-[0_0_0_2px_#12110e]" aria-hidden="true" />
        </button>
      </header>

      {/* Status Aurora — living line reflecting system health */}
      <div className={auroraClass} />

      {/* Metric Strip */}
      <div style={{ animation: 'fadeSlideUp 400ms cubic-bezier(0.25, 1, 0.5, 1) 50ms both' }}>
        <MetricStrip />
      </div>

      {/* Capability pills — single line */}
      <div style={{ animation: 'fadeSlideUp 400ms cubic-bezier(0.25, 1, 0.5, 1) 100ms both' }}>
        <HeroCapabilities onSelectCapability={onSelectCapability} />
      </div>

      {/* Feed + Right Panels */}
      <div className="flex-1 overflow-y-auto custom-scrollbar px-6 pb-4" style={{ animation: 'fadeSlideUp 400ms cubic-bezier(0.25, 1, 0.5, 1) 150ms both' }}>
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 h-full">
          {/* Feed (9 col) */}
          <div className="lg:col-span-9 flex flex-col min-h-0">
            {/* Tab bar */}
            <div className="flex items-center justify-between px-2 py-2 shrink-0">
              <div className="flex gap-5">
                <button
                  onClick={() => setFeedTab('global')}
                  className="text-sm font-display font-bold pb-1"
                  style={{
                    color: feedTab === 'global' ? 'white' : '#94a3b8',
                    borderBottom: feedTab === 'global' ? '2px solid #e09f3e' : '2px solid transparent',
                    transition: 'color 200ms cubic-bezier(0.25, 1, 0.5, 1), border-color 200ms cubic-bezier(0.25, 1, 0.5, 1)',
                  }}
                >
                  Global Investigations
                </button>
                <button
                  onClick={() => setFeedTab('mine')}
                  className="text-sm font-display font-bold pb-1"
                  style={{
                    color: feedTab === 'mine' ? 'white' : '#94a3b8',
                    borderBottom: feedTab === 'mine' ? '2px solid #e09f3e' : '2px solid transparent',
                    transition: 'color 200ms cubic-bezier(0.25, 1, 0.5, 1), border-color 200ms cubic-bezier(0.25, 1, 0.5, 1)',
                  }}
                >
                  My Active ({myActiveCount})
                </button>
              </div>
              <TimeRangeSelector selected={timeRange} onChange={setTimeRange} />
            </div>

            {/* Feed content */}
            <div className="flex-1 overflow-y-auto custom-scrollbar surface-panel">
              <LiveIntelligenceFeed
                onSelectSession={onSelectSession}
                filterActive={feedTab === 'mine'}
              />
            </div>
          </div>

          {/* Right Panels (3 col) */}
          <div className="lg:col-span-3 flex flex-col gap-2 pt-10">
            {/* Environment Health */}
            <div style={{ animation: 'fadeSlideLeft 350ms cubic-bezier(0.25, 1, 0.5, 1) 200ms both' }}>
              <EnvironmentHealth />
            </div>

            {/* Recent Alerts */}
            <div style={{ animation: 'fadeSlideLeft 350ms cubic-bezier(0.25, 1, 0.5, 1) 280ms both' }} className="surface-panel p-2.5 overflow-hidden">
              <RecentAlerts />
            </div>

            {/* Recent Findings */}
            <div style={{ animation: 'fadeSlideLeft 350ms cubic-bezier(0.25, 1, 0.5, 1) 360ms both' }} className="surface-panel p-2.5 overflow-hidden">
              <RecentFindings />
            </div>

            {/* Weekly Stats */}
            <div style={{ animation: 'fadeSlideLeft 350ms cubic-bezier(0.25, 1, 0.5, 1) 440ms both' }} className="surface-panel p-2.5 overflow-hidden">
              <WeeklyStats />
            </div>

            {/* Agent Fleet */}
            <div style={{ animation: 'fadeSlideLeft 350ms cubic-bezier(0.25, 1, 0.5, 1) 520ms both' }} className="surface-panel p-2.5 overflow-hidden flex-1">
              <CompactAgentFleet />
            </div>
          </div>
        </div>
      </div>

      {/* AI Assistant Dock — pinned to bottom */}
      <AssistantDock
        onNavigate={(page) => {
          console.log('Assistant navigate:', page);
        }}
        onStartInvestigation={(capability) => {
          onSelectCapability(capability as CapabilityType);
        }}
      />
    </div>
  );
};

export default HomePage;
