import React, { useState, useMemo } from 'react';
import type { TaskEvent } from '../../types';

interface EventLogViewerProps {
  events: TaskEvent[];
}

const EventLogViewer: React.FC<EventLogViewerProps> = ({ events }) => {
  const [expanded, setExpanded] = useState(false);
  const [filter, setFilter] = useState('');
  const [severityFilter, setSeverityFilter] = useState<string>('all');

  const diagnosticEvents = useMemo(() => {
    return events
      .filter(e => e.event_type !== 'phase_change')
      .filter(e => {
        if (severityFilter === 'error') return e.event_type === 'error' || e.event_type === 'warning';
        if (severityFilter === 'info') return e.event_type !== 'error';
        return true;
      })
      .filter(e => {
        if (!filter) return true;
        const searchStr = `${e.agent_name} ${e.message} ${JSON.stringify(e.details || {})}`.toLowerCase();
        return searchStr.includes(filter.toLowerCase());
      });
  }, [events, filter, severityFilter]);

  if (!expanded) {
    return (
      <button
        onClick={() => setExpanded(true)}
        aria-label="Expand event log"
        aria-expanded={false}
        className="w-full flex items-center justify-between px-3 py-2 bg-[#141210] rounded border border-[#2a2520] hover:border-[#e09f3e]/30 transition-colors"
      >
        <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
          Event Log ({events.length} events)
        </span>
        <span className="material-symbols-outlined text-[14px] text-slate-600">expand_more</span>
      </button>
    );
  }

  return (
    <div className="bg-[#141210] rounded border border-[#2a2520] flex flex-col max-h-[300px]">
      <div className="flex items-center justify-between px-3 py-2 border-b border-[#2a2520] shrink-0">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">Event Log</span>
        <div className="flex items-center gap-2">
          <input
            value={filter}
            onChange={e => setFilter(e.target.value)}
            placeholder="Search..."
            aria-label="Filter events by text"
            className="bg-[#1a1814] text-[10px] text-slate-300 px-2 py-0.5 rounded border border-[#2a2520] w-32 outline-none focus:border-[#e09f3e]/30"
          />
          <select
            value={severityFilter}
            onChange={e => setSeverityFilter(e.target.value)}
            aria-label="Filter by severity"
            className="bg-[#1a1814] text-[10px] text-slate-300 px-1 py-0.5 rounded border border-[#2a2520] outline-none"
          >
            <option value="all">All</option>
            <option value="error">Errors</option>
            <option value="info">Info</option>
          </select>
          <button onClick={() => setExpanded(false)} aria-label="Collapse event log" aria-expanded={true} className="text-slate-600 hover:text-slate-300">
            <span className="material-symbols-outlined text-[14px]">expand_less</span>
          </button>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto custom-scrollbar p-2 space-y-0.5">
        {diagnosticEvents.map((event, i) => (
          <div key={i} className="flex items-start gap-2 px-1 py-0.5 hover:bg-[#1a1814]/50 rounded text-[10px] font-mono">
            <span className={`shrink-0 ${event.event_type === 'error' ? 'text-red-400' : event.event_type === 'warning' ? 'text-amber-400' : 'text-slate-600'}`}>
              {event.event_type === 'error' ? '✗' : event.event_type === 'warning' ? '⚠' : '·'}
            </span>
            <span className="text-slate-500 shrink-0 w-20 truncate">{event.agent_name || '—'}</span>
            <span className="text-slate-300 flex-1">{event.message}</span>
          </div>
        ))}
        {diagnosticEvents.length === 0 && (
          <div className="text-[10px] text-slate-600 text-center py-4">No matching events</div>
        )}
      </div>
    </div>
  );
};

export default EventLogViewer;
