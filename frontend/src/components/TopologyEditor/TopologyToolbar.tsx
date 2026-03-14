import React from 'react';
import ExportMenu from './ExportMenu';

type ExportFormat = 'png' | 'svg' | 'pdf' | 'json';

interface TopologyToolbarProps {
  onSave: () => void;
  onExport?: (format: ExportFormat) => void;
  onDesigns: () => void;
  onTracePath: () => void;
  onApply?: () => void;
  onUndo?: () => void;
  onRedo?: () => void;
  onDeleteSelected?: () => void;
  canUndo?: boolean;
  canRedo?: boolean;
  hasSelection?: boolean;
  saving?: boolean;
  applying?: boolean;
  tracePathActive?: boolean;
  designName?: string;
}

/* ── shared style tokens ─────────────────────────────────── */
const BTN =
  'flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-[11px] font-mono font-medium border transition-colors disabled:opacity-30 disabled:cursor-not-allowed';
const BTN_BG = { backgroundColor: '#1e1b15', borderColor: '#3d3528', color: '#e8e0d4' };
const BTN_HOVER = 'hover:border-[#e09f3e]/40';
const ICON = 'material-symbols-outlined';
const ICON_SIZE = { fontSize: 15 };
const ICON_COLOR = { ...ICON_SIZE, color: '#e09f3e' };
const DIVIDER = 'w-px h-5 mx-1';
const DIVIDER_BG = { backgroundColor: '#3d3528' };

const TopologyToolbar: React.FC<TopologyToolbarProps> = ({
  onSave,
  onExport,
  onDesigns,
  onTracePath,
  onApply,
  onUndo,
  onRedo,
  onDeleteSelected,
  canUndo,
  canRedo,
  hasSelection,
  saving,
  applying,
  tracePathActive,
  designName,
}) => {
  return (
    <div
      className="flex items-center gap-1.5 px-4 py-2 border-b"
      style={{ backgroundColor: '#1a1814', borderColor: '#3d3528' }}
    >
      {/* ── Title ───────────────────────────────────────── */}
      <span className={ICON} style={{ ...ICON_SIZE, color: '#e09f3e', marginRight: 4 }}>
        device_hub
      </span>
      <span className="text-[12px] font-mono font-semibold mr-3" style={{ color: '#e8e0d4' }}>
        Topology Editor
      </span>

      {/* ── Group 1: Edit ────────────────────────────────── */}
      <div className={DIVIDER} style={DIVIDER_BG} />

      {onUndo && (
        <button
          onClick={onUndo}
          disabled={!canUndo}
          title="Undo (Ctrl+Z)"
          className={`${BTN} ${BTN_HOVER}`}
          style={BTN_BG}
        >
          <span className={ICON} style={ICON_COLOR}>undo</span>
        </button>
      )}

      {onRedo && (
        <button
          onClick={onRedo}
          disabled={!canRedo}
          title="Redo (Ctrl+Shift+Z)"
          className={`${BTN} ${BTN_HOVER}`}
          style={BTN_BG}
        >
          <span className={ICON} style={ICON_COLOR}>redo</span>
        </button>
      )}

      {onDeleteSelected && (
        <button
          onClick={onDeleteSelected}
          disabled={!hasSelection}
          title="Delete selected (Del)"
          className={`${BTN} hover:border-red-500/40`}
          style={{
            ...BTN_BG,
            color: hasSelection ? '#ef4444' : '#e8e0d4',
          }}
        >
          <span className={ICON} style={{ ...ICON_SIZE, color: hasSelection ? '#ef4444' : '#e09f3e' }}>
            delete
          </span>
        </button>
      )}

      {/* ── Group 2: File ────────────────────────────────── */}
      <div className={DIVIDER} style={DIVIDER_BG} />

      <button
        onClick={onSave}
        disabled={saving}
        title="Save design"
        className={`${BTN} ${BTN_HOVER}`}
        style={BTN_BG}
      >
        <span className={ICON} style={ICON_COLOR}>save</span>
        {saving ? 'Saving…' : 'Save'}
      </button>

      {onExport && <ExportMenu onExport={onExport} />}

      {/* ── Group 3: Navigate ────────────────────────────── */}
      <div className={DIVIDER} style={DIVIDER_BG} />

      <button
        onClick={onDesigns}
        title="Design Manager"
        className={`${BTN} ${BTN_HOVER}`}
        style={BTN_BG}
      >
        <span className={ICON} style={ICON_COLOR}>folder_open</span>
        Designs
      </button>

      <button
        onClick={onTracePath}
        title="Trace Path"
        className={`${BTN} ${BTN_HOVER}`}
        style={{
          ...BTN_BG,
          ...(tracePathActive
            ? { borderColor: '#e09f3e', color: '#e09f3e', backgroundColor: 'rgba(224,159,62,0.12)' }
            : {}),
        }}
      >
        <span className={ICON} style={ICON_COLOR}>route</span>
        Trace Path
      </button>

      {/* ── Spacer ───────────────────────────────────────── */}
      <div className="flex-1" />

      {/* ── Primary CTA: Apply ───────────────────────────── */}
      {onApply && (
        <button
          onClick={onApply}
          disabled={applying}
          className={`${BTN} font-semibold disabled:opacity-50`}
          style={{
            backgroundColor: 'rgba(34,197,94,0.15)',
            color: '#22c55e',
            borderColor: 'rgba(34,197,94,0.3)',
          }}
        >
          <span className={ICON} style={{ ...ICON_SIZE, color: '#22c55e' }}>
            {applying ? 'sync' : 'published_with_changes'}
          </span>
          {applying
            ? 'Applying…'
            : designName
              ? 'Apply to Infrastructure'
              : 'Promote to Infrastructure'}
        </button>
      )}
    </div>
  );
};

export default TopologyToolbar;
