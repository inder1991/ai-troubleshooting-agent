import { useState, useEffect, useCallback } from 'react';
import { getTools, postInvestigate } from '../services/api';
import type { ToolDefinition, InvestigateRequest, InvestigateResponse } from '../types';

export function useInvestigationTools(sessionId: string | null) {
  const [tools, setTools] = useState<ToolDefinition[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!sessionId) return;
    getTools(sessionId).then((data) => setTools(data.tools)).catch(() => {});
  }, [sessionId]);

  const executeAction = useCallback(
    async (request: InvestigateRequest): Promise<InvestigateResponse | null> => {
      if (!sessionId) return null;
      setLoading(true);
      try {
        return await postInvestigate(sessionId, request);
      } catch {
        return null;
      } finally {
        setLoading(false);
      }
    },
    [sessionId]
  );

  return { tools, loading, executeAction };
}
