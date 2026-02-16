import React, { useState } from 'react';
import type { AttestationGateData, EvidencePinData } from '../../types';

interface AttestationGateUIProps {
  gate: AttestationGateData;
  evidencePins: EvidencePinData[];
  onDecision: (decision: 'approve' | 'reject' | 'modify', notes: string) => void;
  onClose: () => void;
}

const gateHeaders: Record<string, string> = {
  discovery_complete: 'Discovery Complete',
  pre_remediation: 'Pre-Remediation Approval',
  post_remediation: 'Post-Remediation Review',
};

const AttestationGateUI: React.FC<AttestationGateUIProps> = ({
  gate,
  evidencePins,
  onDecision,
  onClose,
}) => {
  const [notes, setNotes] = useState('');
  const [evidenceExpanded, setEvidenceExpanded] = useState(false);

  const headerText = gateHeaders[gate.gate_type] || gate.gate_type;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-[#0f2023] border border-[#224349] rounded-xl shadow-2xl w-full max-w-lg mx-4">
        {/* Header */}
        <div className="px-6 py-4 border-b border-[#224349] flex items-center justify-between">
          <h2 className="text-base font-semibold text-white">
            {headerText}
          </h2>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-white transition-colors text-lg leading-none"
          >
            x
          </button>
        </div>

        {/* Body */}
        <div className="px-6 py-4 space-y-4 max-h-[60vh] overflow-y-auto">
          {/* Evidence Summary */}
          <div>
            <button
              onClick={() => setEvidenceExpanded(!evidenceExpanded)}
              className="flex items-center gap-2 text-sm text-[#07b6d5] hover:text-[#38d9f5] transition-colors"
            >
              <span className="text-xs">{evidenceExpanded ? 'v' : '>'}</span>
              Evidence Summary ({evidencePins.length} pins)
            </button>
            {evidenceExpanded && (
              <ul className="mt-2 space-y-1.5 pl-4">
                {evidencePins.map((pin, idx) => (
                  <li
                    key={idx}
                    className="text-xs text-gray-400 bg-[#1e2f33]/50 border border-[#224349] rounded px-3 py-2"
                  >
                    <span className="text-white font-medium">{pin.claim}</span>
                    <span className="ml-2 text-gray-500">
                      ({pin.source_agent} / {Math.round(pin.confidence * 100)}%)
                    </span>
                  </li>
                ))}
                {evidencePins.length === 0 && (
                  <li className="text-xs text-gray-500 italic">No evidence pins available</li>
                )}
              </ul>
            )}
          </div>

          {/* Proposed Action */}
          {gate.proposed_action && (
            <div className="bg-[#1e2f33]/50 border border-[#224349] rounded-lg p-3">
              <span className="text-xs text-gray-400 uppercase tracking-wider">Proposed Action</span>
              <p className="text-sm text-white mt-1">{gate.proposed_action}</p>
            </div>
          )}

          {/* Notes */}
          <div>
            <label className="text-xs text-gray-400 uppercase tracking-wider block mb-1">
              Notes (optional)
            </label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={3}
              className="w-full bg-[#1e2f33] border border-[#224349] rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 resize-none focus:outline-none focus:ring-1 focus:ring-[#07b6d5]"
              placeholder="Add any notes or modifications..."
            />
          </div>
        </div>

        {/* Actions */}
        <div className="px-6 py-4 border-t border-[#224349] flex gap-3 justify-end">
          <button
            onClick={() => onDecision('reject', notes)}
            className="px-4 py-2 text-sm font-medium rounded-lg bg-red-600/20 text-red-400 border border-red-600/30 hover:bg-red-600/30 transition-colors"
          >
            Reject
          </button>
          <button
            onClick={() => onDecision('modify', notes)}
            className="px-4 py-2 text-sm font-medium rounded-lg bg-yellow-600/20 text-yellow-400 border border-yellow-600/30 hover:bg-yellow-600/30 transition-colors"
          >
            Modify
          </button>
          <button
            onClick={() => onDecision('approve', notes)}
            className="px-4 py-2 text-sm font-medium rounded-lg bg-green-600/20 text-green-400 border border-green-600/30 hover:bg-green-600/30 transition-colors"
          >
            Approve
          </button>
        </div>
      </div>
    </div>
  );
};

export default AttestationGateUI;
