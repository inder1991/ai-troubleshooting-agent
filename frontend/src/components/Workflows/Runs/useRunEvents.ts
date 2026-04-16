import { useState, useEffect, useRef, useCallback } from 'react';
import { getRun, subscribeEvents } from '../../../services/runs';
import type { RunDetail, RunStatus } from '../../../types';
import type { LiveEvent } from './StepStatusPanel';

export interface UseRunEventsResult {
  run: RunDetail | null;
  liveEvents: LiveEvent[];
  loading: boolean;
  error: Error | null;
  connected: boolean;
}

const TERMINAL_STATUSES: ReadonlySet<RunStatus> = new Set([
  'success',
  'failed',
  'cancelled',
]);

const TERMINAL_EVENT_TYPES = new Set([
  'run.completed',
  'run.failed',
  'run.cancelled',
]);

export function useRunEvents(runId: string): UseRunEventsResult {
  const [run, setRun] = useState<RunDetail | null>(null);
  const [liveEvents, setLiveEvents] = useState<LiveEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [connected, setConnected] = useState(false);
  const esRef = useRef<EventSource | null>(null);

  const closeEs = useCallback(() => {
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
      setConnected(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function init() {
      try {
        const data = await getRun(runId);
        if (cancelled) return;
        setRun(data);
        setLoading(false);

        // Don't subscribe if already terminal
        if (TERMINAL_STATUSES.has(data.status)) return;

        const es = subscribeEvents(runId);
        esRef.current = es;

        es.onopen = () => {
          if (!cancelled) setConnected(true);
        };

        es.onmessage = (evt: MessageEvent) => {
          if (cancelled) return;
          try {
            const parsed = JSON.parse(evt.data) as LiveEvent;
            setLiveEvents((prev) => [...prev, parsed]);

            if (TERMINAL_EVENT_TYPES.has(parsed.type)) {
              // Update run status from event
              const newStatus =
                parsed.type === 'run.completed'
                  ? 'success'
                  : parsed.type === 'run.failed'
                    ? 'failed'
                    : 'cancelled';
              setRun((prev) =>
                prev ? { ...prev, status: newStatus as RunStatus } : prev,
              );
              es.close();
              setConnected(false);
            }
          } catch {
            // Ignore parse errors
          }
        };

        es.onerror = () => {
          if (!cancelled) setConnected(false);
        };
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err : new Error(String(err)));
          setLoading(false);
        }
      }
    }

    init();

    return () => {
      cancelled = true;
      closeEs();
    };
  }, [runId, closeEs]);

  return { run, liveEvents, loading, error, connected };
}
