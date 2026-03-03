import React, { useState, useEffect, useRef } from 'react';
import DiagnosisPanel from './DiagnosisPanel';
import NetworkCanvas from './NetworkCanvas';
import NetworkEvidenceStack from './NetworkEvidenceStack';
import { getNetworkFindings, getAdapterStatus } from '../../services/api';
import type { NetworkFindings } from '../../types';

interface NetworkWarRoomProps {
  session: { session_id: string; service_name: string };
  onGoHome: () => void;
}

const NetworkWarRoom: React.FC<NetworkWarRoomProps> = ({ session, onGoHome }) => {
  const [findings, setFindings] = useState<NetworkFindings | null>(null);
  const [adapters, setAdapters] = useState<Array<{ vendor: string; status: string }>>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Fetch adapter status once on mount
  useEffect(() => {
    getAdapterStatus()
      .then((data) => {
        // Backend returns { adapters: [{ device_id, vendor, status, ... }] }
        const adapterList = data?.adapters;
        if (Array.isArray(adapterList)) {
          setAdapters(
            adapterList.map((a: Record<string, unknown>) => ({
              vendor: String(a.vendor || a.device_id || 'unknown'),
              status: String(a.status || 'not_configured'),
            }))
          );
        }
      })
      .catch(() => {
        /* adapter status is non-critical */
      });
  }, []);

  // Poll findings
  useEffect(() => {
    let cancelled = false;

    const fetchFindings = async () => {
      try {
        const data = (await getNetworkFindings(session.session_id)) as NetworkFindings;
        if (cancelled) return;
        setFindings(data);
        setError(null);
        setLoading(false);

        // Stop polling when terminal
        const phase = data.phase?.toLowerCase();
        if (phase === 'complete' || phase === 'error' || phase === 'done') {
          if (pollRef.current) {
            clearInterval(pollRef.current);
            pollRef.current = null;
          }
        }
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : 'Failed to load findings');
        setLoading(false);
      }
    };

    // Initial fetch
    fetchFindings();

    // Start polling every 5 seconds
    pollRef.current = setInterval(fetchFindings, 5000);

    return () => {
      cancelled = true;
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [session.session_id]);

  // Determine if still running
  const phase = findings?.phase?.toLowerCase() || '';
  const isRunning = phase === 'running' || phase === 'queued' || phase === 'initial' || phase === '';

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden" style={{ backgroundColor: '#0a0f13' }}>
      {/* Header */}
      <div
        className="flex items-center justify-between px-6 py-3 flex-shrink-0"
        style={{ borderBottom: '1px solid #224349' }}
      >
        <div className="flex items-center gap-3">
          <span className="material-symbols-outlined text-lg" style={{ color: '#f59e0b' }}>
            cable
          </span>
          <div>
            <h1 className="text-sm font-mono font-bold" style={{ color: '#e2e8f0' }}>
              Network War Room
            </h1>
            <p className="text-xs font-mono" style={{ color: '#64748b' }}>
              {session.service_name}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {/* Phase badge */}
          {findings && (
            <span
              className="text-xs font-mono px-2 py-1 rounded"
              style={{
                color: phase === 'complete' || phase === 'done'
                  ? '#22c55e'
                  : phase === 'error'
                  ? '#ef4444'
                  : '#f59e0b',
                backgroundColor: phase === 'complete' || phase === 'done'
                  ? 'rgba(34,197,94,0.12)'
                  : phase === 'error'
                  ? 'rgba(239,68,68,0.12)'
                  : 'rgba(245,158,11,0.12)',
              }}
            >
              {findings.phase}
            </span>
          )}
          <button
            onClick={onGoHome}
            className="text-xs font-mono px-3 py-1.5 rounded transition-colors hover:opacity-80"
            style={{ color: '#64748b', backgroundColor: '#162a2e' }}
          >
            Back to Home
          </button>
        </div>
      </div>

      {/* Loading state */}
      {loading && !findings && (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center font-mono">
            <div className="relative w-10 h-10 mx-auto mb-4">
              <div
                className="absolute inset-0 rounded-full border-2 border-t-transparent animate-spin"
                style={{ borderColor: '#224349', borderTopColor: '#07b6d5' }}
              />
            </div>
            <p className="text-sm" style={{ color: '#e2e8f0' }}>
              Analyzing network path...
            </p>
            <p className="text-xs mt-1" style={{ color: '#64748b' }}>
              Session: {session.session_id}
            </p>
          </div>
        </div>
      )}

      {/* Error state */}
      {error && !findings && (
        <div className="flex-1 flex items-center justify-center">
          <div
            className="rounded-lg p-6 max-w-sm text-center font-mono"
            style={{ backgroundColor: '#0f2023', border: '1px solid rgba(239,68,68,0.3)' }}
          >
            <span className="material-symbols-outlined text-2xl mb-2" style={{ color: '#ef4444' }}>
              error
            </span>
            <p className="text-sm mb-1" style={{ color: '#ef4444' }}>
              Failed to load findings
            </p>
            <p className="text-xs" style={{ color: '#64748b' }}>
              {error}
            </p>
          </div>
        </div>
      )}

      {/* No Topology Data warning */}
      {findings && findings.state?.diagnosis_status === 'no_path_known' && (
        <div className="mx-4 mt-2 rounded-lg p-3 flex items-center gap-3 font-mono text-xs"
          style={{ backgroundColor: 'rgba(245,158,11,0.1)', border: '1px solid rgba(245,158,11,0.3)' }}>
          <span className="material-symbols-outlined text-lg" style={{ fontFamily: 'Material Symbols Outlined', color: '#f59e0b' }}>warning</span>
          <div>
            <p className="font-semibold" style={{ color: '#f59e0b' }}>No Topology Data</p>
            <p style={{ color: '#94a3b8' }}>
              Import IPAM data or build a topology canvas to enable path analysis.
              Without topology data, the diagnosis engine cannot find network paths.
            </p>
          </div>
        </div>
      )}

      {/* Main War Room Grid */}
      {findings && (
        <div className="flex-1 grid grid-cols-12 gap-4 p-4 overflow-hidden min-h-0">
          {/* Left: Diagnosis Panel (col-span-3) */}
          <div className="col-span-3 min-h-0 overflow-hidden">
            <DiagnosisPanel findings={findings} />
          </div>

          {/* Center: Network Canvas (col-span-5) */}
          <div className="col-span-5 min-h-0 overflow-hidden flex flex-col">
            <NetworkCanvas findings={findings} />
          </div>

          {/* Right: Evidence Stack (col-span-4) */}
          <div className="col-span-4 min-h-0 overflow-hidden">
            <NetworkEvidenceStack findings={findings} adapters={adapters} />
          </div>
        </div>
      )}

      {/* Running indicator */}
      {isRunning && findings && (
        <div
          className="flex items-center gap-2 px-6 py-2 text-xs font-mono flex-shrink-0"
          style={{ borderTop: '1px solid #224349', color: '#f59e0b' }}
        >
          <div
            className="w-2 h-2 rounded-full animate-pulse"
            style={{ backgroundColor: '#f59e0b' }}
          />
          Diagnosis in progress... refreshing every 5s
        </div>
      )}
    </div>
  );
};

export default NetworkWarRoom;
