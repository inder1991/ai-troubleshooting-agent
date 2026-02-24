import React from 'react';
import { usePhaseTracker } from '../../hooks/usePhaseTracker';
import type { PhaseSection } from './Investigator';

interface PhaseBreadcrumbsProps {
  phases: PhaseSection[];
  scrollRef: React.RefObject<HTMLDivElement | null>;
}

export const PhaseBreadcrumbs: React.FC<PhaseBreadcrumbsProps> = ({ phases, scrollRef }) => {
  const activePhaseId = usePhaseTracker(scrollRef);

  if (phases.length <= 1) return null;

  const handleClick = (phaseId: string) => {
    document.getElementById(phaseId)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  return (
    <div className="phase-breadcrumb-bar sticky top-0 z-40 h-8 flex items-center gap-1 px-3 backdrop-blur-md bg-slate-900/70 border-b border-slate-800/50 overflow-x-auto whitespace-nowrap scrollbar-hide"
      style={{
        maskImage: 'linear-gradient(to right, black 85%, transparent 100%)',
        WebkitMaskImage: 'linear-gradient(to right, black 85%, transparent 100%)',
      }}
    >
      {phases.map((phase, i) => {
        const isActive = phase.phaseId === activePhaseId;
        const isComplete = phase.isComplete;

        return (
          <React.Fragment key={phase.phaseId}>
            {i > 0 && <span className="text-[9px] text-slate-600">/</span>}
            <button
              onClick={() => handleClick(phase.phaseId)}
              className={`text-[9px] font-bold uppercase tracking-wider whitespace-nowrap transition-colors flex items-center gap-1 ${
                isActive
                  ? 'text-[#07b6d5] font-bold'
                  : isComplete
                    ? 'text-slate-500 hover:text-slate-400'
                    : 'text-slate-600 hover:text-slate-500'
              }`}
            >
              {isActive && <span className="w-1 h-1 rounded-full bg-[#07b6d5]" />}
              {phase.phase.replace(/_/g, ' ')}
            </button>
          </React.Fragment>
        );
      })}
    </div>
  );
};
