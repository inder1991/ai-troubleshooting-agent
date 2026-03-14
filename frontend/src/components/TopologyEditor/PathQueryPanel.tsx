import React, { useState, useCallback } from 'react';
import { queryTopologyPaths, resolveIP } from '../../services/api';
import type { TopologyPath } from '../../types';

interface ResolvedIP {
  ip: string;
  hostname: string | null;
  loading: boolean;
}

const PathQueryPanel: React.FC = () => {
  const [srcIP, setSrcIP] = useState('');
  const [dstIP, setDstIP] = useState('');
  const [kPaths, setKPaths] = useState(3);
  const [paths, setPaths] = useState<TopologyPath[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resolvedIPs, setResolvedIPs] = useState<Record<string, ResolvedIP>>({});

  const handleResolve = useCallback(async (ip: string) => {
    if (!ip.trim()) return;
    setResolvedIPs((prev) => ({
      ...prev,
      [ip]: { ip, hostname: null, loading: true },
    }));
    try {
      const result = await resolveIP(ip.trim());
      setResolvedIPs((prev) => ({
        ...prev,
        [ip]: { ip, hostname: result.hostname ?? result.device_name ?? null, loading: false },
      }));
    } catch {
      setResolvedIPs((prev) => ({
        ...prev,
        [ip]: { ip, hostname: null, loading: false },
      }));
    }
  }, []);

  const handleTrace = useCallback(async () => {
    if (!srcIP.trim() || !dstIP.trim()) {
      setError('Source and destination IPs are required.');
      return;
    }
    setLoading(true);
    setError(null);
    setPaths([]);
    try {
      const result = await queryTopologyPaths(srcIP.trim(), dstIP.trim(), kPaths);
      const resultPaths: TopologyPath[] = result.paths ?? result ?? [];
      setPaths(Array.isArray(resultPaths) ? resultPaths : []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to query paths.');
    } finally {
      setLoading(false);
    }
  }, [srcIP, dstIP, kPaths]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter') handleTrace();
    },
    [handleTrace],
  );

  return (
    <div
      style={{
        width: 300,
        backgroundColor: '#0a1a1f',
        borderLeft: '1px solid rgba(224,159,62,0.12)',
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        overflow: 'hidden',
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: '12px 14px',
          borderBottom: '1px solid rgba(224,159,62,0.10)',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
        }}
      >
        <span
          className="material-symbols-outlined"
          style={{ fontSize: 18, color: '#e09f3e' }}
        >
          route
        </span>
        <span
          style={{
            fontSize: 13,
            fontWeight: 600,
            fontFamily: 'monospace',
            color: '#e8e0d4',
            letterSpacing: 0.3,
          }}
        >
          Path Query
        </span>
      </div>

      {/* Inputs */}
      <div style={{ padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 10 }}>
        {/* Source IP */}
        <IPField
          label="Source IP"
          value={srcIP}
          onChange={setSrcIP}
          onKeyDown={handleKeyDown}
          resolved={resolvedIPs[srcIP]}
          onResolve={() => handleResolve(srcIP)}
        />

        {/* Destination IP */}
        <IPField
          label="Destination IP"
          value={dstIP}
          onChange={setDstIP}
          onKeyDown={handleKeyDown}
          resolved={resolvedIPs[dstIP]}
          onResolve={() => handleResolve(dstIP)}
        />

        {/* K paths */}
        <div>
          <label
            style={{
              fontSize: 10,
              fontFamily: 'monospace',
              color: '#64748b',
              textTransform: 'uppercase',
              letterSpacing: 0.5,
              display: 'block',
              marginBottom: 4,
            }}
          >
            Max paths (K)
          </label>
          <input
            type="number"
            min={1}
            max={10}
            value={kPaths}
            onChange={(e) => setKPaths(Math.max(1, Math.min(10, Number(e.target.value) || 1)))}
            onKeyDown={handleKeyDown}
            style={{
              width: '100%',
              backgroundColor: 'rgba(224,159,62,0.06)',
              border: '1px solid rgba(224,159,62,0.15)',
              borderRadius: 6,
              padding: '6px 10px',
              color: '#e8e0d4',
              fontSize: 12,
              fontFamily: 'monospace',
              outline: 'none',
              boxSizing: 'border-box',
            }}
          />
        </div>

        {/* Trace button */}
        <button
          onClick={handleTrace}
          disabled={loading}
          style={{
            backgroundColor: loading ? 'rgba(224,159,62,0.3)' : '#e09f3e',
            color: '#1a1814',
            border: 'none',
            borderRadius: 6,
            padding: '8px 0',
            fontSize: 12,
            fontFamily: 'monospace',
            fontWeight: 600,
            cursor: loading ? 'not-allowed' : 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 6,
            transition: 'background-color 0.15s',
          }}
        >
          <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
            {loading ? 'hourglass_empty' : 'network_check'}
          </span>
          {loading ? 'Tracing...' : 'Trace'}
        </button>
      </div>

      {/* Error */}
      {error && (
        <div
          style={{
            margin: '0 14px 10px',
            padding: '8px 10px',
            backgroundColor: 'rgba(239,68,68,0.08)',
            border: '1px solid rgba(239,68,68,0.2)',
            borderRadius: 6,
            fontSize: 11,
            fontFamily: 'monospace',
            color: '#ef4444',
            display: 'flex',
            alignItems: 'flex-start',
            gap: 6,
          }}
        >
          <span className="material-symbols-outlined" style={{ fontSize: 14, marginTop: 1 }}>
            error
          </span>
          <span>{error}</span>
        </div>
      )}

      {/* Results */}
      <div
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '0 14px 14px',
          display: 'flex',
          flexDirection: 'column',
          gap: 10,
        }}
      >
        {!loading && paths.length === 0 && !error && (
          <div
            style={{
              textAlign: 'center',
              padding: '24px 10px',
              color: '#475569',
              fontSize: 11,
              fontFamily: 'monospace',
            }}
          >
            Enter source and destination IPs to trace network paths.
          </div>
        )}

        {paths.map((path, idx) => (
          <PathCard key={idx} path={path} index={idx} />
        ))}
      </div>
    </div>
  );
};

