import { useState, useEffect } from 'react';
import type { SimulationResult } from '../../types';
import {
  simulateDesign,
  getSimulationResults,
  simulateConnectivity,
  simulateFirewallPolicy,
} from '../../services/api';

interface SimulationPanelProps {
  designId: string;
  onClose: () => void;
  onSimulationComplete?: (passed: boolean) => void;
}

export default function SimulationPanel({ designId, onClose, onSimulationComplete }: SimulationPanelProps) {
  const [result, setResult] = useState<SimulationResult | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');

  // Ad-hoc connectivity
  const [connSource, setConnSource] = useState('');
  const [connTarget, setConnTarget] = useState('');
  const [connResult, setConnResult] = useState<any>(null);
  const [connRunning, setConnRunning] = useState(false);

  // Ad-hoc firewall
  const [fwSrcIp, setFwSrcIp] = useState('');
  const [fwDstIp, setFwDstIp] = useState('');
  const [fwPort, setFwPort] = useState('80');
  const [fwProto, setFwProto] = useState('tcp');
  const [fwResult, setFwResult] = useState<any>(null);
  const [fwRunning, setFwRunning] = useState(false);

  useEffect(() => {
    getSimulationResults(designId).then(setResult).catch(() => {});
  }, [designId]);

  const handleRunSimulation = async () => {
    setRunning(true);
    setError('');
    try {
      const res = await simulateDesign(designId);
      setResult(res);
      onSimulationComplete?.(res.summary.errors === 0);
    } catch (e: any) {
      setError(e.message || 'Simulation failed');
    } finally {
      setRunning(false);
    }
  };

  const handleConnTest = async () => {
    if (!connSource || !connTarget) return;
    setConnRunning(true);
    try {
      const res = await simulateConnectivity(designId, connSource, connTarget);
      setConnResult(res);
    } catch (e: any) {
      setConnResult({ error: e.message });
    } finally {
      setConnRunning(false);
    }
  };

  const handleFwTest = async () => {
    if (!fwSrcIp || !fwDstIp) return;
    setFwRunning(true);
    try {
      const res = await simulateFirewallPolicy(designId, fwSrcIp, fwDstIp, parseInt(fwPort) || 80, fwProto);
      setFwResult(res);
    } catch (e: any) {
      setFwResult({ error: e.message });
    } finally {
      setFwRunning(false);
    }
  };

  return (
    <div
      className="fixed right-0 top-0 h-full w-[420px] z-40 border-l shadow-2xl overflow-y-auto"
      style={{ background: '#0b1a1f', borderColor: 'rgba(224,159,62,0.15)' }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b" style={{ borderColor: 'rgba(224,159,62,0.1)' }}>
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-purple-400" style={{ fontSize: 20 }}>science</span>
          <h2 className="text-sm font-semibold text-white">What-If Simulation</h2>
        </div>
        <button onClick={onClose} className="text-gray-500 hover:text-white transition-colors">
          <span className="material-symbols-outlined" style={{ fontSize: 18 }}>close</span>
        </button>
      </div>

      <div className="p-4 space-y-5">
        {/* Run Simulation */}
        <section>
          <button
            onClick={handleRunSimulation}
            disabled={running}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-all"
            style={{
              background: running ? 'rgba(168,85,247,0.1)' : 'rgba(168,85,247,0.2)',
              color: running ? '#a78bfa' : '#c084fc',
            }}
          >
            {running ? (
              <>
                <span className="material-symbols-outlined animate-spin" style={{ fontSize: 16 }}>progress_activity</span>
                Running Simulation...
              </>
            ) : (
              <>
                <span className="material-symbols-outlined" style={{ fontSize: 16 }}>play_arrow</span>
                Simulate Design
              </>
            )}
          </button>
          {error && <p className="mt-2 text-xs text-red-400">{error}</p>}
        </section>

        {/* Results */}
        {result && (
          <>
            {/* Summary */}
            <section className="flex items-center gap-3 p-3 rounded-lg" style={{ background: 'rgba(100,116,139,0.06)' }}>
              <span className="flex items-center gap-1 text-xs font-semibold" style={{ color: result.summary.errors > 0 ? '#ef4444' : '#4ade80' }}>
                <span className="material-symbols-outlined" style={{ fontSize: 14 }}>{result.summary.errors > 0 ? 'error' : 'check_circle'}</span>
                {result.summary.errors} errors
              </span>
              <span className="flex items-center gap-1 text-xs font-semibold text-amber-400">
                <span className="material-symbols-outlined" style={{ fontSize: 14 }}>warning</span>
                {result.summary.warnings} warnings
              </span>
              <span className="flex items-center gap-1 text-xs font-semibold text-green-400">
                <span className="material-symbols-outlined" style={{ fontSize: 14 }}>check</span>
                {result.summary.passed} passed
              </span>
            </section>

            {/* Integrity Checks */}
            {result.integrity_checks.length > 0 && (
              <section>
                <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">Integrity Checks</h3>
                <div className="space-y-1">
                  {result.integrity_checks.map((c, i) => (
                    <div
                      key={i}
                      className="flex items-start gap-2 p-2 rounded text-xs"
                      style={{ background: c.severity === 'error' ? 'rgba(239,68,68,0.06)' : 'rgba(245,158,11,0.06)' }}
                    >
                      <span
                        className="material-symbols-outlined mt-0.5"
                        style={{ fontSize: 12, color: c.severity === 'error' ? '#ef4444' : '#f59e0b' }}
                      >
                        {c.severity === 'error' ? 'error' : 'warning'}
                      </span>
                      <div>
                        <span className="font-medium" style={{ color: c.severity === 'error' ? '#fca5a5' : '#fde68a' }}>
                          {c.type.replace(/_/g, ' ')}
                        </span>
                        {c.device && <span className="text-gray-500 ml-1">({c.device})</span>}
                        <p className="text-gray-400 mt-0.5">{c.description}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {/* Connectivity Tests */}
            {result.connectivity_tests.length > 0 && (
              <section>
                <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">Connectivity Tests</h3>
                <div className="space-y-1">
                  {result.connectivity_tests.map((t, i) => (
                    <div
                      key={i}
                      className="flex items-center gap-2 p-2 rounded text-xs"
                      style={{ background: t.result === 'reachable' ? 'rgba(34,197,94,0.06)' : 'rgba(239,68,68,0.06)' }}
                    >
                      <span
                        className="material-symbols-outlined"
                        style={{ fontSize: 14, color: t.result === 'reachable' ? '#4ade80' : '#ef4444' }}
                      >
                        {t.result === 'reachable' ? 'check_circle' : 'cancel'}
                      </span>
                      <span className="text-gray-300">{t.source}</span>
                      <span className="text-gray-600">→</span>
                      <span className="text-gray-300">{t.target}</span>
                      {t.blocked_by && <span className="text-red-400 ml-auto text-[10px]">{t.blocked_by}</span>}
                    </div>
                  ))}
                </div>
              </section>
            )}
          </>
        )}

        {/* Divider */}
        <hr style={{ borderColor: 'rgba(224,159,62,0.08)' }} />

        {/* Ad-hoc Connectivity Test */}
        <section>
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">Test Connectivity</h3>
          <div className="space-y-2">
            <input
              placeholder="Source node ID"
              value={connSource}
              onChange={(e) => setConnSource(e.target.value)}
              className="w-full bg-transparent border rounded px-2 py-1.5 text-xs text-white placeholder-gray-600 outline-none"
              style={{ borderColor: 'rgba(224,159,62,0.2)' }}
            />
            <input
              placeholder="Target node ID"
              value={connTarget}
              onChange={(e) => setConnTarget(e.target.value)}
              className="w-full bg-transparent border rounded px-2 py-1.5 text-xs text-white placeholder-gray-600 outline-none"
              style={{ borderColor: 'rgba(224,159,62,0.2)' }}
            />
            <button
              onClick={handleConnTest}
              disabled={connRunning}
              className="w-full px-3 py-1.5 rounded text-xs font-medium"
              style={{ background: 'rgba(224,159,62,0.15)', color: '#e09f3e' }}
            >
              {connRunning ? 'Testing...' : 'Test Path'}
            </button>
            {connResult && !connResult.error && (
              <div className="p-2 rounded text-xs" style={{ background: connResult.reachable ? 'rgba(34,197,94,0.06)' : 'rgba(239,68,68,0.06)' }}>
                <span style={{ color: connResult.reachable ? '#4ade80' : '#ef4444' }}>
                  {connResult.reachable ? 'Reachable' : 'Blocked'}
                </span>
                {connResult.path?.length > 0 && (
                  <p className="text-gray-400 mt-1">Path: {connResult.path.join(' → ')}</p>
                )}
                {connResult.blocked_by && <p className="text-red-400 mt-1">Blocked by: {connResult.blocked_by}</p>}
              </div>
            )}
            {connResult?.error && <p className="text-xs text-red-400">{connResult.error}</p>}
          </div>
        </section>

        {/* Ad-hoc Firewall Test */}
        <section>
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">Test Firewall Policy</h3>
          <div className="space-y-2">
            <div className="grid grid-cols-2 gap-2">
              <input
                placeholder="Source IP"
                value={fwSrcIp}
                onChange={(e) => setFwSrcIp(e.target.value)}
                className="bg-transparent border rounded px-2 py-1.5 text-xs text-white placeholder-gray-600 outline-none"
                style={{ borderColor: 'rgba(224,159,62,0.2)' }}
              />
              <input
                placeholder="Destination IP"
                value={fwDstIp}
                onChange={(e) => setFwDstIp(e.target.value)}
                className="bg-transparent border rounded px-2 py-1.5 text-xs text-white placeholder-gray-600 outline-none"
                style={{ borderColor: 'rgba(224,159,62,0.2)' }}
              />
              <input
                placeholder="Port"
                value={fwPort}
                onChange={(e) => setFwPort(e.target.value)}
                className="bg-transparent border rounded px-2 py-1.5 text-xs text-white placeholder-gray-600 outline-none"
                style={{ borderColor: 'rgba(224,159,62,0.2)' }}
              />
              <select
                value={fwProto}
                onChange={(e) => setFwProto(e.target.value)}
                className="bg-transparent border rounded px-2 py-1.5 text-xs text-white outline-none"
                style={{ borderColor: 'rgba(224,159,62,0.2)' }}
              >
                <option value="tcp">TCP</option>
                <option value="udp">UDP</option>
                <option value="icmp">ICMP</option>
              </select>
            </div>
            <button
              onClick={handleFwTest}
              disabled={fwRunning}
              className="w-full px-3 py-1.5 rounded text-xs font-medium"
              style={{ background: 'rgba(224,159,62,0.15)', color: '#e09f3e' }}
            >
              {fwRunning ? 'Testing...' : 'Test Policy'}
            </button>
            {fwResult && !fwResult.error && (
              <div className="p-2 rounded text-xs" style={{ background: fwResult.allowed ? 'rgba(34,197,94,0.06)' : 'rgba(239,68,68,0.06)' }}>
                <span style={{ color: fwResult.allowed ? '#4ade80' : '#ef4444' }}>
                  {fwResult.allowed ? 'Allowed' : 'Blocked'}
                </span>
                {fwResult.firewall_id && <span className="text-gray-500 ml-2">by {fwResult.firewall_id}</span>}
                {fwResult.rule_description && <p className="text-gray-400 mt-1">{fwResult.rule_description}</p>}
              </div>
            )}
            {fwResult?.error && <p className="text-xs text-red-400">{fwResult.error}</p>}
          </div>
        </section>
      </div>
    </div>
  );
}
