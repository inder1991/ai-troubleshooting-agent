import React from 'react';
import { WF_COLORS } from './workflowConfigs';

interface PlaybackBarProps {
  isPlaying: boolean;
  elapsed: number;
  totalDuration: number;
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
    <div
      className="px-6 py-4 shrink-0 border-t"
      style={{ backgroundColor: WF_COLORS.panelBg, borderColor: WF_COLORS.border }}
    >
      {/* Phase info */}
      <div className="flex items-center gap-3 mb-3">
        <span
          className="text-[10px] uppercase tracking-widest font-bold"
          style={{ color: WF_COLORS.amber, fontFamily: 'DM Sans, system-ui' }}
        >
          {phaseName}
        </span>
        <span className="text-xs" style={{ color: WF_COLORS.mutedText }}>
          {phaseDescription}
        </span>
      </div>

      {/* Controls + timeline */}
      <div className="flex items-center gap-4">
        {/* Play/Pause */}
        <button
          onClick={onPlayPause}
          className="w-8 h-8 rounded-full bg-[#e09f3e]/10 border border-[#e09f3e]/30 flex items-center justify-center hover:bg-[#e09f3e]/20 transition-colors"
          aria-label={isPlaying ? 'Pause' : 'Play'}
        >
          <span className="material-symbols-outlined text-sm" style={{ color: WF_COLORS.amber }}>
            {isPlaying ? 'pause' : 'play_arrow'}
          </span>
        </button>

        {/* Reset */}
        <button
          onClick={onReset}
          className="w-8 h-8 rounded-full flex items-center justify-center hover:opacity-80 transition-opacity"
          style={{ backgroundColor: WF_COLORS.cardBg, border: `1px solid ${WF_COLORS.border}` }}
          aria-label="Reset"
        >
          <span className="material-symbols-outlined text-sm" style={{ color: WF_COLORS.mutedText }}>
            replay
          </span>
        </button>

        {/* Timeline scrubber */}
        <div
          className="flex-1 relative h-1.5 rounded-full cursor-pointer group"
          style={{ backgroundColor: WF_COLORS.cardBg }}
          onClick={(e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            const pct = (e.clientX - rect.left) / rect.width;
            onSeek(pct * totalDuration);
          }}
        >
          <div
            className="absolute inset-y-0 left-0 rounded-full transition-all duration-100"
            style={{ width: `${progress}%`, backgroundColor: WF_COLORS.amber }}
          />
          <div
            className="absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full opacity-0 group-hover:opacity-100 transition-opacity"
            style={{
              left: `${progress}%`,
              transform: 'translate(-50%, -50%)',
              backgroundColor: WF_COLORS.amber,
              border: `2px solid ${WF_COLORS.pageBg}`,
              boxShadow: `0 0 6px ${WF_COLORS.amber}`,
            }}
          />
        </div>

        {/* Time display */}
        <span
          className="text-xs font-mono w-20 text-right"
          style={{ color: WF_COLORS.mutedText }}
        >
          {formatTime(elapsed)} / {formatTime(totalDuration)}
        </span>
      </div>
    </div>
  );
};

export default PlaybackBar;