/* ---- Sub-components ---- */

interface IPFieldProps {
  label: string;
  value: string;
  onChange: (v: string) => void;
  onKeyDown: (e: React.KeyboardEvent) => void;
  resolved?: ResolvedIP;
  onResolve: () => void;
}

const IPField: React.FC<IPFieldProps> = ({ label, value, onChange, onKeyDown, resolved, onResolve }) => (
  <div>
    <label
      style={{
        fontSize: 10,
        fontFamily: 'monospace',
        color: '#64748b',
        textTransform: 'uppercase',
        letterSpacing: 0.5,
        display: 'block',
        marginBottom: 4,
      }}
    >
      {label}
    </label>
    <div style={{ display: 'flex', gap: 4 }}>
      <input
        type="text"
        placeholder="e.g. 10.0.1.1"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={onKeyDown}
        style={{
          flex: 1,
          backgroundColor: 'rgba(224,159,62,0.06)',
          border: '1px solid rgba(224,159,62,0.15)',
          borderRadius: 6,
          padding: '6px 10px',
          color: '#e8e0d4',
          fontSize: 12,
          fontFamily: 'monospace',
          outline: 'none',
          minWidth: 0,
        }}
      />
      <button
        onClick={onResolve}
        disabled={!value.trim() || (resolved?.loading ?? false)}
        title="Resolve hostname"
        style={{
          backgroundColor: 'rgba(224,159,62,0.08)',
          border: '1px solid rgba(224,159,62,0.15)',
          borderRadius: 6,
          padding: '4px 8px',
          color: '#e09f3e',
          fontSize: 11,
          fontFamily: 'monospace',
          cursor: !value.trim() ? 'not-allowed' : 'pointer',
          opacity: !value.trim() ? 0.4 : 1,
          whiteSpace: 'nowrap',
          display: 'flex',
          alignItems: 'center',
          gap: 3,
          transition: 'background-color 0.15s',
        }}
      >
        <span className="material-symbols-outlined" style={{ fontSize: 13 }}>
          dns
        </span>
        {resolved?.loading ? '...' : 'Resolve'}
      </button>
    </div>
    {resolved && !resolved.loading && resolved.hostname && (
      <div
        style={{
          marginTop: 3,
          fontSize: 10,
          fontFamily: 'monospace',
          color: '#e09f3e',
          opacity: 0.8,
          display: 'flex',
          alignItems: 'center',
          gap: 4,
        }}
      >
        <span className="material-symbols-outlined" style={{ fontSize: 11 }}>
          check_circle
        </span>
        {resolved.hostname}
      </div>
    )}
    {resolved && !resolved.loading && !resolved.hostname && (
      <div
        style={{
          marginTop: 3,
          fontSize: 10,
          fontFamily: 'monospace',
          color: '#64748b',
        }}
      >
        Could not resolve hostname
      </div>
    )}
  </div>
);

