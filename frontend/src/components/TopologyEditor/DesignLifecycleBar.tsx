import { useState } from 'react';
import type { TopologyDesign, DesignStatus } from '../../types';
import ExportMenu from './ExportMenu';

type ExportFormat = 'png' | 'svg' | 'pdf' | 'json';

interface DesignLifecycleBarProps {
  design: TopologyDesign | null;
  onStatusChange: (status: DesignStatus) => void;
  onExport: (format: ExportFormat) => void;
  onRename: (newName: string) => void;
  onSimulate?: () => void;
  simulationPassed?: boolean;
}

const STATUS_COLORS: Record<DesignStatus, { bg: string; text: string; label: string }> = {
  draft: { bg: 'rgba(100,116,139,0.2)', text: '#8a7e6b', label: 'Draft' },
  reviewed: { bg: 'rgba(59,130,246,0.2)', text: '#60a5fa', label: 'Reviewed' },
  simulated: { bg: 'rgba(168,85,247,0.2)', text: '#c084fc', label: 'Simulated' },
  approved: { bg: 'rgba(34,197,94,0.2)', text: '#4ade80', label: 'Approved' },
  parked: { bg: 'rgba(245,158,11,0.2)', text: '#fbbf24', label: 'Parked' },
  applied: { bg: 'rgba(16,185,129,0.2)', text: '#34d399', label: 'Applied' },
  verified: { bg: 'rgba(224,159,62,0.2)', text: '#e09f3e', label: 'Verified' },
};

const TRANSITIONS: Record<DesignStatus, { label: string; next: DesignStatus; icon: string }[]> = {
  draft: [{ label: 'Mark Reviewed', next: 'reviewed', icon: 'rate_review' }],
  reviewed: [
    { label: 'Simulate', next: 'simulated', icon: 'science' },
    { label: 'Park', next: 'parked', icon: 'pause_circle' },
  ],
  simulated: [{ label: 'Approve', next: 'approved', icon: 'verified' }],
  approved: [
    { label: 'Apply to Infrastructure', next: 'applied', icon: 'rocket_launch' },
    { label: 'Park', next: 'parked', icon: 'pause_circle' },
  ],
  parked: [{ label: 'Resume to Draft', next: 'draft', icon: 'play_circle' }],
  applied: [{ label: 'Mark Verified', next: 'verified', icon: 'check_circle' }],
  verified: [],
};

/* ── shared style tokens (same as TopologyToolbar) ───────── */
const BTN =
  'flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-body-xs font-mono font-medium border transition-colors disabled:opacity-30 disabled:cursor-not-allowed';
const ICON = 'material-symbols-outlined';
const ICON_SIZE = { fontSize: 15 };

export default function DesignLifecycleBar({
  design,
  onStatusChange,
  onExport,
  onRename,
  onSimulate,
  simulationPassed,
}: DesignLifecycleBarProps) {
  const [editing, setEditing] = useState(false);
  const [nameInput, setNameInput] = useState('');

  if (!design) return null;

  const status = design.status as DesignStatus;
  const colors = STATUS_COLORS[status];
  const transitions = TRANSITIONS[status] || [];

  const handleStartEdit = () => {
    setNameInput(design.name);
    setEditing(true);
  };

  const handleFinishEdit = () => {
    if (nameInput.trim() && nameInput !== design.name) {
      onRename(nameInput.trim());
    }
    setEditing(false);
  };

  const handleTransition = (next: DesignStatus) => {
    if (next === 'simulated' && onSimulate) {
      onSimulate();
      return;
    }
    onStatusChange(next);
  };

  return (
    <div
      className="flex items-center gap-2 px-4 py-1.5 border-b"
      style={{ background: '#0a1a1f', borderColor: 'rgba(224,159,62,0.15)' }}
    >
      {/* Design name */}
      {editing ? (
        <input
          autoFocus
          value={nameInput}
          onChange={(e) => setNameInput(e.target.value)}
          onBlur={handleFinishEdit}
          onKeyDown={(e) => e.key === 'Enter' && handleFinishEdit()}
          className="bg-transparent border border-amber-800 rounded-md px-2 py-0.5 text-body-xs font-mono text-white outline-none"
          style={{ minWidth: 140 }}
        />
      ) : (
        <button
          onClick={handleStartEdit}
          className="text-body-xs font-mono font-medium text-white hover:text-amber-300 transition-colors flex items-center gap-1"
        >
          <span className={ICON} style={{ ...ICON_SIZE, color: '#e09f3e' }}>edit</span>
          {design.name}
        </button>
      )}

      {/* Status badge */}
      <span
        className="text-body-xs font-mono font-semibold px-2 py-0.5 rounded-full uppercase tracking-wide"
        style={{ background: colors.bg, color: colors.text }}
      >
        {colors.label}
      </span>

      {/* Version */}
      <span className="text-body-xs font-mono text-gray-500">v{design.version}</span>

      <div className="flex-1" />

      {/* Transition buttons */}
      {transitions.map((t) => {
        const disabled = t.next === 'approved' && !simulationPassed;
        return (
          <button
            key={t.next}
            onClick={() => handleTransition(t.next)}
            disabled={disabled}
            className={BTN}
            style={{
              background: disabled ? 'rgba(100,116,139,0.1)' : 'rgba(224,159,62,0.15)',
              color: disabled ? '#475569' : '#e09f3e',
              borderColor: disabled ? 'rgba(100,116,139,0.15)' : 'rgba(224,159,62,0.25)',
              cursor: disabled ? 'not-allowed' : 'pointer',
            }}
            title={disabled ? 'Run simulation first' : t.label}
          >
            <span className={ICON} style={{ ...ICON_SIZE, color: disabled ? '#475569' : '#e09f3e' }}>
              {t.icon}
            </span>
            {t.label}
          </button>
        );
      })}

      {/* Export dropdown */}
      <ExportMenu onExport={onExport} />

      {/* Updated timestamp */}
      <span className="text-body-xs font-mono text-gray-600">
        {new Date(design.updated_at).toLocaleString()}
      </span>
    </div>
  );
}
