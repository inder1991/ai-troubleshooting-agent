import { useState, useEffect, useCallback } from 'react';
import { API_BASE_URL } from '../../../services/api';

export interface CatalogAgent {
  id: string;
  name: string;
  workflow: string;
  role: string;
  description: string;
  status: 'active' | 'degraded' | 'offline';
  degraded_tools: string[];
  tools: string[];
  timeout_s: number;
  llm_config?: { model?: string };
}

export function useAgentCatalog() {
  const [agents, setAgents] = useState<CatalogAgent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const res = await window.fetch(`${API_BASE_URL}/api/v4/agents`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setAgents(data.agents || []);
      setError(null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  return { agents, loading, error, refresh: load };
}