interface PathCardProps {
  path: TopologyPath;
  index: number;
}

const PathCard: React.FC<PathCardProps> = ({ path, index }) => {
  const confidencePct = Math.round(path.confidence * 100);
  const confidenceColor =
    confidencePct >= 80 ? '#22c55e' : confidencePct >= 50 ? '#f59e0b' : '#ef4444';

  return (
    <div
      style={{
        backgroundColor: 'rgba(224,159,62,0.04)',
        border: '1px solid rgba(224,159,62,0.12)',
        borderRadius: 10,
        padding: 16,
      }}
    >
      {/* Card header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 10,
        }}
      >
        <span
          style={{
            fontSize: 11,
            fontFamily: 'monospace',
            fontWeight: 600,
            color: '#e8e0d4',
          }}
        >
          Path {index + 1}
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span
            style={{
              fontSize: 10,
              fontFamily: 'monospace',
              color: '#8a7e6b',
            }}
          >
            {path.latency_ms.toFixed(1)} ms
          </span>
          <span
            style={{
              fontSize: 10,
              fontFamily: 'monospace',
              fontWeight: 600,
              color: confidenceColor,
            }}
          >
            {confidencePct}%
          </span>
        </div>
      </div>

      {/* Hops */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
        {path.hops.map((hop, hopIdx) => (
          <React.Fragment key={hopIdx}>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '5px 8px',
                borderRadius: 5,
                backgroundColor:
                  hopIdx === 0 || hopIdx === path.hops.length - 1
                    ? 'rgba(224,159,62,0.06)'
                    : 'transparent',
              }}
            >
              <span
                style={{
                  fontSize: 9,
                  fontFamily: 'monospace',
                  fontWeight: 600,
                  color: '#e09f3e',
                  minWidth: 14,
                  textAlign: 'center',
                }}
              >
                {hopIdx + 1}
              </span>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
                <span
                  style={{
                    fontSize: 11,
                    fontFamily: 'monospace',
                    fontWeight: 500,
                    color: '#e8e0d4',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {hop.device_name}
                </span>
                <span
                  style={{
                    fontSize: 10,
                    fontFamily: 'monospace',
                    color: '#64748b',
                  }}
                >
                  {hop.ip}
                </span>
              </div>
            </div>
            {hopIdx < path.hops.length - 1 && (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  padding: '2px 0',
                }}
              >
                <span
                  className="material-symbols-outlined"
                  style={{ fontSize: 14, color: 'rgba(224,159,62,0.35)' }}
                >
                  arrow_forward
                </span>
              </div>
            )}
          </React.Fragment>
        ))}
      </div>
    </div>
  );
};

export default PathQueryPanel;
