import React from 'react';
import LiveTopologyView from './LiveTopologyView';

interface FullScreenTopologyProps {
  onGoBack: () => void;
}

const FullScreenTopology: React.FC<FullScreenTopologyProps> = ({ onGoBack }) => {
  return (
    <div className="flex flex-col h-full w-full overflow-hidden" style={{ background: '#1a1814' }}>
      {/* Minimal header — just back button + title */}
      <header
        className="flex items-center gap-3 px-4 py-2 shrink-0"
        style={{ background: '#13110d', borderBottom: '1px solid #3d3528' }}
      >
        <button
          onClick={onGoBack}
          className="flex items-center justify-center w-8 h-8 rounded-lg transition-colors"
          style={{ color: '#64748b', border: '1px solid #3d3528' }}
          onMouseEnter={e => { e.currentTarget.style.color = '#e09f3e'; e.currentTarget.style.borderColor = '#e09f3e'; }}
          onMouseLeave={e => { e.currentTarget.style.color = '#64748b'; e.currentTarget.style.borderColor = '#3d3528'; }}
          title="Back to Observatory"
        >
          <span className="material-symbols-outlined text-[16px]">arrow_back</span>
        </button>
        <span className="material-symbols-outlined text-[18px]" style={{ color: '#e09f3e' }}>device_hub</span>
        <span style={{ color: 'white', fontSize: 14, fontWeight: 600 }}>Live Network Topology</span>
        <span style={{ color: '#64748b', fontSize: 11, marginLeft: 8 }}>Full Screen</span>
      </header>

      {/* Canvas takes ALL remaining space */}
      <div className="flex-1 min-h-0">
        <LiveTopologyView />
      </div>
    </div>
  );
};

export default FullScreenTopology;
