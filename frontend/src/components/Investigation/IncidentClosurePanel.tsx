import React, { useState, useEffect, useCallback } from 'react';
import type {
  V4Findings,
  DiagnosticPhase,
  ClosureStatusResponse,
  IntegrationAvailability,
} from '../../types';
import {
  getClosureStatus,
  createJiraIssue,
  linkJiraIssue,
  createRemedyIncident,
} from '../../services/api';
import ClosureStepCard from './cards/ClosureStepCard';
import IntegrationStatusBadge from './cards/IntegrationStatusBadge';
import PostMortemPreviewModal from './PostMortemPreviewModal';

interface IncidentClosurePanelProps {
  sessionId: string;
  findings: V4Findings | null;
  phase: DiagnosticPhase | null;
}

const emptyIntegration: IntegrationAvailability = {
  configured: false,
  status: 'not_linked',
  has_credentials: false,
};

const IncidentClosurePanel: React.FC<IncidentClosurePanelProps> = ({
  sessionId,
  findings,
  phase,
}) => {
  const [closureStatus, setClosureStatus] = useState<ClosureStatusResponse | null>(null);
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Jira form
  const [jiraProjectKey, setJiraProjectKey] = useState('');
  const [linkMode, setLinkMode] = useState(false);
  const [linkIssueKey, setLinkIssueKey] = useState('');

  // Post-mortem modal
  const [showPostMortem, setShowPostMortem] = useState(false);

  const fetchStatus = useCallback(async () => {
    try {
      const data = await getClosureStatus(sessionId);
      setClosureStatus(data);
    } catch {
      // silent
    }
  }, [sessionId]);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  const jiraIntegration = closureStatus?.integrations?.jira || emptyIntegration;
  const confluenceIntegration = closureStatus?.integrations?.confluence || emptyIntegration;
  const remedyIntegration = closureStatus?.integrations?.remedy || emptyIntegration;

  const closureState = closureStatus?.closure_state || findings?.closure_state;
  const preDone = !!(findings?.fix_data && (
    findings.fix_data.fix_status === 'pr_created' ||
    findings.fix_data.fix_status === 'approved' ||
    findings.fix_data.fix_status === 'verified'
  ));
  const jiraDone = closureState?.jira_result?.status === 'success';
  const remedyDone = closureState?.remedy_result?.status === 'success';
  const confluenceDone = closureState?.confluence_result?.status === 'success';
  const step2Done = jiraDone || remedyDone;

  const handleCreateJira = async () => {
    if (!jiraProjectKey.trim()) return;
    setLoading('jira');
    setError(null);
    try {
      await createJiraIssue(sessionId, { project_key: jiraProjectKey.trim() });
      await fetchStatus();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Jira creation failed');
    } finally {
      setLoading(null);
    }
  };

  const handleLinkJira = async () => {
    if (!linkIssueKey.trim()) return;
    setLoading('jira-link');
    setError(null);
    try {
      await linkJiraIssue(sessionId, linkIssueKey.trim());
      await fetchStatus();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Jira link failed');
    } finally {
      setLoading(null);
    }
  };

  const handleCreateRemedy = async () => {
    setLoading('remedy');
    setError(null);
    try {
      await createRemedyIncident(sessionId, {});
      await fetchStatus();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Remedy creation failed');
    } finally {
      setLoading(null);
    }
  };

  const handlePreviewPostMortem = () => {
    setError(null);
    setShowPostMortem(true);
  };

  return (
    <>
      <div className="bg-slate-900/40 border border-slate-800 rounded-xl overflow-hidden">
        {/* Header */}
        <div className="px-4 py-2.5 border-b border-slate-800 bg-slate-900/60 flex items-center gap-2">
          <span className="material-symbols-outlined text-violet-400 text-sm" style={{ fontFamily: 'Material Symbols Outlined' }}>
            verified_user
          </span>
          <span className="text-[11px] font-bold uppercase tracking-wider text-violet-400">
            Incident Closure
          </span>
          <span className="text-[10px] text-slate-500 italic ml-1">
            Remediate, then document.
          </span>
        </div>

        <div className="p-4 space-y-3">
          {error && (
            <div className="text-[10px] text-red-400 bg-red-500/10 border border-red-500/20 rounded px-3 py-1.5">
              {error}
            </div>
          )}

          {/* Step 1: Fix Production */}
          <ClosureStepCard
            stepNumber={1}
            title="Fix Production"
            icon="build"
            completed={preDone}
            active={!preDone && (phase === 'fix_in_progress' || phase === 'diagnosis_complete')}
          >
            {preDone && findings?.fix_data?.pr_url ? (
              <div className="flex items-center gap-2 text-[11px]">
                <span className="text-green-400">PR created</span>
                <a
                  href={findings.fix_data.pr_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[#07b6d5] hover:underline font-mono"
                >
                  {findings.fix_data.pr_url.split('/').pop()}
                </a>
              </div>
            ) : preDone ? (
              <span className="text-[11px] text-green-400">Fix generated</span>
            ) : (
              <span className="text-[11px] text-slate-400">
                {phase === 'fix_in_progress' ? 'Fix generation in progress...' : 'Generate a fix from the diagnosis.'}
              </span>
            )}
          </ClosureStepCard>

          {/* Step 2: Update Governance */}
          <ClosureStepCard
            stepNumber={2}
            title="Update Governance"
            icon="assignment"
            completed={step2Done}
            active={preDone && !step2Done}
          >
            <div className="space-y-3">
              {/* Jira */}
              <div className="space-y-1.5">
                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-bold text-slate-300 uppercase tracking-wider">Jira</span>
                  <IntegrationStatusBadge integration={jiraIntegration} name="Jira" />
                </div>
                {jiraDone ? (
                  <div className="flex items-center gap-2 text-[11px]">
                    <span className="text-green-400">
                      {closureState!.jira_result.issue_key}
                    </span>
                    {closureState!.jira_result.issue_url && (
                      <a
                        href={closureState!.jira_result.issue_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-[#07b6d5] hover:underline"
                      >
                        Open
                      </a>
                    )}
                  </div>
                ) : jiraIntegration.configured && jiraIntegration.has_credentials ? (
                  <div className="space-y-1.5">
                    {!linkMode ? (
                      <div className="flex items-center gap-2">
                        <input
                          type="text"
                          placeholder="Project key (e.g. OPS)"
                          value={jiraProjectKey}
                          onChange={(e) => setJiraProjectKey(e.target.value)}
                          className="text-[11px] bg-slate-800/60 border border-slate-700/50 rounded px-2 py-1 text-slate-200 placeholder-slate-600 w-36 font-mono focus:outline-none focus:border-violet-500/50"
                        />
                        <button
                          onClick={handleCreateJira}
                          disabled={!jiraProjectKey.trim() || loading === 'jira'}
                          className="text-[10px] font-bold px-2.5 py-1 rounded bg-violet-500/20 text-violet-400 border border-violet-500/30 hover:bg-violet-500/30 disabled:opacity-50 disabled:cursor-not-allowed disabled:saturate-0"
                        >
                          {loading === 'jira' ? 'Creating...' : 'Create'}
                        </button>
                        <button
                          onClick={() => setLinkMode(true)}
                          className="text-[10px] text-slate-500 hover:text-slate-300"
                        >
                          or link existing
                        </button>
                      </div>
                    ) : (
                      <div className="flex items-center gap-2">
                        <input
                          type="text"
                          placeholder="Issue key (e.g. OPS-123)"
                          value={linkIssueKey}
                          onChange={(e) => setLinkIssueKey(e.target.value)}
                          className="text-[11px] bg-slate-800/60 border border-slate-700/50 rounded px-2 py-1 text-slate-200 placeholder-slate-600 w-36 font-mono focus:outline-none focus:border-violet-500/50"
                        />
                        <button
                          onClick={handleLinkJira}
                          disabled={!linkIssueKey.trim() || loading === 'jira-link'}
                          className="text-[10px] font-bold px-2.5 py-1 rounded bg-violet-500/20 text-violet-400 border border-violet-500/30 hover:bg-violet-500/30 disabled:opacity-50 disabled:cursor-not-allowed disabled:saturate-0"
                        >
                          {loading === 'jira-link' ? 'Linking...' : 'Link'}
                        </button>
                        <button
                          onClick={() => setLinkMode(false)}
                          className="text-[10px] text-slate-500 hover:text-slate-300"
                        >
                          or create new
                        </button>
                      </div>
                    )}
                  </div>
                ) : (
                  <span className="text-[10px] text-slate-500">Configure Jira in Settings to enable.</span>
                )}
              </div>

              {/* Remedy */}
              <div className="space-y-1.5">
                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-bold text-slate-300 uppercase tracking-wider">Remedy</span>
                  <IntegrationStatusBadge integration={remedyIntegration} name="Remedy" />
                </div>
                {remedyDone ? (
                  <div className="flex items-center gap-2 text-[11px]">
                    <span className="text-green-400">
                      {closureState!.remedy_result.incident_number}
                    </span>
                    {closureState!.remedy_result.incident_url && (
                      <a
                        href={closureState!.remedy_result.incident_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-[#07b6d5] hover:underline"
                      >
                        Open
                      </a>
                    )}
                  </div>
                ) : remedyIntegration.configured && remedyIntegration.has_credentials ? (
                  <button
                    onClick={handleCreateRemedy}
                    disabled={loading === 'remedy'}
                    className="text-[10px] font-bold px-2.5 py-1 rounded bg-violet-500/20 text-violet-400 border border-violet-500/30 hover:bg-violet-500/30 disabled:opacity-50 disabled:cursor-not-allowed disabled:saturate-0"
                  >
                    {loading === 'remedy' ? 'Creating...' : 'Create Incident'}
                  </button>
                ) : (
                  <span className="text-[10px] text-slate-500">Configure Remedy in Settings to enable.</span>
                )}
              </div>
            </div>
          </ClosureStepCard>

          {/* Step 3: Knowledge Capture */}
          <ClosureStepCard
            stepNumber={3}
            title="Knowledge Capture"
            icon="menu_book"
            completed={confluenceDone}
            active={step2Done && !confluenceDone}
          >
            <div className="space-y-1.5">
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-bold text-slate-300 uppercase tracking-wider">Confluence</span>
                <IntegrationStatusBadge integration={confluenceIntegration} name="Confluence" />
              </div>
              {confluenceDone ? (
                <div className="flex items-center gap-2 text-[11px]">
                  <span className="text-green-400">Post-mortem published</span>
                  {closureState!.confluence_result.page_url && (
                    <a
                      href={closureState!.confluence_result.page_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-[#07b6d5] hover:underline"
                    >
                      View Page
                    </a>
                  )}
                </div>
              ) : confluenceIntegration.configured && confluenceIntegration.has_credentials ? (
                <button
                  onClick={handlePreviewPostMortem}
                  className="text-[10px] font-bold px-2.5 py-1 rounded bg-violet-500/20 text-violet-400 border border-violet-500/30 hover:bg-violet-500/30"
                >
                  Generate Preview
                </button>
              ) : (
                <span className="text-[10px] text-slate-500">Configure Confluence in Settings to enable.</span>
              )}
            </div>
          </ClosureStepCard>
        </div>
      </div>

      {/* Post-Mortem Preview Modal */}
      {showPostMortem && (
        <PostMortemPreviewModal
          sessionId={sessionId}
          defaultTitle={closureStatus?.pre_filled?.confluence_title || ''}
          onClose={() => setShowPostMortem(false)}
          onPublished={() => {
            setShowPostMortem(false);
            fetchStatus();
          }}
        />
      )}
    </>
  );
};

export default IncidentClosurePanel;
