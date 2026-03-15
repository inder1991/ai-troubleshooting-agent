import React, { useState } from 'react';

const LEGEND_ITEMS = [
  { label: 'Physical Link (L2/L3)', color: '#22c55e', width: 3 },
  { label: 'WAN / MPLS', color: '#f59e0b', width: 4 },
  { label: 'HA Peer', color: '#f59e0b', width: 2, dash: true },
  { label: 'Tunnel (GRE/IPsec)', color: '#06b6d4', width: 3, dash: true },
  { label: 'Cloud Attachment', color: '#06b6d4', width: 3 },
  { label: 'Load Balancer', color: '#a855f7', width: 2 },
  { label: 'Link Down', color: '#ef4444', width: 4, dash: true },
];

const STATUS_ITEMS = [
  { label: 'Healthy', color: '#22c55e' },
  { label: 'Degraded', color: '#f59e0b' },
  { label: 'Critical', color: '#ef4444' },
  { label: 'Initializing', color: '#e09f3e' },
];

const TYPE_ITEMS = [
  { label: 'Firewall', color: '#ef4444' },
  { label: 'Router', color: '#3b82f6' },
  { label: 'Switch', color: '#10b981' },
  { label: 'Load Balancer', color: '#a855f7' },
  { label: 'Cloud / Transit GW', color: '#f59e0b' },
];

const TopologyLegend: React.FC = () => {
  const [open, setOpen] = useState(false);

  return (
    <div style={{ position: 'absolute', bottom: 16, left: 16, zIndex: 20 }}>
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
              <svg width={24} height={6}>
                <line x1={0} y1={3} x2={24} y2={3} stroke={item.color} strokeWidth={item.width} strokeDasharray={item.dash ? '4,3' : 'none'} />
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
          <div style={{ fontSize: 9, color: '#64748b', fontWeight: 600, marginTop: 8, marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Device Types</div>
          {TYPE_ITEMS.map(item => (
            <div key={item.label} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 3 }}>
              <span style={{
                width: 16, height: 3, borderRadius: 1, background: item.color, flexShrink: 0,
              }} />
              <span style={{ color: '#8a7e6b', fontSize: 10 }}>{item.label}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default TopologyLegend;
