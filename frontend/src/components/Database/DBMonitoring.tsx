/**
 * DBMonitoring — Time-series charts, active alerts, and alert rule management.
 */
import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  fetchDBProfiles,
  fetchDBMonitorStatus,
  fetchDBMonitorMetrics,
  startDBMonitor,
  stopDBMonitor,
  fetchDBAlertRules,
  createDBAlertRule,
  deleteDBAlertRule,
  updateDBAlertRule,
  fetchDBActiveAlerts,
} from '../../services/api';

interface MetricPoint {
  time: string;
  value: number;
}

interface AlertRule {
  id: string;
  name: string;
  severity: string;
  metric: string;
  condition: string;
  threshold: number;
  enabled: boolean;
}

interface ActiveAlert {
  rule_id: string;
  entity_id: string;
  severity: string;
  message: string;
  fired_at: string;
  value: number;
}

interface Profile {
  id: string;
  name: string;
  engine: string;
}

const TIME_RANGES = [
  { label: '1h', duration: '1h', resolution: '1m' },
  { label: '6h', duration: '6h', resolution: '5m' },
  { label: '24h', duration: '24h', resolution: '15m' },
  { label: '7d', duration: '7d', resolution: '1h' },
];

const CHART_CONFIGS = [
  { metric: 'db_conn_active', label: 'Active Connections', color: '#07b6d5', unit: '' },
  { metric: 'db_cache_hit_ratio', label: 'Cache Hit Ratio', color: '#10b981', unit: '%', scale: 100 },
  { metric: 'db_tps', label: 'Transactions/sec', color: '#f59e0b', unit: '/s' },
  { metric: 'db_repl_lag_bytes', label: 'Replication Lag', color: '#8b5cf6', unit: 'B' },
];

/** Inline SVG polyline chart */
const MiniChart: React.FC<{ data: MetricPoint[]; color: string; label: string; unit: string; scale?: number }> = ({
  data, color, label, unit, scale,
}) => {
  const points = useMemo(() => {
    if (!data || data.length < 2) return '';
    const vals = data.map((d) => (scale ? d.value * scale : d.value));
    const min = Math.min(...vals);
    const max = Math.max(...vals);
    const range = max - min || 1;
    return vals
      .map((v, i) => {
        const x = (i / (vals.length - 1)) * 100;
        const y = 100 - ((v - min) / range) * 100;
        return `${x},${y}`;
      })
      .join(' ');
  }, [data, scale]);

  const latestVal = data.length > 0 ? (scale ? data[data.length - 1].value * scale : data[data.length - 1].value) : null;

  return (
    <div className="rounded-xl border border-slate-700/50 bg-[#0d2328] p-4 space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs text-slate-400">{label}</span>
        {latestVal !== null && (
          <span className="text-sm font-mono font-semibold" style={{ color }}>
            {latestVal < 1000 ? latestVal.toFixed(1) : `${(latestVal / 1000).toFixed(1)}k`}{unit}
          </span>
        )}
      </div>
      <div className="h-16">
        {data.length >= 2 ? (
          <svg viewBox="0 -5 100 110" preserveAspectRatio="none" className="w-full h-full">
            <polyline
              fill="none"
              stroke={color}
              strokeWidth={1.5}
              strokeLinecap="round"
              strokeLinejoin="round"
              points={points}
            />
          </svg>
        ) : (
          <div className="flex items-center justify-center h-full text-xs text-slate-600">
            No data yet
          </div>
        )}
      </div>
    </div>
  );
};

const severityColors: Record<string, string> = {
  critical: 'bg-red-500/20 text-red-400',
  warning: 'bg-amber-500/20 text-amber-400',
  info: 'bg-blue-500/20 text-blue-400',
};

