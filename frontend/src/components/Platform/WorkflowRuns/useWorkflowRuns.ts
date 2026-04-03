import { useState, useEffect, useCallback } from 'react';
import { API_BASE_URL } from '../../../services/api';

export interface WorkflowRun {
  id: string;
  workflow_name: string;
  service_name: string;
  status: 'running' | 'completed' | 'failed' | 'waiting_approval';
  started_at: string;
  finished_at?: string;
  agents_completed: string[];
  agents_pending: string[];
  overall_confidence?: number;
}

function deriveStatus(session: any): WorkflowRun['status'] {
  if (session.phase === 'FIX_APPROVAL_PENDING') return 'waiting_approval';
  if (session.phase === 'DIAGNOSIS_COMPLETE') return 'completed';
  if (session.error) return 'failed';
  return 'running';
}

export function useWorkflowRuns() {
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const res = await window.fetch(`${API_BASE_URL}/api/v4/sessions`);
      if (!res.ok) return;
      const data = await res.json();
      const sessions: any[] = data.sessions || [];
      setRuns(sessions.map(s => ({
        id: s.session_id || s.id,
        workflow_name: 'App Diagnostics',
        service_name: s.service_name || s.input?.service_name || 'Unknown service',
        status: deriveStatus(s),
        started_at: s.created_at || s.started_at || new Date().toISOString(),
        finished_at: s.finished_at,
        agents_completed: s.agents_completed || [],
        agents_pending: s.agents_pending || [],
        overall_confidence: s.overall_confidence,
      })));
    } catch {
      // API unavailable
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  return { runs, loading, refresh: load };
}
