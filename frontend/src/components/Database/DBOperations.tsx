/**
 * DBOperations — Main operations view with active queries, pending plans,
 * config recommendations, and execution log.
 */
import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  fetchDBProfiles,
  fetchDBActiveQueries,
  fetchRemediationPlans,
  fetchConfigRecommendations,
  fetchRemediationLog,
  killDBQuery,
  approveRemediationPlan,
  rejectRemediationPlan,
  executeRemediationPlan,
  createRemediationPlan,
} from '../../services/api';
import RemediationCard from './RemediationCard';
import type { RemediationPlan } from './RemediationCard';
import OperationFormModal from './OperationFormModal';

interface Profile {
  id: string;
  name: string;
  engine: string;
}

interface ActiveQuery {
  pid: number;
  query: string;
  duration_ms: number;
  state: string;
  user: string;
  database: string;
  waiting: boolean;
}

interface ConfigRecommendation {
  param: string;
  current_value: string;
  recommended_value: string;
  reason: string;
  requires_restart: boolean;
}

interface AuditLogEntry {
  timestamp: string;
  action: string;
  sql_executed: string;
  status: string;
  error?: string;
  before_state?: Record<string, unknown>;
  after_state?: Record<string, unknown>;
}

const statusDotColor: Record<string, string> = {
  completed: 'bg-green-400',
  failed: 'bg-red-400',
  executing: 'bg-cyan-400 animate-pulse',
  pending: 'bg-yellow-400',
  approved: 'bg-blue-400',
  rejected: 'bg-slate-400',
};

