import React, { useEffect, useState, useCallback } from 'react';
import type { V4Findings, V4SessionStatus } from '../../types';
import { getFindings, getSessionStatus } from '../../services/api';
import ErrorPatternsCard from './ErrorPatternsCard';
import MetricsChartCard from './MetricsChartCard';
import K8sStatusCard from './K8sStatusCard';
import TraceCard from './TraceCard';
import CodeImpactCard from './CodeImpactCard';
import DiagnosisSummaryCard from './DiagnosisSummaryCard';

interface DashboardTabProps {
  sessionId: string;
}

const DashboardTab: React.FC<DashboardTabProps> = ({ sessionId }) => {
  const [findings, setFindings] = useState<V4Findings | null>(null);
  const [status, setStatus] = useState<V4SessionStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const [findingsData, statusData] = await Promise.all([
        getFindings(sessionId),
        getSessionStatus(sessionId),
      ]);
      setFindings(findingsData);
      setStatus(statusData);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data');
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    setLoading(true);
    fetchData();

    // Poll for updates every 5 seconds while diagnosis is in progress
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, [fetchData]);

  if (loading && !findings) {
    return (
      <div className="flex items-center justify-center h-full text-gray-500">
        <div className="text-center">
          <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
          <p className="text-sm">Loading dashboard...</p>
        </div>
      </div>
    );
  }

  if (error && !findings) {
    return (
      <div className="flex items-center justify-center h-full text-gray-500">
        <div className="text-center">
          <p className="text-sm text-red-400">{error}</p>
          <button
            onClick={fetchData}
            className="mt-2 px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-sm text-white"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  const hasData =
    findings &&
    (findings.error_patterns.length > 0 ||
      findings.metric_anomalies.length > 0 ||
      findings.pod_statuses.length > 0 ||
      findings.k8s_events.length > 0 ||
      findings.trace_spans.length > 0 ||
      findings.impacted_files.length > 0 ||
      findings.findings.length > 0);

  if (!hasData) {
    return (
      <div className="flex items-center justify-center h-full text-gray-500">
        <div className="text-center">
          <div className="w-8 h-8 border-2 border-gray-600 border-t-blue-500 rounded-full animate-spin mx-auto mb-3" />
          <p className="text-lg mb-1">Waiting for analysis...</p>
          <p className="text-sm text-gray-600">
            Results will appear as agents complete their investigation.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-4">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Summary always goes full width at top */}
        {findings && status && findings.findings.length > 0 && (
          <div className="lg:col-span-2">
            <DiagnosisSummaryCard
              confidence={status.confidence}
              findings={findings.findings}
              criticVerdicts={findings.critic_verdicts}
              breadcrumbs={status.breadcrumbs}
            />
          </div>
        )}

        {findings && findings.error_patterns.length > 0 && (
          <ErrorPatternsCard patterns={findings.error_patterns} />
        )}

        {findings && findings.metric_anomalies.length > 0 && (
          <MetricsChartCard anomalies={findings.metric_anomalies} />
        )}

        {findings && (findings.pod_statuses.length > 0 || findings.k8s_events.length > 0) && (
          <K8sStatusCard pods={findings.pod_statuses} events={findings.k8s_events} />
        )}

        {findings && findings.trace_spans.length > 0 && (
          <TraceCard spans={findings.trace_spans} />
        )}

        {findings && findings.impacted_files.length > 0 && (
          <CodeImpactCard impacts={findings.impacted_files} />
        )}
      </div>
    </div>
  );
};

export default DashboardTab;
