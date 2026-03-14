import React from 'react';
import type { ValidationError } from '../../utils/networkValidation';

interface ValidationPanelProps {
  errors: ValidationError[];
  onClickError: (nodeId: string) => void;
  onDismiss: () => void;
}

const ValidationPanel: React.FC<ValidationPanelProps> = ({ errors, onClickError, onDismiss }) => {
  if (errors.length === 0) return null;

  const errorCount = errors.filter((e) => e.severity === 'error').length;
  const warnCount = errors.filter((e) => e.severity === 'warning').length;

  return (
    <div
      className="border-t p-3 overflow-y-auto"
      style={{ backgroundColor: '#0f1a1e', borderColor: '#3d3528', maxHeight: '200px' }}
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span
            className="material-symbols-outlined text-base"
            style={{ color: '#ef4444' }}
          >
            error
          </span>
          <span className="text-xs font-mono font-semibold" style={{ color: '#e8e0d4' }}>
            {errorCount > 0 && <span style={{ color: '#ef4444' }}>{errorCount} error{errorCount !== 1 ? 's' : ''}</span>}
            {errorCount > 0 && warnCount > 0 && ', '}
            {warnCount > 0 && <span style={{ color: '#f59e0b' }}>{warnCount} warning{warnCount !== 1 ? 's' : ''}</span>}
          </span>
        </div>
        <button
          onClick={onDismiss}
          className="text-xs font-mono px-2 py-1 rounded transition-colors hover:bg-white/5"
          style={{ color: '#64748b' }}
        >
          Dismiss
        </button>
      </div>
      <div className="flex flex-col gap-1">
        {errors.map((err, i) => (
          <button
            key={i}
            onClick={() => err.nodeId && onClickError(err.nodeId)}
            className="flex items-start gap-2 text-left px-2 py-1.5 rounded transition-colors hover:bg-white/5 text-xs font-mono"
            style={{ color: err.severity === 'error' ? '#ef4444' : err.severity === 'warning' ? '#f59e0b' : '#64748b' }}
          >
            <span
              className="material-symbols-outlined text-sm mt-0.5 flex-shrink-0"
            >
              {err.severity === 'error' ? 'cancel' : err.severity === 'warning' ? 'warning' : 'info'}
            </span>
            <span>{err.message}</span>
          </button>
        ))}
      </div>
    </div>
  );
};

export default ValidationPanel;