const DBOperations: React.FC = () => {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [selectedProfileId, setSelectedProfileId] = useState('');
  const [showModal, setShowModal] = useState(false);
  const [showOpMenu, setShowOpMenu] = useState(false);
  const [modalInitialAction, setModalInitialAction] = useState<string | null>(null);
  const [expandedLogEntry, setExpandedLogEntry] = useState<string | null>(null);

  // Panel data
  const [activeQueries, setActiveQueries] = useState<ActiveQuery[]>([]);
  const [plans, setPlans] = useState<RemediationPlan[]>([]);
  const [configRecs, setConfigRecs] = useState<ConfigRecommendation[]>([]);
  const [auditLog, setAuditLog] = useState<AuditLogEntry[]>([]);

  // Approval tokens for execute flow
  const [approvalTokens, setApprovalTokens] = useState<Record<string, string>>({});

  // Loading states
  const [loadingQueries, setLoadingQueries] = useState(false);
  const [loadingPlans, setLoadingPlans] = useState(false);
  const [loadingConfig, setLoadingConfig] = useState(false);
  const [loadingLog, setLoadingLog] = useState(false);

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const activeQueriesRef = useRef<HTMLDivElement>(null);
  const opMenuRef = useRef<HTMLDivElement>(null);

  // Load profiles on mount
  useEffect(() => {
    fetchDBProfiles()
      .then((list: Profile[]) => {
        setProfiles(list);
        if (list.length > 0) setSelectedProfileId(list[0].id);
      })
      .catch(() => setProfiles([]));
  }, []);

  // Load active queries
  const loadQueries = useCallback(async () => {
    if (!selectedProfileId) return;
    setLoadingQueries(true);
    try {
      const data = await fetchDBActiveQueries(selectedProfileId);
      setActiveQueries(data.queries || []);
    } catch {
      setActiveQueries([]);
    } finally {
      setLoadingQueries(false);
    }
  }, [selectedProfileId]);

  // Load remediation plans (pending + approved)
  const loadPlans = useCallback(async () => {
    if (!selectedProfileId) return;
    setLoadingPlans(true);
    try {
      const allPlans = await fetchRemediationPlans(selectedProfileId);
      const planList = Array.isArray(allPlans) ? allPlans : allPlans.plans || [];
      setPlans(planList.filter((p: RemediationPlan) => ['pending', 'approved', 'executing'].includes(p.status)));
    } catch {
      setPlans([]);
    } finally {
      setLoadingPlans(false);
    }
  }, [selectedProfileId]);

  // Load config recommendations
  const loadConfig = useCallback(async () => {
    if (!selectedProfileId) return;
    setLoadingConfig(true);
    try {
      const data = await fetchConfigRecommendations(selectedProfileId);
      setConfigRecs(Array.isArray(data) ? data : data.recommendations || []);
    } catch {
      setConfigRecs([]);
    } finally {
      setLoadingConfig(false);
    }
  }, [selectedProfileId]);

  // Load audit log
  const loadLog = useCallback(async () => {
    if (!selectedProfileId) return;
    setLoadingLog(true);
    try {
      const data = await fetchRemediationLog(selectedProfileId);
      setAuditLog(Array.isArray(data) ? data : data.entries || []);
    } catch {
      setAuditLog([]);
    } finally {
      setLoadingLog(false);
    }
  }, [selectedProfileId]);

  // Load all data when profile changes
  useEffect(() => {
    if (!selectedProfileId) return;
    loadQueries();
    loadPlans();
    loadConfig();
    loadLog();
  }, [selectedProfileId, loadQueries, loadPlans, loadConfig, loadLog]);

  // Auto-refresh every 10s
  useEffect(() => {
    if (!selectedProfileId) return;
    intervalRef.current = setInterval(() => {
      loadQueries();
      loadPlans();
    }, 10000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [selectedProfileId, loadQueries, loadPlans]);

  // Close dropdown on outside click
  useEffect(() => {
    if (!showOpMenu) return;
    const handleClick = (e: MouseEvent) => {
      if (opMenuRef.current && !opMenuRef.current.contains(e.target as Node)) {
        setShowOpMenu(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [showOpMenu]);

  // Handlers
  const handleKillQuery = async (queryPid: number) => {
    if (!confirm(`Kill process ${queryPid}?`)) return;
    try {
      await killDBQuery(selectedProfileId, queryPid);
      alert('Query killed successfully');
      await loadQueries();
    } catch (err) {
      alert(`Failed to kill query: ${err instanceof Error ? err.message : 'Unknown error'}`);
    }
  };

  const handleApprove = async (planId: string) => {
    try {
      const result = await approveRemediationPlan(planId);
      const token = result.approval_token || result.token || '';
      if (token) {
        setApprovalTokens(prev => ({ ...prev, [planId]: token }));
        await executeRemediationPlan(planId, token);
        alert('Plan approved and execution started');
      } else {
        alert('Plan approved');
      }
      await loadPlans();
      await loadLog();
    } catch (err) {
      alert(`Failed to approve plan: ${err instanceof Error ? err.message : 'Unknown error'}`);
    }
  };

  const handleReject = async (planId: string) => {
    try {
      await rejectRemediationPlan(planId);
      alert('Plan rejected');
      await loadPlans();
      await loadLog();
    } catch (err) {
      alert(`Failed to reject plan: ${err instanceof Error ? err.message : 'Unknown error'}`);
    }
  };

  const handleExecute = async (planId: string) => {
    try {
      let token = approvalTokens[planId];
      if (!token) {
        // Plan may already be approved — try to re-approve to get a token
        try {
          const result = await approveRemediationPlan(planId);
          token = result.approval_token || result.token || '';
        } catch {
          // Plan is likely already approved and we don't have a cached token
        }
      }
      if (!token) {
        alert('Cannot execute: no approval token available. Please approve the plan first.');
        return;
      }
      await executeRemediationPlan(planId, token);
      alert('Execution started');
      await loadPlans();
      await loadLog();
    } catch (err) {
      alert(`Execution failed: ${err instanceof Error ? err.message : err}`);
    }
  };

  const handleCreateOperation = async (action: string, params: Record<string, unknown>) => {
    try {
      await createRemediationPlan({ profile_id: selectedProfileId, action, params });
      setShowModal(false);
      alert('Plan created');
      await loadPlans();
    } catch (err) {
      alert(`Failed to create plan: ${err instanceof Error ? err.message : 'Unknown error'}`);
    }
  };

  const handleApplyConfig = async (param: string, value: string) => {
    try {
      await createRemediationPlan({
        profile_id: selectedProfileId,
        action: 'alter_config',
        params: { param, value },
      });
      alert('Config change plan created');
      await loadPlans();
    } catch (err) {
      alert(`Failed to create config plan: ${err instanceof Error ? err.message : 'Unknown error'}`);
    }
  };

  return (
    <div className="p-6 space-y-6">
      {/* Top bar */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold text-slate-100">Operations</h2>
          <select
            value={selectedProfileId}
            onChange={(e) => setSelectedProfileId(e.target.value)}
            className="px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-600 text-sm text-slate-100 focus:border-cyan-500 outline-none"
          >
            {profiles.map((p) => (
              <option key={p.id} value={p.id}>{p.name} ({p.engine})</option>
            ))}
          </select>
        </div>
        <div className="relative" ref={opMenuRef}>
          <button
            onClick={() => setShowOpMenu((v) => !v)}
            className="flex items-center gap-1.5 px-4 py-2 text-xs rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white transition-colors"
          >
            <span className="material-symbols-outlined text-[16px]">add</span>
            New Operation
            <span className="material-symbols-outlined text-[16px]">expand_more</span>
          </button>
          {showOpMenu && (
            <div className="absolute right-0 mt-1 w-56 bg-[#0d2329] border border-slate-700/50 rounded-lg shadow-xl z-50 py-1">
              <button
                onClick={() => { setShowOpMenu(false); activeQueriesRef.current?.scrollIntoView({ behavior: 'smooth' }); }}
                className="w-full text-left px-3 py-2 text-sm text-slate-300 hover:bg-slate-700/50 hover:text-slate-100 flex items-center gap-2"
              >
                <span className="material-symbols-outlined text-[16px]">cancel</span>
                Kill Query
              </button>
              <button
                onClick={() => { setShowOpMenu(false); setModalInitialAction('vacuum'); setShowModal(true); }}
                className="w-full text-left px-3 py-2 text-sm text-slate-300 hover:bg-slate-700/50 hover:text-slate-100 flex items-center gap-2"
              >
                <span className="material-symbols-outlined text-[16px]">cleaning_services</span>
                Vacuum Table
              </button>
              <button
                onClick={() => { setShowOpMenu(false); setModalInitialAction('reindex'); setShowModal(true); }}
                className="w-full text-left px-3 py-2 text-sm text-slate-300 hover:bg-slate-700/50 hover:text-slate-100 flex items-center gap-2"
              >
                <span className="material-symbols-outlined text-[16px]">reorder</span>
                Reindex Table
              </button>
              <button
                onClick={() => { setShowOpMenu(false); setModalInitialAction('create_index'); setShowModal(true); }}
                className="w-full text-left px-3 py-2 text-sm text-slate-300 hover:bg-slate-700/50 hover:text-slate-100 flex items-center gap-2"
              >
                <span className="material-symbols-outlined text-[16px]">add_circle</span>
                Create Index
              </button>
              <button
                onClick={() => { setShowOpMenu(false); setModalInitialAction('drop_index'); setShowModal(true); }}
                className="w-full text-left px-3 py-2 text-sm text-slate-300 hover:bg-slate-700/50 hover:text-slate-100 flex items-center gap-2"
              >
                <span className="material-symbols-outlined text-[16px]">remove_circle</span>
                Drop Index
              </button>
              <button
                onClick={() => { setShowOpMenu(false); setModalInitialAction('alter_config'); setShowModal(true); }}
                className="w-full text-left px-3 py-2 text-sm text-slate-300 hover:bg-slate-700/50 hover:text-slate-100 flex items-center gap-2"
              >
                <span className="material-symbols-outlined text-[16px]">settings</span>
                Alter Config
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Panel 1: Active Queries */}
      <div ref={activeQueriesRef} className="bg-[#0d2329] border border-slate-700/50 rounded-lg">
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700/30">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-cyan-400 text-[18px]">terminal</span>
            <h3 className="text-sm font-semibold text-slate-200">Active Queries</h3>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-700/60 text-slate-400">
              {activeQueries.length}
            </span>
          </div>
          <button
            onClick={loadQueries}
            className="text-slate-500 hover:text-slate-300 transition-colors"
          >
            <span className={`material-symbols-outlined text-[16px] ${loadingQueries ? 'animate-spin' : ''}`}>
              {loadingQueries ? 'progress_activity' : 'refresh'}
            </span>
          </button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs text-slate-300">
            <thead>
              <tr className="border-b border-slate-700/30 text-slate-500">
                <th className="px-4 py-2 text-left font-medium">PID</th>
                <th className="px-4 py-2 text-left font-medium">SQL</th>
                <th className="px-4 py-2 text-left font-medium">Duration</th>
                <th className="px-4 py-2 text-left font-medium">State</th>
                <th className="px-4 py-2 text-left font-medium">User</th>
                <th className="px-4 py-2 text-left font-medium">Database</th>
                <th className="px-4 py-2 text-right font-medium">Action</th>
              </tr>
            </thead>
            <tbody>
              {activeQueries.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-6 text-center text-slate-500">
                    No active queries
                  </td>
                </tr>
              ) : (
                activeQueries.map((q) => (
                  <tr key={q.pid} className="border-b border-slate-700/30 hover:bg-slate-800/30">
                    <td className="px-4 py-2 font-mono">{q.pid}</td>
                    <td className="px-4 py-2 font-mono max-w-xs truncate" title={q.query}>
                      {q.query.length > 80 ? `${q.query.slice(0, 80)}...` : q.query}
                    </td>
                    <td className="px-4 py-2">{q.duration_ms >= 1000 ? `${(q.duration_ms / 1000).toFixed(1)}s` : `${Math.round(q.duration_ms)}ms`}</td>
                    <td className="px-4 py-2">
                      <span className="px-1.5 py-0.5 rounded bg-slate-700/50 text-[10px]">{q.state}</span>
                    </td>
                    <td className="px-4 py-2">{q.user}</td>
                    <td className="px-4 py-2">{q.database}</td>
                    <td className="px-4 py-2 text-right">
                      <button
                        onClick={() => handleKillQuery(q.pid)}
                        className="flex items-center gap-1 ml-auto px-2 py-1 text-[10px] rounded bg-red-500/20 hover:bg-red-500/30 text-red-400 transition-colors"
                      >
                        <span className="material-symbols-outlined text-[12px]">stop</span>
                        Kill
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Panel 2: Pending Plans */}
      <div className="bg-[#0d2329] border border-slate-700/50 rounded-lg">
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700/30">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-cyan-400 text-[18px]">pending_actions</span>
            <h3 className="text-sm font-semibold text-slate-200">Pending Plans</h3>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-700/60 text-slate-400">
              {plans.length}
            </span>
          </div>
          <button
            onClick={loadPlans}
            className="text-slate-500 hover:text-slate-300 transition-colors"
          >
            <span className={`material-symbols-outlined text-[16px] ${loadingPlans ? 'animate-spin' : ''}`}>
              {loadingPlans ? 'progress_activity' : 'refresh'}
            </span>
          </button>
        </div>
        <div className="p-4 space-y-3">
          {plans.length === 0 ? (
            <p className="text-xs text-slate-500 text-center py-4">No pending plans</p>
          ) : (
            plans.map((plan) => (
              <RemediationCard
                key={plan.plan_id}
                plan={plan}
                onApprove={handleApprove}
                onReject={handleReject}
                onExecute={handleExecute}
              />
            ))
          )}
        </div>
      </div>

      {/* Panel 3: Config Recommendations */}
      <div className="bg-[#0d2329] border border-slate-700/50 rounded-lg">
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700/30">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-cyan-400 text-[18px]">tune</span>
            <h3 className="text-sm font-semibold text-slate-200">Config Recommendations</h3>
          </div>
          <button
            onClick={loadConfig}
            className="text-slate-500 hover:text-slate-300 transition-colors"
          >
            <span className={`material-symbols-outlined text-[16px] ${loadingConfig ? 'animate-spin' : ''}`}>
              {loadingConfig ? 'progress_activity' : 'refresh'}
            </span>
          </button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs text-slate-300">
            <thead>
              <tr className="border-b border-slate-700/30 text-slate-500">
                <th className="px-4 py-2 text-left font-medium">Parameter</th>
                <th className="px-4 py-2 text-left font-medium">Current</th>
                <th className="px-4 py-2 text-left font-medium">Recommended</th>
                <th className="px-4 py-2 text-left font-medium">Reason</th>
                <th className="px-4 py-2 text-left font-medium">Restart</th>
                <th className="px-4 py-2 text-right font-medium">Action</th>
              </tr>
            </thead>
            <tbody>
              {configRecs.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-6 text-center text-slate-500">
                    No recommendations
                  </td>
                </tr>
              ) : (
                configRecs.map((rec) => (
                  <tr key={rec.param} className="border-b border-slate-700/30 hover:bg-slate-800/30">
                    <td className="px-4 py-2 font-mono text-cyan-400">{rec.param}</td>
                    <td className="px-4 py-2 font-mono">{rec.current_value}</td>
                    <td className="px-4 py-2 font-mono text-green-400">{rec.recommended_value}</td>
                    <td className="px-4 py-2 max-w-xs">{rec.reason}</td>
                    <td className="px-4 py-2">
                      {rec.requires_restart ? (
                        <span className="px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-400 text-[10px] font-medium">
                          RESTART
                        </span>
                      ) : (
                        <span className="px-1.5 py-0.5 rounded bg-green-500/20 text-green-400 text-[10px] font-medium">
                          LIVE
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2 text-right">
                      <button
                        onClick={() => handleApplyConfig(rec.param, rec.recommended_value)}
                        className="flex items-center gap-1 ml-auto px-2 py-1 text-[10px] rounded bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-400 transition-colors"
                      >
                        <span className="material-symbols-outlined text-[12px]">play_arrow</span>
                        Apply
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Panel 4: Execution Log */}
      <div className="bg-[#0d2329] border border-slate-700/50 rounded-lg">
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700/30">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-cyan-400 text-[18px]">history</span>
            <h3 className="text-sm font-semibold text-slate-200">Execution Log</h3>
          </div>
          <button
            onClick={loadLog}
            className="text-slate-500 hover:text-slate-300 transition-colors"
          >
            <span className={`material-symbols-outlined text-[16px] ${loadingLog ? 'animate-spin' : ''}`}>
              {loadingLog ? 'progress_activity' : 'refresh'}
            </span>
          </button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs text-slate-300">
            <thead>
              <tr className="border-b border-slate-700/30 text-slate-500">
                <th className="px-4 py-2 text-left font-medium">Timestamp</th>
                <th className="px-4 py-2 text-left font-medium">Action</th>
                <th className="px-4 py-2 text-left font-medium">SQL</th>
                <th className="px-4 py-2 text-left font-medium">Status</th>
                <th className="px-4 py-2 text-left font-medium">Error</th>
              </tr>
            </thead>
            <tbody>
              {auditLog.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-6 text-center text-slate-500">
                    No log entries
                  </td>
                </tr>
              ) : (
                auditLog.map((entry, idx) => {
                  const entryId = `${entry.timestamp}-${idx}`;
                  const isExpanded = expandedLogEntry === entryId;
                  return (
                    <React.Fragment key={idx}>
                      <tr
                        className="border-b border-slate-700/30 hover:bg-slate-800/30 cursor-pointer"
                        onClick={() => setExpandedLogEntry(isExpanded ? null : entryId)}
                      >
                        <td className="px-4 py-2 whitespace-nowrap">{new Date(entry.timestamp).toLocaleString()}</td>
                        <td className="px-4 py-2">{entry.action.replace(/_/g, ' ')}</td>
                        <td className="px-4 py-2 font-mono max-w-xs truncate" title={entry.sql_executed}>
                          {entry.sql_executed.length > 60 ? `${entry.sql_executed.slice(0, 60)}...` : entry.sql_executed}
                        </td>
                        <td className="px-4 py-2">
                          <span className="flex items-center gap-1.5">
                            <span className={`inline-block w-1.5 h-1.5 rounded-full ${statusDotColor[entry.status] || 'bg-slate-400'}`} />
                            {entry.status}
                          </span>
                        </td>
                        <td className="px-4 py-2 text-red-400 max-w-xs truncate" title={entry.error || ''}>
                          {entry.error || '-'}
                        </td>
                      </tr>
                      {isExpanded && (
                        <tr className="border-b border-slate-700/30">
                          <td colSpan={5} className="px-4 py-3">
                            <div className="grid grid-cols-2 gap-4 p-3 bg-[#081418] rounded">
                              <div>
                                <div className="text-xs font-semibold text-slate-400 mb-1">Before</div>
                                <pre className="text-xs text-slate-300 font-mono whitespace-pre-wrap">{JSON.stringify(entry.before_state, null, 2) || '\u2014'}</pre>
                              </div>
                              <div>
                                <div className="text-xs font-semibold text-slate-400 mb-1">After</div>
                                <pre className="text-xs text-slate-300 font-mono whitespace-pre-wrap">{JSON.stringify(entry.after_state, null, 2) || '\u2014'}</pre>
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* New Operation Modal */}
      {showModal && (
        <OperationFormModal
          onClose={() => { setShowModal(false); setModalInitialAction(null); }}
          onCreate={handleCreateOperation}
          initialAction={modalInitialAction || undefined}
        />
      )}
    </div>
  );
};

export default DBOperations;
