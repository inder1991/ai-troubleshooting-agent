import React, { useState } from 'react';
import type { DiscoveryCandidate } from './hooks/useMonitorSnapshot';
import { promoteDiscovery, dismissDiscovery } from '../../services/api';

interface Props {
  candidates: DiscoveryCandidate[];
  onRefresh: () => void;
}

const DiscoveryCandidates: React.FC<Props> = ({ candidates, onRefresh }) => {
  const [promotingIp, setPromotingIp] = useState<string | null>(null);
  const [promoteName, setPromoteName] = useState('');

  if (candidates.length === 0) return null;

  const handlePromote = async (ip: string) => {
    if (!promoteName.trim()) return;
    try {
      await promoteDiscovery(ip, promoteName.trim());
      setPromotingIp(null);
      setPromoteName('');
      onRefresh();
    } catch (err) {
      console.error('Failed to promote:', err);
    }
  };

  const handleDismiss = async (ip: string) => {
    try {
      await dismissDiscovery(ip);
      onRefresh();
    } catch (err) {
      console.error('Failed to dismiss:', err);
    }
  };

  return (
    <div className="rounded-lg border" style={{ backgroundColor: '#0a1a1e', borderColor: '#3d3528' }}>
      <div className="flex items-center justify-between px-3 py-2 border-b" style={{ borderColor: '#3d3528' }}>
        <span className="text-xs font-semibold text-white">Discovered Devices</span>
        <span className="text-body-xs font-mono" style={{ color: '#e09f3e' }}>{candidates.length} found</span>
      </div>
      <div className="max-h-48 overflow-y-auto">
        {candidates.map((c) => (
          <div key={c.ip} className="px-3 py-2 border-b" style={{ borderColor: '#1a3038' }}>
            <div className="flex items-center justify-between">
              <div>
                <span className="text-xs font-mono" style={{ color: '#e8e0d4' }}>{c.ip}</span>
                {c.hostname && (
                  <span className="ml-2 text-body-xs" style={{ color: '#64748b' }}>{c.hostname}</span>
                )}
              </div>
              <div className="flex gap-1">
                {promotingIp === c.ip ? (
                  <div className="flex gap-1">
                    <input
                      type="text"
                      value={promoteName}
                      onChange={(e) => setPromoteName(e.target.value)}
                      placeholder="Device name"
                      className="px-2 py-0.5 rounded text-body-xs font-mono w-24 border outline-none"
                      style={{ backgroundColor: '#1a1814', borderColor: '#3d3528', color: '#e8e0d4' }}
                      onKeyDown={(e) => e.key === 'Enter' && handlePromote(c.ip)}
                    />
                    <button
                      onClick={() => handlePromote(c.ip)}
                      className="px-2 py-0.5 rounded text-body-xs font-bold"
                      style={{ backgroundColor: 'rgba(224,159,62,0.15)', color: '#e09f3e' }}
                    >
                      OK
                    </button>
                    <button
                      onClick={() => { setPromotingIp(null); setPromoteName(''); }}
                      className="px-1 py-0.5 rounded text-body-xs"
                      style={{ color: '#64748b' }}
                    >
                      &times;
                    </button>
                  </div>
                ) : (
                  <>
                    <button
                      onClick={() => setPromotingIp(c.ip)}
                      className="px-2 py-0.5 rounded text-body-xs font-bold"
                      style={{ backgroundColor: 'rgba(224,159,62,0.1)', color: '#e09f3e' }}
                    >
                      Add
                    </button>
                    <button
                      onClick={() => handleDismiss(c.ip)}
                      className="px-2 py-0.5 rounded text-body-xs"
                      style={{ color: '#64748b' }}
                    >
                      Dismiss
                    </button>
                  </>
                )}
              </div>
            </div>
            <div className="text-body-xs mt-0.5 font-mono" style={{ color: '#475569' }}>
              via {c.discovered_via}
              {c.source_device_id && ` from ${c.source_device_id}`}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default DiscoveryCandidates;
