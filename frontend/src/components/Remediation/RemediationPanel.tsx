import React, { useState } from 'react';
import type { RemediationDecisionData, RunbookMatchData } from '../../types';
import { dryRunRemediation, executeRemediation, rollbackRemediation } from '../../services/api';

interface RemediationPanelProps {
  sessionId: string;
  decision: RemediationDecisionData | null;
  runbookMatches: RunbookMatchData[];
}

const RemediationPanel: React.FC<RemediationPanelProps> = ({
  sessionId,
  decision,
  runbookMatches,
}) => {
  const [dryRunOutput, setDryRunOutput] = useState<string | null>(null);
  const [executeOutput, setExecuteOutput] = useState<string | null>(null);
  const [showConfirm, setShowConfirm] = useState(false);
  const [loading, setLoading] = useState(false);
  const [preCheckStatus, setPreCheckStatus] = useState<Record<number, boolean>>({});
  const [postCheckStatus, setPostCheckStatus] = useState<Record<number, boolean>>({});

  const handleDryRun = async () => {
    if (!decision) return;
    setLoading(true);
    try {
      const result = await dryRunRemediation(sessionId, { action: decision.proposed_action });
      setDryRunOutput(result.output || 'Dry run completed');
    } catch {
      setDryRunOutput('Dry run failed');
    } finally {
      setLoading(false);
    }
  };

  const handleExecute = async () => {
    if (!decision) return;
    if (decision.is_destructive && !showConfirm) {
      setShowConfirm(true);
      return;
    }
    setShowConfirm(false);
    setLoading(true);
    try {
      const result = await executeRemediation(sessionId, { action: decision.proposed_action });
      setExecuteOutput(result.output || 'Execution completed');
    } catch {
      setExecuteOutput('Execution failed');
    } finally {
      setLoading(false);
    }
  };

  const handleRollback = async () => {
    setLoading(true);
    try {
      await rollbackRemediation(sessionId);
      setExecuteOutput('Rolled back successfully');
    } catch {
      setExecuteOutput('Rollback failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-3">
      <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
        Remediation
      </h4>

      {/* Matched Runbooks */}
      {runbookMatches.length > 0 && (
        <div className="space-y-2">
          <span className="text-xs text-gray-500">Matched Runbooks</span>
          {runbookMatches.map((rb) => (
            <div
              key={rb.runbook_id}
              className="bg-[#1e2f33]/50 border border-[#224349] rounded-lg p-3"
            >
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-medium text-white">{rb.title}</span>
                <span className="text-xs text-[#07b6d5] font-mono">
                  {Math.round(rb.match_score * 100)}%
                </span>
              </div>
              <div className="flex items-center gap-2 text-xs text-gray-500 mb-2">
                <span className="capitalize">{rb.source}</span>
                <span>|</span>
                <span>{Math.round(rb.success_rate * 100)}% success rate</span>
              </div>
              {rb.steps.length > 0 && (
                <ol className="list-decimal list-inside space-y-0.5">
                  {rb.steps.map((step, idx) => (
                    <li key={idx} className="text-xs text-gray-400">{step}</li>
                  ))}
                </ol>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Proposed Action */}
      {decision && (
        <div className="bg-[#1e2f33]/50 border border-[#224349] rounded-lg p-3 space-y-3">
          <div>
            <span className="text-xs text-gray-500 uppercase tracking-wider">Proposed Action</span>
            <p className="text-sm text-white mt-1">{decision.proposed_action}</p>
            <div className="flex items-center gap-2 mt-1">
              <span className="text-xs px-1.5 py-0.5 rounded bg-[#224349] text-gray-300">
                {decision.action_type}
              </span>
              {decision.is_destructive && (
                <span className="text-xs px-1.5 py-0.5 rounded bg-red-500/20 text-red-400">
                  Destructive
                </span>
              )}
            </div>
          </div>

          {/* Pre-checks */}
          {decision.pre_checks.length > 0 && (
            <div>
              <span className="text-xs text-gray-500">Pre-checks</span>
              <ul className="mt-1 space-y-1">
                {decision.pre_checks.map((check, idx) => (
                  <li
                    key={idx}
                    className="flex items-center gap-2 text-xs text-gray-400 cursor-pointer"
                    onClick={() => setPreCheckStatus((prev) => ({ ...prev, [idx]: !prev[idx] }))}
                  >
                    <span
                      className={`w-3.5 h-3.5 rounded border flex items-center justify-center ${
                        preCheckStatus[idx]
                          ? 'bg-green-600/30 border-green-600 text-green-400'
                          : 'border-gray-600'
                      }`}
                    >
                      {preCheckStatus[idx] ? '~' : ''}
                    </span>
                    {check}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Action Buttons */}
          <div className="flex gap-2">
            {decision.dry_run_available && (
              <button
                onClick={handleDryRun}
                disabled={loading}
                className="flex-1 px-3 py-1.5 text-xs font-medium rounded bg-[#224349] text-[#07b6d5] hover:bg-[#2a555c] transition-colors disabled:opacity-50"
              >
                {loading ? '...' : 'Dry Run'}
              </button>
            )}
            <button
              onClick={handleExecute}
              disabled={loading}
              className={`flex-1 px-3 py-1.5 text-xs font-medium rounded transition-colors disabled:opacity-50 ${
                decision.is_destructive
                  ? 'bg-red-600/20 text-red-400 hover:bg-red-600/30'
                  : 'bg-green-600/20 text-green-400 hover:bg-green-600/30'
              }`}
            >
              {loading ? '...' : 'Execute'}
            </button>
            {executeOutput && (
              <button
                onClick={handleRollback}
                disabled={loading}
                className="px-3 py-1.5 text-xs font-medium rounded bg-yellow-600/20 text-yellow-400 hover:bg-yellow-600/30 transition-colors disabled:opacity-50"
              >
                Rollback
              </button>
            )}
          </div>

          {/* Confirmation Dialog */}
          {showConfirm && (
            <div className="bg-red-900/20 border border-red-600/30 rounded-lg p-3">
              <p className="text-xs text-red-400 mb-2">
                This is a destructive action. Are you sure you want to proceed?
              </p>
              <div className="flex gap-2">
                <button
                  onClick={handleExecute}
                  className="px-3 py-1 text-xs rounded bg-red-600/30 text-red-400 hover:bg-red-600/40"
                >
                  Confirm Execute
                </button>
                <button
                  onClick={() => setShowConfirm(false)}
                  className="px-3 py-1 text-xs rounded bg-[#224349] text-gray-400 hover:bg-[#2a555c]"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {/* Dry Run Output */}
          {dryRunOutput && (
            <div className="bg-[#0a1a1d] border border-[#224349] rounded p-2">
              <span className="text-xs text-gray-500 block mb-1">Dry Run Output</span>
              <pre className="text-xs text-gray-300 whitespace-pre-wrap">{dryRunOutput}</pre>
            </div>
          )}

          {/* Execution Output */}
          {executeOutput && (
            <div className="bg-[#0a1a1d] border border-[#224349] rounded p-2">
              <span className="text-xs text-gray-500 block mb-1">Execution Output</span>
              <pre className="text-xs text-gray-300 whitespace-pre-wrap">{executeOutput}</pre>
            </div>
          )}

          {/* Post-checks */}
          {decision.post_checks.length > 0 && executeOutput && (
            <div>
              <span className="text-xs text-gray-500">Post-checks</span>
              <ul className="mt-1 space-y-1">
                {decision.post_checks.map((check, idx) => (
                  <li
                    key={idx}
                    className="flex items-center gap-2 text-xs text-gray-400 cursor-pointer"
                    onClick={() => setPostCheckStatus((prev) => ({ ...prev, [idx]: !prev[idx] }))}
                  >
                    <span
                      className={`w-3.5 h-3.5 rounded border flex items-center justify-center ${
                        postCheckStatus[idx]
                          ? 'bg-green-600/30 border-green-600 text-green-400'
                          : 'border-gray-600'
                      }`}
                    >
                      {postCheckStatus[idx] ? '~' : ''}
                    </span>
                    {check}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Rollback Plan */}
          {decision.rollback_plan && (
            <div className="text-xs text-gray-500">
              <span className="text-gray-600">Rollback plan:</span> {decision.rollback_plan}
            </div>
          )}
        </div>
      )}

      {!decision && runbookMatches.length === 0 && (
        <div className="text-xs text-gray-600 italic">
          No remediation actions proposed yet.
        </div>
      )}
    </div>
  );
};

export default RemediationPanel;