const DBMonitoring: React.FC = () => {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [selectedProfileId, setSelectedProfileId] = useState('');
  const [timeRange, setTimeRange] = useState(TIME_RANGES[0]);
  const [monitorRunning, setMonitorRunning] = useState(false);
  const [chartData, setChartData] = useState<Record<string, MetricPoint[]>>({});
  const [alerts, setAlerts] = useState<ActiveAlert[]>([]);
  const [rules, setRules] = useState<AlertRule[]>([]);
  const [loadingCharts, setLoadingCharts] = useState(false);
  const [showRuleForm, setShowRuleForm] = useState(false);
  const [newRule, setNewRule] = useState({ name: '', metric: 'db_conn_utilization', condition: 'gt', threshold: 80, severity: 'warning', cooldown: 300 });
  const [editingRuleId, setEditingRuleId] = useState<string | null>(null);

  // Load profiles
  useEffect(() => {
    fetchDBProfiles().then((list: Profile[]) => {
      setProfiles(list);
      if (list.length > 0 && !selectedProfileId) setSelectedProfileId(list[0].id);
    }).catch(() => setProfiles([]));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Load monitor status
  useEffect(() => {
    fetchDBMonitorStatus().then((s: { running: boolean }) => setMonitorRunning(s.running)).catch(() => {});
  }, []);

  // Load charts when profile or time range changes
  const loadCharts = useCallback(async () => {
    if (!selectedProfileId) return;
    setLoadingCharts(true);
    try {
      const results = await Promise.all(
        CHART_CONFIGS.map(async (cfg) => {
          try {
            const data = await fetchDBMonitorMetrics(selectedProfileId, cfg.metric, timeRange.duration, timeRange.resolution);
            return { metric: cfg.metric, data: Array.isArray(data) ? data : (data.points || []) };
          } catch {
            return { metric: cfg.metric, data: [] };
          }
        }),
      );
      const newData: Record<string, MetricPoint[]> = {};
      for (const r of results) newData[r.metric] = r.data;
      setChartData(newData);
    } finally {
      setLoadingCharts(false);
    }
  }, [selectedProfileId, timeRange]);

  useEffect(() => { loadCharts(); }, [loadCharts]);

  // Load alerts + rules
  const loadAlerts = useCallback(async () => {
    try { setAlerts(await fetchDBActiveAlerts()); } catch { setAlerts([]); }
    try { setRules(await fetchDBAlertRules()); } catch { setRules([]); }
  }, []);

  useEffect(() => { loadAlerts(); }, [loadAlerts]);

  const handleToggleMonitor = async () => {
    try {
      if (monitorRunning) {
        await stopDBMonitor();
        setMonitorRunning(false);
      } else {
        await startDBMonitor();
        setMonitorRunning(true);
      }
    } catch { /* ignore */ }
  };

  const handleCreateRule = async () => {
    try {
      if (editingRuleId) {
        await updateDBAlertRule(editingRuleId, newRule);
      } else {
        await createDBAlertRule(newRule);
      }
      setShowRuleForm(false);
      setEditingRuleId(null);
      setNewRule({ name: '', metric: 'db_conn_utilization', condition: 'gt', threshold: 80, severity: 'warning', cooldown: 300 });
      await loadAlerts();
    } catch { /* ignore */ }
  };

  const handleDeleteRule = async (ruleId: string) => {
    if (!confirm('Delete this alert rule?')) return;
    try {
      await deleteDBAlertRule(ruleId);
      await loadAlerts();
    } catch { /* ignore */ }
  };

  const handleEditRule = (rule: AlertRule) => {
    setEditingRuleId(rule.id);
    setNewRule({ name: rule.name, metric: rule.metric, condition: rule.condition, threshold: rule.threshold, severity: rule.severity, cooldown: 300 });
    setShowRuleForm(true);
  };

  return (
    <div className="p-6 space-y-6">
      {/* Top bar */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold text-slate-100">Monitoring</h2>
          <select
            value={selectedProfileId}
            onChange={(e) => setSelectedProfileId(e.target.value)}
            className="px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-600 text-sm text-slate-100 focus:border-cyan-500 outline-none"
          >
            {profiles.map((p) => (
              <option key={p.id} value={p.id}>{p.name} ({p.engine})</option>
            ))}
          </select>
          <div className="flex rounded-lg overflow-hidden border border-slate-600">
            {TIME_RANGES.map((tr) => (
              <button
                key={tr.label}
                onClick={() => setTimeRange(tr)}
                className={`px-2.5 py-1 text-xs transition-colors ${
                  timeRange.label === tr.label
                    ? 'bg-cyan-600 text-white'
                    : 'bg-slate-800 text-slate-400 hover:text-slate-200'
                }`}
              >
                {tr.label}
              </button>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={loadCharts}
            className="flex items-center gap-1 px-3 py-1.5 text-xs bg-slate-700/50 hover:bg-slate-700 text-slate-300 rounded-lg transition-colors"
          >
            <span className={`material-symbols-outlined text-[16px] ${loadingCharts ? 'animate-spin' : ''}`}>
              {loadingCharts ? 'progress_activity' : 'refresh'}
            </span>
            Refresh
          </button>
          <button
            onClick={handleToggleMonitor}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg transition-colors ${
              monitorRunning
                ? 'bg-red-500/20 text-red-400 hover:bg-red-500/30'
                : 'bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30'
            }`}
          >
            <span className="material-symbols-outlined text-[16px]">
              {monitorRunning ? 'stop_circle' : 'play_circle'}
            </span>
            {monitorRunning ? 'Stop Monitor' : 'Start Monitor'}
          </button>
        </div>
      </div>

      {/* Chart grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {CHART_CONFIGS.map((cfg) => (
          <MiniChart
            key={cfg.metric}
            data={chartData[cfg.metric] || []}
            color={cfg.color}
            label={cfg.label}
            unit={cfg.unit}
            scale={cfg.scale}
          />
        ))}
      </div>

      {/* Active Alerts */}
      <div>
        <h3 className="text-sm font-medium text-slate-400 mb-2">Active Alerts</h3>
        {alerts.length === 0 ? (
          <div className="text-xs text-slate-600 py-4 text-center rounded-lg border border-slate-700/30 bg-[#0d2328]">
            No active alerts
          </div>
        ) : (
          <div className="space-y-1.5">
            {alerts.map((a, i) => (
              <div key={i} className={`flex items-center justify-between px-3 py-2 rounded-lg ${severityColors[a.severity] || severityColors.info}`}>
                <div className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-[16px]">
                    {a.severity === 'critical' ? 'error' : 'warning'}
                  </span>
                  <span className="text-sm">{a.message}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs opacity-60">{new Date(a.fired_at).toLocaleTimeString()}</span>
                  <button className="text-slate-500 hover:text-emerald-400 transition-colors" title="Acknowledge">
                    <span className="material-symbols-outlined text-[16px]">check_circle</span>
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Alert Rules */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-medium text-slate-400">Alert Rules</h3>
          <button
            onClick={() => setShowRuleForm(true)}
            className="flex items-center gap-1 px-2.5 py-1 text-xs bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg transition-colors"
          >
            <span className="material-symbols-outlined text-[14px]">add</span>
            Add Rule
          </button>
        </div>
        <div className="rounded-xl border border-slate-700/50 bg-[#0d2328] overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-700/50 text-xs text-slate-500">
                <th className="text-left px-4 py-2 font-medium">Name</th>
                <th className="text-left px-4 py-2 font-medium">Metric</th>
                <th className="text-left px-4 py-2 font-medium">Condition</th>
                <th className="text-left px-4 py-2 font-medium">Severity</th>
                <th className="text-center px-4 py-2 font-medium">Enabled</th>
                <th className="text-right px-4 py-2 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {rules.map((r) => (
                <tr key={r.id} className="border-b border-slate-700/30 last:border-0 hover:bg-slate-800/30">
                  <td className="px-4 py-2 text-slate-200">{r.name}</td>
                  <td className="px-4 py-2 text-slate-400 font-mono text-xs">{r.metric}</td>
                  <td className="px-4 py-2 text-slate-400 text-xs">{r.condition} {r.threshold}</td>
                  <td className="px-4 py-2">
                    <span className={`text-xs px-1.5 py-0.5 rounded ${severityColors[r.severity] || 'bg-slate-500/20 text-slate-400'}`}>
                      {r.severity}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-center">
                    <span className={`inline-block w-2.5 h-2.5 rounded-full ${r.enabled ? 'bg-emerald-400' : 'bg-slate-600'}`} title={r.enabled ? 'Enabled' : 'Disabled'} />
                  </td>
                  <td className="px-4 py-2 text-right flex items-center justify-end gap-1">
                    <button
                      onClick={() => handleEditRule(r)}
                      className="text-slate-500 hover:text-cyan-400 transition-colors"
                    >
                      <span className="material-symbols-outlined text-[16px]">edit</span>
                    </button>
                    <button
                      onClick={() => handleDeleteRule(r.id)}
                      className="text-slate-500 hover:text-red-400 transition-colors"
                    >
                      <span className="material-symbols-outlined text-[16px]">delete</span>
                    </button>
                  </td>
                </tr>
              ))}
              {rules.length === 0 && (
                <tr><td colSpan={6} className="text-center py-4 text-xs text-slate-600">No alert rules configured</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Create rule modal */}
      {showRuleForm && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={() => { setShowRuleForm(false); setEditingRuleId(null); }}>
          <div className="bg-[#0d2328] border border-slate-700/50 rounded-xl w-full max-w-md p-6 space-y-4" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-base font-semibold text-slate-100">{editingRuleId ? 'Edit Alert Rule' : 'New Alert Rule'}</h3>
            <div className="space-y-3">
              <div>
                <label className="block text-xs text-slate-400 mb-1">Name</label>
                <input
                  value={newRule.name}
                  onChange={(e) => setNewRule({ ...newRule, name: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-600 text-sm text-slate-100 focus:border-cyan-500 outline-none"
                  placeholder="My custom rule"
                />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Metric</label>
                  <select
                    value={newRule.metric}
                    onChange={(e) => setNewRule({ ...newRule, metric: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-600 text-sm text-slate-100 focus:border-cyan-500 outline-none"
                  >
                    <option value="db_conn_utilization">Connection Utilization</option>
                    <option value="db_cache_hit_ratio">Cache Hit Ratio</option>
                    <option value="db_repl_lag_bytes">Replication Lag (bytes)</option>
                    <option value="db_deadlocks">Deadlocks</option>
                    <option value="db_slow_query_count">Slow Query Count</option>
                    <option value="db_tps">Transactions/sec</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Condition</label>
                  <select
                    value={newRule.condition}
                    onChange={(e) => setNewRule({ ...newRule, condition: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-600 text-sm text-slate-100 focus:border-cyan-500 outline-none"
                  >
                    <option value="gt">Greater than</option>
                    <option value="lt">Less than</option>
                    <option value="eq">Equal to</option>
                  </select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Threshold</label>
                  <input
                    type="number"
                    value={newRule.threshold}
                    onChange={(e) => setNewRule({ ...newRule, threshold: parseFloat(e.target.value) || 0 })}
                    className="w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-600 text-sm text-slate-100 focus:border-cyan-500 outline-none"
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Cooldown (s)</label>
                  <input
                    type="number"
                    value={newRule.cooldown}
                    onChange={(e) => setNewRule({ ...newRule, cooldown: parseInt(e.target.value) || 0 })}
                    className="w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-600 text-sm text-slate-100 focus:border-cyan-500 outline-none"
                  />
                </div>
              </div>
              <div>
                <label className="block text-xs text-slate-400 mb-1">Severity</label>
                <select
                  value={newRule.severity}
                  onChange={(e) => setNewRule({ ...newRule, severity: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-600 text-sm text-slate-100 focus:border-cyan-500 outline-none"
                >
                  <option value="warning">Warning</option>
                  <option value="critical">Critical</option>
                  <option value="info">Info</option>
                </select>
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button onClick={() => { setShowRuleForm(false); setEditingRuleId(null); }} className="px-4 py-2 text-sm text-slate-400 hover:text-slate-200 transition-colors">Cancel</button>
              <button
                onClick={handleCreateRule}
                disabled={!newRule.name}
                className="px-4 py-2 text-sm bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white rounded-lg transition-colors"
              >
                {editingRuleId ? 'Update' : 'Create'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default DBMonitoring;
