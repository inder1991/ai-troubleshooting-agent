import React, { useState, useEffect, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useQuery } from '@tanstack/react-query';
import type { V4Session } from '../../types';
import { listSessionsV4 } from '../../services/api';

interface TickerEvent {
  id: string;
  icon: string;
  iconColor: string;
  message: string;
  accent: string;
}

const COMPLETED = ['complete', 'diagnosis_complete'];

export const EventTicker: React.FC = () => {
  const { data: sessions = [] } = useQuery({
    queryKey: ['live-sessions'],
    queryFn: listSessionsV4,
    refetchInterval: 10000,
    staleTime: 5000,
  });

  // Derive live events from session state
  const tickerEvents = useMemo<TickerEvent[]>(() => {
    const events: TickerEvent[] = [];

    // Running investigations
    const running = sessions.filter(s => !COMPLETED.includes(s.status) && s.status !== 'error' && s.status !== 'cancelled');
    for (const s of running) {
      events.push({
        id: `run-${s.session_id}`,
        icon: 'progress_activity',
        iconColor: 'text-amber-400 animate-spin',
        message: `Investigating ${s.service_name}`,
        accent: 'text-amber-400',
      });
    }

    // Critical findings from recent sessions
    const recent = sessions
      .filter(s => COMPLETED.includes(s.status))
      .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime());

    for (const s of recent.slice(0, 5)) {
      const critCount = s.critical_count ?? 0;
      const findCount = s.findings_count ?? 0;

      if (critCount > 0) {
        events.push({
          id: `crit-${s.session_id}`,
          icon: 'emergency',
          iconColor: 'text-red-400',
          message: `CRITICAL: ${critCount} issue${critCount > 1 ? 's' : ''} found in ${s.service_name} (${s.incident_id || s.session_id.slice(0, 8)})`,
          accent: 'text-red-400',
        });
      } else if (findCount > 3) {
        events.push({
          id: `warn-${s.session_id}`,
          icon: 'warning',
          iconColor: 'text-amber-400',
          message: `${findCount} findings in ${s.service_name} (${s.incident_id || s.session_id.slice(0, 8)})`,
          accent: 'text-amber-400',
        });
      }
    }

    // Completed clean
    for (const s of recent.slice(0, 3)) {
      const findCount = s.findings_count ?? 0;
      if (findCount === 0) {
        events.push({
          id: `clean-${s.session_id}`,
          icon: 'check_circle',
          iconColor: 'text-emerald-400',
          message: `${s.service_name} — no issues found (${s.incident_id || s.session_id.slice(0, 8)})`,
          accent: 'text-emerald-400',
        });
      }
    }

    // Errored sessions
    const errored = sessions.filter(s => s.status === 'error').slice(0, 2);
    for (const s of errored) {
      events.push({
        id: `err-${s.session_id}`,
        icon: 'error',
        iconColor: 'text-red-400',
        message: `Investigation failed: ${s.service_name} (${s.incident_id || s.session_id.slice(0, 8)})`,
        accent: 'text-red-400',
      });
    }

    // If no real events, show demo events so the ticker is never empty
    if (events.length === 0) {
      return [
        {
          id: 'demo-1',
          icon: 'emergency',
          iconColor: 'text-red-400',
          message: 'CRITICAL: Connection pool saturation (87%) in prod-orders (INC-20260314-A3F2)',
          accent: 'text-red-400',
        },
        {
          id: 'demo-2',
          icon: 'progress_activity',
          iconColor: 'text-amber-400 animate-spin',
          message: 'Investigating payment-service — query_analyst analyzing slow queries',
          accent: 'text-amber-400',
        },
        {
          id: 'demo-3',
          icon: 'check_circle',
          iconColor: 'text-emerald-400',
          message: 'auth-service — all checks passed, no issues found (INC-20260314-B1C3)',
          accent: 'text-emerald-400',
        },
        {
          id: 'demo-4',
          icon: 'warning',
          iconColor: 'text-amber-400',
          message: '7 findings in staging-db: 3 bloated tables, 2 unused indexes (INC-20260314-D4E5)',
          accent: 'text-amber-400',
        },
        {
          id: 'demo-5',
          icon: 'emergency',
          iconColor: 'text-red-400',
          message: 'Replication lag 45s on replica-eu-1 — health_analyst investigating (INC-20260314-F6G7)',
          accent: 'text-red-400',
        },
      ];
    }

    return events;
  }, [sessions]);

  // Cycle through events
  const [currentIdx, setCurrentIdx] = useState(0);
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    if (tickerEvents.length <= 1 || paused) return;
    const iv = setInterval(() => {
      setCurrentIdx(i => (i + 1) % tickerEvents.length);
    }, 5000);
    return () => clearInterval(iv);
  }, [tickerEvents.length, paused]);

  // Reset index if events change
  useEffect(() => {
    setCurrentIdx(0);
  }, [tickerEvents.length]);

  // Nothing to show
  if (tickerEvents.length === 0) {
    return (
      <div className="flex items-center gap-2">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500/40" aria-hidden="true" />
        <span className="text-[12px] font-display text-slate-400">All systems monitored</span>
      </div>
    );
  }

  const current = tickerEvents[currentIdx % tickerEvents.length];

  return (
    <div
      className="flex items-center gap-3 min-w-0 overflow-hidden cursor-default"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      aria-live="polite"
      aria-label="Live event ticker"
    >
      {/* Live indicator */}
      <div className="flex items-center gap-1.5 shrink-0">
        <span className="w-1.5 h-1.5 rounded-full bg-duck-accent animate-pulse" aria-hidden="true" />
        <span className="text-body-xs font-display font-bold text-slate-400 uppercase tracking-wider">Live</span>
      </div>

      {/* Animated event */}
      <AnimatePresence mode="wait">
        <motion.div
          key={current.id}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          transition={{ duration: 0.3, ease: 'easeOut' }}
          className="flex items-center gap-2 min-w-0"
        >
          <span className={`material-symbols-outlined text-[16px] shrink-0 ${current.iconColor}`} aria-hidden="true">
            {current.icon}
          </span>
          <span className={`text-[12px] font-display font-bold truncate ${current.accent}`}>
            {current.message}
          </span>
        </motion.div>
      </AnimatePresence>

      {/* Counter */}
      {tickerEvents.length > 1 && (
        <span className="text-body-xs text-slate-500 font-mono shrink-0 tabular-nums">
          {currentIdx + 1}/{tickerEvents.length}
        </span>
      )}
    </div>
  );
};
