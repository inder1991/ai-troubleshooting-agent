import React from 'react';

interface PlaybackBarProps {
  isPlaying: boolean;
  elapsed: number;      // seconds
  totalDuration: number; // seconds
  phaseName: string;
  phaseDescription: string;
  onPlayPause: () => void;
  onReset: () => void;
  onSeek: (time: number) => void;
}

const formatTime = (s: number) => {
  const mins = Math.floor(s / 60);
  const secs = Math.floor(s % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
};

const PlaybackBar: React.FC<PlaybackBarProps> = ({
  isPlaying, elapsed, totalDuration, phaseName, phaseDescription,
  onPlayPause, onReset, onSeek,
}) => {
  const progress = totalDuration > 0 ? (elapsed / totalDuration) * 100 : 0;

  return (
    <div className="border-t border-slate-800 bg-[#0a1a1f] px-6 py-4 shrink-0">
      {/* Phase info */}
      <div className="flex items-center gap-3 mb-3">
        <span className="text-[10px] uppercase tracking-widest text-[#07b6d5] font-bold">
          {phaseName}
        </span>
        <span className="text-xs text-slate-400">{phaseDescription}</span>
      </div>

      {/* Controls + timeline */}
      <div className="flex items-center gap-4">
        {/* Play/Pause */}
        <button
          onClick={onPlayPause}
          className="w-8 h-8 rounded-full bg-[#07b6d5]/10 border border-[#07b6d5]/30 flex items-center justify-center hover:bg-[#07b6d5]/20 transition-colors"
          aria-label={isPlaying ? 'Pause' : 'Play'}
        >
          <span className="material-symbols-outlined text-[#07b6d5] text-sm">
            {isPlaying ? 'pause' : 'play_arrow'}
          </span>
        </button>

        {/* Reset */}
        <button
          onClick={onReset}
          className="w-8 h-8 rounded-full bg-slate-800/50 border border-slate-700 flex items-center justify-center hover:bg-slate-700/50 transition-colors"
          aria-label="Reset"
        >
          <span className="material-symbols-outlined text-slate-400 text-sm">replay</span>
        </button>

        {/* Timeline scrubber */}
        <div className="flex-1 relative h-1.5 bg-slate-800 rounded-full cursor-pointer group"
          onClick={(e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            const pct = (e.clientX - rect.left) / rect.width;
            onSeek(pct * totalDuration);
          }}
        >
          {/* Progress fill */}
          <div
            className="absolute inset-y-0 left-0 bg-[#07b6d5] rounded-full transition-all duration-100"
            style={{ width: `${progress}%` }}
          />
          {/* Scrubber handle */}
          <div
            className="absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-[#07b6d5] border-2 border-[#0f2023] shadow-[0_0_6px_#07b6d5] opacity-0 group-hover:opacity-100 transition-opacity"
            style={{ left: `${progress}%`, transform: `translate(-50%, -50%)` }}
          />
        </div>

        {/* Time display */}
        <span className="text-xs font-mono text-slate-500 w-20 text-right">
          {formatTime(elapsed)} / {formatTime(totalDuration)}
        </span>
      </div>
    </div>
  );
};

export default PlaybackBar;
