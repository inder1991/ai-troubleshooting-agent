import React, { useState } from 'react';
import { runReachabilityMatrix } from '../../services/api';

interface MatrixCell {
  src_zone: string;
  dst_zone: string;
  reachable: string;
  path_count: number;
  confidence: number;
}

const ReachabilityMatrix: React.FC = () => {
  const [zones, setZones] = useState<string[]>([]);
  const [matrix, setMatrix] = useState<MatrixCell[]>([]);
  const [loading, setLoading] = useState(false);

  const handleRun = async () => {
    if (zones.length < 2) return;
    setLoading(true);
    try {
      const result = await runReachabilityMatrix(zones);
      setMatrix(result.matrix || []);
    } finally {
      setLoading(false);
    }
  };

  const cellColor = (reachable: string) => {
    if (reachable === 'yes') return '#22c55e';
    if (reachable === 'no') return '#ef4444';
    return '#64748b';
  };

  return (
    <div className="flex-1 flex flex-col overflow-hidden p-6" style={{ backgroundColor: '#0f2023' }}>
      <h1 className="text-xl font-bold text-white mb-4">Reachability Matrix</h1>
      {/* Zone input */}
      <div className="flex gap-3 mb-4">
        <input
          type="text"
          placeholder="Enter zone IDs comma-separated..."
          onChange={(e) => setZones(e.target.value.split(',').map(z => z.trim()).filter(Boolean))}
          className="flex-1 px-3 py-2 rounded-lg border text-sm font-mono outline-none"
          style={{ backgroundColor: '#0a1a1e', borderColor: '#224349', color: '#e2e8f0' }}
        />
        <button onClick={handleRun} disabled={loading || zones.length < 2}
          className="px-4 py-2 rounded-lg font-semibold text-sm disabled:opacity-50"
          style={{ backgroundColor: '#07b6d5', color: '#0f2023' }}>
          {loading ? 'Computing...' : 'Run Matrix'}
        </button>
      </div>
      {/* Matrix grid */}
      {matrix.length > 0 && (
        <div className="overflow-auto">
          <table className="border-collapse font-mono text-xs">
            <thead>
              <tr>
                <th className="p-2 text-left" style={{ color: '#64748b' }}>From \ To</th>
                {zones.map(z => <th key={z} className="p-2" style={{ color: '#94a3b8' }}>{z}</th>)}
              </tr>
            </thead>
            <tbody>
              {zones.map(src => (
                <tr key={src}>
                  <td className="p-2 font-semibold" style={{ color: '#94a3b8' }}>{src}</td>
                  {zones.map(dst => {
                    if (src === dst) return <td key={dst} className="p-2 text-center" style={{ color: '#64748b' }}>—</td>;
                    const cell = matrix.find(m => m.src_zone === src && m.dst_zone === dst);
                    return (
                      <td key={dst} className="p-2 text-center">
                        <span className="px-2 py-1 rounded font-bold"
                          style={{ color: cellColor(cell?.reachable || 'unknown'),
                            backgroundColor: `${cellColor(cell?.reachable || 'unknown')}15` }}>
                          {cell?.reachable?.toUpperCase() || '?'}
                        </span>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default ReachabilityMatrix;
