import React from 'react';
import type { TimelineEventData } from '../../types';

interface TimelineCardProps {
  events: TimelineEventData[];
}

const severityColor: Record<string, string> = {
  info: 'bg-gray-500',
  warning: 'bg-yellow-500',
  error: 'bg-red-500',
  critical: 'bg-purple-500',
};

const severityBorder: Record<string, string> = {
  info: 'border-gray-500/40',
  warning: 'border-yellow-500/40',
  error: 'border-red-500/40',
  critical: 'border-purple-500/40',
};

const severityText: Record<string, string> = {
  info: 'text-gray-400',
  warning: 'text-yellow-400',
  error: 'text-red-400',
  critical: 'text-purple-400',
};

const TimelineCard: React.FC<TimelineCardProps> = ({ events }) => {
  if (events.length === 0) return null;

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg p-4">
      <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
        <span className="w-2 h-2 rounded-full bg-cyan-500" />
        Incident Timeline
      </h3>

      <div className="overflow-x-auto">
        <div className="flex items-start gap-0 min-w-max pb-2">
          {events.map((event, idx) => {
            const ts = new Date(event.timestamp);
            const timeStr = ts.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
            const dotColor = severityColor[event.severity] || 'bg-gray-500';
            const borderColor = severityBorder[event.severity] || 'border-gray-500/40';
            const textColor = severityText[event.severity] || 'text-gray-400';

            return (
              <div key={idx} className="flex flex-col items-center" style={{ minWidth: '160px' }}>
                {/* Dot and connecting line */}
                <div className="flex items-center w-full justify-center relative">
                  {idx > 0 && (
                    <div className="absolute left-0 right-1/2 top-1/2 h-px bg-gray-600" />
                  )}
                  {idx < events.length - 1 && (
                    <div className="absolute left-1/2 right-0 top-1/2 h-px bg-gray-600" />
                  )}
                  <div className={`w-3 h-3 rounded-full ${dotColor} relative z-10 ring-2 ring-gray-800`} />
                </div>

                {/* Event card */}
                <div className={`mt-2 border ${borderColor} rounded-md px-3 py-2 bg-gray-900/50 w-36`}>
                  <div className="text-[10px] text-gray-500 font-mono mb-1">{timeStr}</div>
                  <span className={`inline-block text-[10px] px-1.5 py-0.5 rounded font-medium bg-gray-700 ${textColor} mb-1`}>
                    {event.source}
                  </span>
                  <p className="text-xs text-gray-300 line-clamp-2">{event.description}</p>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Legend */}
      <div className="flex gap-4 mt-3 border-t border-gray-700 pt-2">
        {(['info', 'warning', 'error', 'critical'] as const).map((sev) => (
          <div key={sev} className="flex items-center gap-1">
            <div className={`w-2 h-2 rounded-full ${severityColor[sev]}`} />
            <span className="text-[10px] text-gray-500 capitalize">{sev}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

export default TimelineCard;
