import React from 'react';

interface FirewallVerdict {
  device_id: string;
  device_name: string;
  action: string;
  rule_id?: string;
  rule_name?: string;
  confidence: number;
  match_type: string;
  details?: string;
  matched_source?: string;
  matched_destination?: string;
  matched_ports?: string;
  security_grade?: string;
}

interface FirewallVerdictCardProps {
  verdict: FirewallVerdict;
}

const ACTION_STYLES: Record<string, { color: string; bg: string; label: string }> = {
  ALLOW: { color: '#22c55e', bg: 'rgba(34,197,94,0.12)', label: 'ALLOW' },
  DENY: { color: '#ef4444', bg: 'rgba(239,68,68,0.12)', label: 'DENY' },
  DROP: { color: '#ef4444', bg: 'rgba(239,68,68,0.12)', label: 'DROP' },
};

const FirewallVerdictCard: React.FC<FirewallVerdictCardProps> = ({ verdict }) => {
  const actionKey = verdict.action?.toUpperCase() || 'UNKNOWN';
  const style = ACTION_STYLES[actionKey] || {
    color: '#f59e0b',
    bg: 'rgba(245,158,11,0.12)',
    label: actionKey,
  };

  return (
    <div
      className="rounded-lg p-3 font-mono text-xs"
      style={{ backgroundColor: '#1a1814', border: '1px solid #3d3528' }}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-sm" style={{ color: '#f59e0b' }}>
            security
          </span>
          <span style={{ color: '#e8e0d4' }}>{verdict.device_name || verdict.device_id}</span>
        </div>
        <div className="flex items-center gap-2">
          <span
            className="px-2 py-0.5 rounded font-bold tracking-wider"
            style={{ color: style.color, backgroundColor: style.bg }}
          >
            {style.label}
          </span>
          {/* Security Grade */}
          {verdict.action?.toUpperCase() === 'ALLOW' && verdict.matched_source && (
            (() => {
              const srcAny = ['0.0.0.0/0', 'any', '*', ''].includes(verdict.matched_source || '');
              const portAny = ['any', '*', '', '0-65535'].includes(verdict.matched_ports || '');
              const grade = srcAny && portAny ? 'CRITICAL' : srcAny ? 'HIGH' : 'LOW';
              if (grade === 'LOW') return null;
              const gradeColors = { CRITICAL: '#ef4444', HIGH: '#f59e0b' };
              return (
                <span
                  className="px-2 py-0.5 rounded text-body-xs font-bold tracking-wider animate-pulse"
                  style={{
                    color: gradeColors[grade as keyof typeof gradeColors],
                    backgroundColor: `${gradeColors[grade as keyof typeof gradeColors]}20`,
                  }}
                >
                  SEC-WARN
                </span>
              );
            })()
          )}
        </div>
      </div>

      {/* Rule citation */}
      {(verdict.rule_id || verdict.rule_name) && (
        <div className="mb-1.5" style={{ color: '#64748b' }}>
          Rule: {verdict.rule_name || verdict.rule_id}
          {verdict.rule_id && verdict.rule_name && (
            <span className="ml-1 opacity-60">({verdict.rule_id})</span>
          )}
        </div>
      )}

      {/* Match type */}
      <div className="mb-1.5" style={{ color: '#64748b' }}>
        Match: <span style={{ color: '#8a7e6b' }}>{verdict.match_type}</span>
      </div>

      {/* Details */}
      {verdict.details && (
        <div className="mb-1.5" style={{ color: '#64748b' }}>
          {verdict.details}
        </div>
      )}

      {/* Confidence */}
      <div className="flex items-center gap-2 mt-2">
        <div
          className="flex-1 h-1 rounded-full overflow-hidden"
          style={{ backgroundColor: '#1a3a3f' }}
        >
          <div
            className="h-full rounded-full transition-all"
            style={{
              width: `${Math.round(verdict.confidence * 100)}%`,
              backgroundColor: style.color,
            }}
          />
        </div>
        <span style={{ color: '#8a7e6b' }}>
          {Math.round(verdict.confidence * 100)}%
        </span>
      </div>
    </div>
  );
};

export default FirewallVerdictCard;
