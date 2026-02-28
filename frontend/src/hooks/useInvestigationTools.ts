import { useState, useEffect, useCallback, useRef } from 'react';
import { getTools, postInvestigate } from '../services/api';
import type { ToolDefinition, InvestigateRequest, InvestigateResponse } from '../types';

export function useInvestigationTools(sessionId: string | null) {
  const [tools, setTools] = useState<ToolDefinition[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // AbortController ref for in-flight postInvestigate calls
  const investigateAbortRef = useRef<AbortController | null>(null);

  // F2: Fetch tools with AbortController cleanup
  useEffect(() => {
    if (!sessionId) return;

    const controller = new AbortController();

    setError(null);
    getTools(sessionId, controller.signal)
      .then((data) => {
        setTools(data.tools);
        setError(null);
      })
      .catch((err) => {
        // Don't set error state for intentional aborts
        if (err instanceof DOMException && err.name === 'AbortError') return;
        setError('Failed to load tools');
      });

    return () => {
      controller.abort();
    };
  }, [sessionId]);

  // F1: Retry callback — re-fetches tools
  const retry = useCallback(() => {
    if (!sessionId) return;
    setError(null);
    getTools(sessionId)
      .then((data) => {
        setTools(data.tools);
        setError(null);
      })
      .catch(() => {
        setError('Failed to load tools');
      });
  }, [sessionId]);

  // F2: Abort previous in-flight postInvestigate before starting new one
  const executeAction = useCallback(
    async (request: InvestigateRequest): Promise<InvestigateResponse | null> => {
      if (!sessionId) return null;

      // Abort any previous in-flight request
      if (investigateAbortRef.current) {
        investigateAbortRef.current.abort();
      }
      const controller = new AbortController();
      investigateAbortRef.current = controller;

      setLoading(true);
      setError(null);
      try {
        const result = await postInvestigate(sessionId, request, controller.signal);
        setError(null);
        return result;
      } catch (err) {
        // Don't set error for intentional aborts
        if (err instanceof DOMException && err.name === 'AbortError') return null;
        setError('Investigation request failed');
        return null;
      } finally {
        setLoading(false);
      }
    },
    [sessionId]
  );

  return { tools, loading, error, retry, executeAction };
}
