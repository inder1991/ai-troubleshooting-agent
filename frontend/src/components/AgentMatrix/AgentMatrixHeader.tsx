import React from 'react';

interface AgentMatrixHeaderProps {
  onGoHome: () => void;
}

const AgentMatrixHeader: React.FC<AgentMatrixHeaderProps> = ({ onGoHome }) => {
  return (
    <header className="flex items-center gap-3 px-8 py-4 border-b" style={{ borderColor: '#3d3528', backgroundColor: '#13110d' }}>
      <span className="material-symbols-outlined text-xl" style={{ color: '#e09f3e' }}>smart_toy</span>
      <div>
        <h1 className="text-lg font-bold text-white">Agent Fleet</h1>
        <p className="text-body-xs text-slate-400">Status and configuration for all diagnostic agents</p>
      </div>
    </header>
  );
};

export default AgentMatrixHeader;
