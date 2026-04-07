import React from 'react';

interface HowItWorksViewProps {
  onGoHome: () => void;
}

const HowItWorksView: React.FC<HowItWorksViewProps> = ({ onGoHome }) => {
  return (
    <div className="flex flex-col h-full bg-[#0f2023] text-slate-300">
      <header className="h-14 border-b border-slate-800 flex items-center gap-4 px-6 shrink-0">
        <button onClick={onGoHome} className="text-slate-400 hover:text-white transition-colors">
          <span className="material-symbols-outlined">arrow_back</span>
        </button>
        <h1 className="text-xl font-bold text-white">How It Works</h1>
      </header>
      <div className="flex-1 flex items-center justify-center text-slate-500">
        Animation coming soon
      </div>
    </div>
  );
};

export default HowItWorksView;
