import React, { useEffect, useRef, useState, useCallback } from 'react';
import type { TaskEvent, TokenUsage } from '../../types';
import { getEvents, getSessionStatus } from '../../services/api';
import TokenSummary from './TokenSummary';

interface ActivityLogTabProps {
  sessionId: string;
  events: TaskEvent[];
}

const eventTypeColors: Record<TaskEvent['event_type'], string> = {
  started: 'border-l-blue-500 bg-blue-900/10',
  progress: 'border-l-gray-500 bg-gray-900/10',
  success: 'border-l-green-500 bg-green-900/10',
  warning: 'border-l-orange-500 bg-orange-900/10',
  error: 'border-l-red-500 bg-red-900/10',
};

const eventTypeDot: Record<TaskEvent['event_type'], string> = {
  started: 'bg-blue-500',
  progress: 'bg-gray-500',
  success: 'bg-green-500',
  warning: 'bg-orange-500',
  error: 'bg-red-500',
};

const ActivityLogTab: React.FC<ActivityLogTabProps> = ({ sessionId, events: propEvents }) => {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [allEvents, setAllEvents] = useState<TaskEvent[]>(propEvents);
  const [tokenUsage, setTokenUsage] = useState<TokenUsage[]>([]);

  const fetchData = useCallback(async () => {
    try {
      const [eventsData, statusData] = await Promise.all([
        getEvents(sessionId),
        getSessionStatus(sessionId),
      ]);
      setAllEvents(eventsData);
      setTokenUsage(statusData?.token_usage || []);
    } catch (err) {
      console.error('Failed to fetch activity log:', err);
    }
  }, [sessionId]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, [fetchData]);

  // Merge prop events with fetched events
  useEffect(() => {
    if (propEvents.length > 0) {
      setAllEvents((prev) => {
        const existing = new Set(prev.map((e) => `${e.timestamp}-${e.agent_name}-${e.message}`));
        const newEvents = propEvents.filter(
          (e) => !existing.has(`${e.timestamp}-${e.agent_name}-${e.message}`)
        );
        return newEvents.length > 0 ? [...prev, ...newEvents] : prev;
      });
    }
  }, [propEvents]);

  // Auto-scroll
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [allEvents]);

  return (
    <div className="flex flex-col h-full">
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-1">
        {allEvents.length === 0 ? (
          <div className="flex items-center justify-center h-full text-gray-500">
            <div className="text-center">
              <p className="text-lg mb-1">No events yet</p>
              <p className="text-sm">Activity will appear as agents begin their investigation.</p>
            </div>
          </div>
        ) : (
          allEvents.map((event, i) => (
            <div
              key={`${event.timestamp}-${i}`}
              className={`border-l-2 rounded-r px-3 py-2 ${eventTypeColors[event.event_type]}`}
            >
              <div className="flex items-center gap-2">
                <span className={`w-2 h-2 rounded-full ${eventTypeDot[event.event_type]}`} />
                <span className="text-xs text-gray-500 font-mono whitespace-nowrap">
                  {new Date(event.timestamp).toLocaleTimeString([], {
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit',
                  })}
                </span>
                <span className="text-xs text-blue-400 font-medium whitespace-nowrap">
                  {event.agent_name}
                </span>
                <span className="text-sm text-gray-300 truncate">{event.message}</span>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Token summary at bottom */}
      {tokenUsage.length > 0 && (
        <div className="border-t border-gray-700 p-4">
          <TokenSummary tokenUsage={tokenUsage} />
        </div>
      )}
    </div>
  );
};

export default ActivityLogTab;
