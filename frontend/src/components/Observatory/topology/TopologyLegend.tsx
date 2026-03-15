import React, { useState } from 'react';

const LEGEND_ITEMS = [
  { label: 'L2 Link (LLDP/CDP)', color: '#64748b', dash: false },
  { label: 'L3 Link (P2P)', color: '#3d3528', dash: false },
  { label: 'HA Peer', color: '#f59e0b', dash: true },
  { label: 'GRE/IPsec Tunnel', color: '#0ea5e9', dash: true },
  { label: 'MPLS Circuit', color: '#e09f3e', dash: false, thick: true },
  { label: 'Route (summary)', color: '#3d3528', dash: false, thin: true },
];

const STATUS_ITEMS = [
  { label: 'Healthy', color: '#10b981' },
  { label: 'Degraded', color: '#f59e0b' },
  { label: 'Critical', color: '#ef4444' },
  { label: 'Unknown', color: '#64748b' },
];

const TopologyLegend: React.FC = () => {
  const [open, setOpen] = useState(false);

  return (
    <div style={{ position: 'absolute', bottom: 16, right: 16, zIndex: 20 }}>
      <button
        onClick={() => setOpen(!open)}
        style={{
          background: '#1e1b15', border: '1px solid #3d3528', borderRadius: 6,
          padding: '6px 10px', color: '#8a7e6b', fontSize: 10, cursor: 'pointer',
          display: 'flex', alignItems: 'center', gap: 4,
        }}
      >
        <span className="material-symbols-outlined" style={{ fontSize: 14 }}>info</span>
        Legend
      </button>
      {open && (
        <div style={{
          background: '#1e1b15', border: '1px solid #3d3528', borderRadius: 8,
          padding: 12, marginTop: 4, minWidth: 180,
        }}>
          <div style={{ fontSize: 9, color: '#64748b', fontWeight: 600, marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Links</div>
          {LEGEND_ITEMS.map(item => (
            <div key={item.label} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
              <svg width={24} height={4}>
                <line x1={0} y1={2} x2={24} y2={2} stroke={item.color} strokeWidth={item.thick ? 3 : item.thin ? 1 : 2} strokeDasharray={item.dash ? '4,3' : 'none'} />
              </svg>
              <span style={{ color: '#8a7e6b', fontSize: 10 }}>{item.label}</span>
            </div>
          ))}
          <div style={{ fontSize: 9, color: '#64748b', fontWeight: 600, marginTop: 8, marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Status</div>
          {STATUS_ITEMS.map(item => (
            <div key={item.label} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 3 }}>
              <span style={{ width: 8, height: 8, borderRadius: '50%', background: item.color, flexShrink: 0 }} />
              <span style={{ color: '#8a7e6b', fontSize: 10 }}>{item.label}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default TopologyLegend;
