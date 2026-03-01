import React from 'react';

interface AgentMatrixHeaderProps {
  onGoHome: () => void;
}

const AgentMatrixHeader: React.FC<AgentMatrixHeaderProps> = ({ onGoHome }) => {
  return (
    <header className="flex items-center gap-4 px-8 py-5 border-b" style={{ borderColor: '#224349', backgroundColor: '#0a1214' }}>
      <button
        onClick={onGoHome}
        className="flex items-center justify-center w-9 h-9 rounded-lg border transition-colors hover:text-white"
        style={{ borderColor: '#224349', color: '#64748b' }}
        title="Back to Dashboard"
      >
        <span className="material-symbols-outlined text-lg" style={{ fontFamily: 'Material Symbols Outlined' }}>arrow_back</span>
      </button>

      <div className="flex flex-col gap-0.5">
        <div className="flex items-center gap-3">
          <span className="material-symbols-outlined text-2xl" style={{ fontFamily: 'Material Symbols Outlined', color: '#07b6d5' }}>smart_toy</span>
          <h1 className="text-xl font-bold tracking-wide text-white">NEURAL DIRECTORY HUD</h1>
        </div>
        <p className="text-[10px] font-mono tracking-[0.2em] uppercase ml-10" style={{ color: '#07b6d5', opacity: 0.7 }}>
          /// LIVE WORKFORCE MATRIX /// AUTONOMOUS DIAGNOSTICS ///
        </p>
      </div>
    </header>
  );
};

export default AgentMatrixHeader;
