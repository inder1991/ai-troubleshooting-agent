import React from 'react';

interface ClosureStepCardProps {
  stepNumber: 1 | 2 | 3;
  title: string;
  icon: string;
  completed: boolean;
  active: boolean;
  children: React.ReactNode;
}

const ClosureStepCard: React.FC<ClosureStepCardProps> = ({
  stepNumber,
  title,
  icon,
  completed,
  active,
  children,
}) => {
  return (
    <div className={`rounded-lg overflow-hidden border-l-[3px] ${
      completed
        ? 'border-l-green-500 bg-green-500/5 border border-l-0 border-green-500/20'
        : active
        ? 'border-l-violet-500 bg-violet-500/5 border border-l-0 border-violet-500/20'
        : 'border-l-slate-600 bg-slate-900/40 border border-l-0 border-slate-700/50'
    }`}>
      <div className="px-4 py-2.5 flex items-center gap-2">
        {completed ? (
          <span className="w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold bg-green-500 text-white shrink-0">
            <span className="material-symbols-outlined text-xs" style={{ fontFamily: 'Material Symbols Outlined' }}>check</span>
          </span>
        ) : (
          <span className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold shrink-0 ${
            active ? 'bg-violet-500 text-white' : 'bg-slate-700 text-slate-400'
          }`}>
            {stepNumber}
          </span>
        )}
        <span className={`material-symbols-outlined text-sm ${
          completed ? 'text-green-400' : active ? 'text-violet-400' : 'text-slate-500'
        }`} style={{ fontFamily: 'Material Symbols Outlined' }}>{icon}</span>
        <span className={`text-[11px] font-bold uppercase tracking-wider ${
          completed ? 'text-green-400' : active ? 'text-violet-400' : 'text-slate-500'
        }`}>{title}</span>
        {active && (
          <span className="w-2 h-2 rounded-full bg-violet-500 animate-pulse ml-auto" />
        )}
      </div>
      <div className="px-4 pb-3">
        {children}
      </div>
    </div>
  );
};

export default ClosureStepCard;
