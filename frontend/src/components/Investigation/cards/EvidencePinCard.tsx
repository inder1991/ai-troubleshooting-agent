import React, { useState } from 'react';
import CausalRoleBadge from './CausalRoleBadge';
import type { EvidencePinV2, EvidencePinDomain, ValidationStatus, Severity, CausalRole } from '../../../types';

interface EvidencePinCardProps {
  pin: EvidencePinV2;
}

const domainColors: Record<EvidencePinDomain, { bg: string; text: string; border: string }> = {
  compute:       { bg: 'bg-orange-500/15', text: 'text-orange-300', border: 'border-orange-500/30' },
  network:       { bg: 'bg-violet-500/15', text: 'text-violet-300', border: 'border-violet-500/30' },
  storage:       { bg: 'bg-blue-500/15',   text: 'text-blue-300',   border: 'border-blue-500/30' },
  control_plane: { bg: 'bg-cyan-500/15',   text: 'text-cyan-300',   border: 'border-cyan-500/30' },
  security:      { bg: 'bg-red-500/15',    text: 'text-red-300',    border: 'border-red-500/30' },
  unknown:       { bg: 'bg-slate-500/15',  text: 'text-slate-300',  border: 'border-slate-500/30' },
};

const severityBadgeClass: Record<Exclude<Severity, null>, string> = {
  critical: 'bg-red-500/20 text-red-300 border-red-500/40',
  high:     'bg-orange-500/20 text-orange-300 border-orange-500/40',
  medium:   'bg-yellow-500/20 text-yellow-300 border-yellow-500/40',
  low:      'bg-blue-500/20 text-blue-300 border-blue-500/40',
  info:     'bg-slate-500/20 text-slate-300 border-slate-500/40',
};

/** Map EvidencePinV2 causal_role to CausalRoleBadge's expected type */
const causalRoleToBadgeRole: Record<string, 'root_cause' | 'cascading_failure' | 'correlated_anomaly'> = {
  root_cause: 'root_cause',
  cascading_symptom: 'cascading_failure',
  correlated: 'correlated_anomaly',
  informational: 'correlated_anomaly',
};

function getValidationBorderClass(status: ValidationStatus): string {
  switch (status) {
    case 'pending_critic':
      return 'border-amber-500/40 animate-border-pulse-amber';
    case 'validated':
      return 'border-emerald-500/60 animate-border-pulse-green';
    case 'rejected':
      return 'border-slate-700/40 opacity-50';
    default:
      return 'border-slate-700/40';
  }
}

function getTriggeredByLabel(triggeredBy: EvidencePinV2['triggered_by']): string {
  switch (triggeredBy) {
    case 'automated_pipeline': return 'Pipeline';
    case 'user_chat': return 'Chat';
    case 'quick_action': return 'Quick Action';
    default: return triggeredBy;
  }
}

const EvidencePinCard: React.FC<EvidencePinCardProps> = ({ pin }) => {
  const [showRaw, setShowRaw] = useState(false);
  const domainStyle = domainColors[pin.domain] || domainColors.unknown;
  const borderClass = getValidationBorderClass(pin.validation_status);

  return (
    <div className={`relative rounded-lg border-2 ${borderClass} bg-slate-900/60 p-3 transition-all`}>
      {/* Top row: severity + source + domain badge */}
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="flex items-center gap-2 flex-wrap">
          {/* Severity badge */}
          {pin.severity && (
            <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider border ${severityBadgeClass[pin.severity]}`}>
              {pin.severity}
            </span>
          )}

          {/* Source badge */}
          <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] ${
            pin.source === 'manual'
              ? 'bg-amber-500/15 text-amber-300 border border-amber-500/30'
              : 'bg-slate-500/15 text-slate-400 border border-slate-600'
          }`}>
            <span
              className="material-symbols-outlined"
              style={{ fontFamily: 'Material Symbols Outlined', fontSize: '10px' }}
            >
              {pin.source === 'manual' ? 'person' : 'smart_toy'}
            </span>
            {pin.source === 'manual' ? 'Manual' : 'Auto'}
          </span>

          {/* Triggered by */}
          <span className="text-[9px] text-slate-500">
            via {getTriggeredByLabel(pin.triggered_by)}
          </span>
        </div>

        {/* Domain badge (top-right) */}
        <span className={`shrink-0 inline-flex items-center px-2 py-0.5 rounded-full text-[9px] font-semibold uppercase tracking-wider border ${domainStyle.bg} ${domainStyle.text} ${domainStyle.border}`}>
          {pin.domain.replace('_', ' ')}
        </span>
      </div>

      {/* Claim */}
      <p className="text-sm text-slate-200 leading-relaxed mb-2">{pin.claim}</p>

      {/* Causal role badge */}
      {pin.causal_role && causalRoleToBadgeRole[pin.causal_role] && (
        <div className="mb-2">
          <CausalRoleBadge role={causalRoleToBadgeRole[pin.causal_role]} />
        </div>
      )}

      {/* Supporting evidence */}
      {pin.supporting_evidence.length > 0 && (
        <div className="mb-2">
          <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Evidence</div>
          <ul className="space-y-0.5">
            {pin.supporting_evidence.map((ev, i) => (
              <li key={i} className="text-[11px] text-slate-400 pl-2 border-l border-slate-700">
                {ev}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Metadata row */}
      <div className="flex items-center gap-3 text-[9px] text-slate-500 mt-2">
        {pin.source_agent && (
          <span>Agent: <span className="text-slate-400">{pin.source_agent}</span></span>
        )}
        <span>Tool: <span className="text-slate-400">{pin.source_tool}</span></span>
        <span>Confidence: <span className="text-slate-400">{Math.round(pin.confidence * 100)}%</span></span>
        {pin.namespace && (
          <span>NS: <span className="text-slate-400">{pin.namespace}</span></span>
        )}
      </div>

      {/* Expandable raw output */}
      {pin.raw_output && (
        <div className="mt-2">
          <button
            onClick={() => setShowRaw(!showRaw)}
            className="text-[10px] text-cyan-500 hover:text-cyan-400 transition-colors flex items-center gap-1"
          >
            <span
              className="material-symbols-outlined"
              style={{ fontFamily: 'Material Symbols Outlined', fontSize: '12px', transition: 'transform 0.2s' , transform: showRaw ? 'rotate(90deg)' : 'rotate(0deg)' }}
            >
              chevron_right
            </span>
            View Raw
          </button>
          {showRaw && (
            <pre className="mt-1 p-2 rounded bg-slate-950/70 border border-slate-800 text-[10px] text-slate-400 overflow-x-auto max-h-[200px] font-mono whitespace-pre-wrap">
              {pin.raw_output}
            </pre>
          )}
        </div>
      )}

      {/* Validation status indicator */}
      {pin.validation_status === 'pending_critic' && (
        <div className="mt-2 flex items-center gap-1.5 text-[9px] text-amber-400">
          <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
          Awaiting critic validation
        </div>
      )}
      {pin.validation_status === 'validated' && (
        <div className="mt-2 flex items-center gap-1.5 text-[9px] text-emerald-400">
          <span
            className="material-symbols-outlined"
            style={{ fontFamily: 'Material Symbols Outlined', fontSize: '12px' }}
          >
            verified
          </span>
          Validated
        </div>
      )}
      {pin.validation_status === 'rejected' && (
        <div className="mt-2 flex items-center gap-1.5 text-[9px] text-slate-500">
          <span
            className="material-symbols-outlined"
            style={{ fontFamily: 'Material Symbols Outlined', fontSize: '12px' }}
          >
            cancel
          </span>
          Rejected
        </div>
      )}
    </div>
  );
};

export default EvidencePinCard;
