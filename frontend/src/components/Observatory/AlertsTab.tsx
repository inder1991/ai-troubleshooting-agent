import React, { useState, useEffect } from 'react';
import { AlertEvent } from './hooks/useMonitorSnapshot';
import { acknowledgeAlert, exportAlertRules, fetchCompositeAlertRules, createCompositeAlertRule, deleteCompositeAlertRule } from '../../services/api';
import type { CompositeAlertRule, CompositeAlertCondition } from '../../types';

interface Props {
  alerts: AlertEvent[];
  onRefresh: () => void;
}

const severityColors: Record<string, string> = {
  critical: '#ef4444',
  warning: '#f59e0b',
  info: '#e09f3e',
};

const AlertsTab: React.FC<Props> = ({ alerts, onRefresh }) => {
  const [filter, setFilter] = useState<string>('all');
  const [compositeRules, setCompositeRules] = useState<CompositeAlertRule[]>([]);
  const [showCompositeForm, setShowCompositeForm] = useState(false);
  const [compositeForm, setCompositeForm] = useState({ name: '', operator: 'AND' as 'AND' | 'OR', duration_seconds: 60, conditions: [{ metric: '', operator: '>', threshold: 0 }] as CompositeAlertCondition[] });

  const filtered = filter === 'all'
    ? alerts
    : alerts.filter(a => a.severity === filter);

  const handleAck = async (key: string) => {
    try {
      await acknowledgeAlert(key);
      onRefresh();
    } catch {
      // Toast would be nice here
    }
  };

  useEffect(() => {
    fetchCompositeAlertRules().then(setCompositeRules).catch(() => {});
  }, []);

  const handleExportRules = async () => {
    try {
      const blob = await exportAlertRules('json');
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'alert-rules.json';
      a.click();
      URL.revokeObjectURL(url);
    } catch { /* ignore */ }
  };

  const handleCreateComposite = async () => {
    try {
      await createCompositeAlertRule({
        name: compositeForm.name,
        logic: compositeForm.operator,
        duration_seconds: compositeForm.duration_seconds,
        conditions: compositeForm.conditions,
      });
      const updated = await fetchCompositeAlertRules();
      setCompositeRules(updated);
      setShowCompositeForm(false);
      setCompositeForm({ name: '', operator: 'AND', duration_seconds: 60, conditions: [{ metric: '', operator: '>', threshold: 0 }] });
    } catch { /* ignore */ }
  };

  const handleDeleteComposite = async (id: string) => {
    try {
      await deleteCompositeAlertRule(id);
      setCompositeRules(prev => prev.filter(r => r.id !== id));
    } catch { /* ignore */ }
  };

  return (
    <div className="p-6 space-y-4">
      {/* Filter buttons + Export */}
      <div className="flex items-center gap-2">
        {['all', 'critical', 'warning', 'info'].map(s => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            className="px-3 py-1 rounded text-xs font-mono transition-colors"
            style={{
              backgroundColor: filter === s ? '#1a3a40' : 'transparent',
              color: s === 'all' ? '#e8e0d4' : severityColors[s] || '#e8e0d4',
              border: `1px solid ${filter === s ? '#e09f3e' : '#3d3528'}`,
            }}
          >
            {s.toUpperCase()}
            {s !== 'all' && ` (${alerts.filter(a => a.severity === s).length})`}
          </button>
        ))}
        <div className="flex-1" />
        <button
          onClick={handleExportRules}
          style={{
            background: 'rgba(224,159,62,0.08)',
            border: '1px solid rgba(224,159,62,0.2)',
            borderRadius: 8,
            color: '#e09f3e',
            padding: '6px 12px',
            fontSize: 12,
            fontWeight: 600,
          }}
          className="font-mono flex items-center gap-1.5 transition-colors hover:border-[#e09f3e]"
        >
          <span className="material-symbols-outlined" style={{ fontSize: 14 }}>download</span>
          Export Rules
        </button>
      </div>

      {/* Severity Summary */}
      <div className="grid grid-cols-3 gap-3">
        {(['critical', 'warning', 'info'] as const).map(severity => {
          const count = alerts.filter(a => a.severity === severity && !a.acknowledged).length;
          const total = alerts.filter(a => a.severity === severity).length;
          const colors: Record<string, string> = { critical: '#ef4444', warning: '#f59e0b', info: '#e09f3e' };
          const color = colors[severity];
          return (
            <div
              key={severity}
              onClick={() => setFilter(severity)}
              className="rounded-lg border p-3 cursor-pointer transition-all hover:border-[#e09f3e]/50"
              style={{
                backgroundColor: '#0a1a1e',
                borderColor: count > 0 ? `${color}40` : '#3d3528',
                borderLeftWidth: '3px',
                borderLeftColor: color,
              }}
            >
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-mono font-bold uppercase tracking-wider" style={{ color }}>
                  {severity}
                </span>
                <span className="text-lg font-mono font-bold" style={{ color: count > 0 ? color : '#64748b' }}>
                  {count}
                </span>
              </div>
              <div className="text-[10px] font-mono mt-1" style={{ color: '#64748b' }}>
                {total - count} acknowledged
              </div>
            </div>
          );
        })}
      </div>

      {/* Alert list */}
      {filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16">
          <span className="material-symbols-outlined text-4xl mb-3" style={{ color: '#3d3528' }}>
            check_circle
          </span>
          <span className="text-sm font-mono" style={{ color: '#64748b' }}>
            No active alerts
          </span>
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map(alert => (
            <div
              key={alert.key}
              className="rounded border p-3 flex items-center justify-between"
              style={{
                backgroundColor: '#0a1a1e',
                borderColor: (severityColors[alert.severity] || '#3d3528') + '40',
                borderLeftWidth: '3px',
                borderLeftColor: severityColors[alert.severity] || '#3d3528',
                opacity: alert.acknowledged ? 0.5 : 1,
              }}
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span
                    className="text-[9px] font-mono font-bold px-1.5 py-0.5 rounded"
                    style={{
                      backgroundColor: (severityColors[alert.severity] || '#3d3528') + '20',
                      color: severityColors[alert.severity] || '#e8e0d4',
                    }}
                  >
                    {alert.severity.toUpperCase()}
                  </span>
                  <span className="text-sm font-mono" style={{ color: '#e8e0d4' }}>
                    {alert.rule_name}
                  </span>
                  {alert.acknowledged && (
                    <span className="text-[9px] font-mono px-1.5 py-0.5 rounded"
                      style={{ backgroundColor: '#22432920', color: '#64748b' }}>
                      ACK
                    </span>
                  )}
                </div>
                <div className="text-xs font-mono mt-1" style={{ color: '#64748b' }}>
                  {alert.entity_id} — {alert.metric}: {alert.value.toFixed(1)} ({alert.condition} {alert.threshold})
                </div>
                <div className="text-[10px] font-mono mt-0.5" style={{ color: '#4a5568' }}>
                  {new Date(alert.fired_at * 1000).toLocaleString()}
                </div>
              </div>
              {!alert.acknowledged && (
                <button
                  onClick={() => handleAck(alert.key)}
                  className="text-xs font-mono px-3 py-1.5 rounded border transition-colors hover:border-[#e09f3e]"
                  style={{ borderColor: '#3d3528', color: '#64748b' }}
                >
                  Acknowledge
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {/* ===== Composite Rules Section ===== */}
      <div style={{ borderTop: '1px solid rgba(224,159,62,0.12)', paddingTop: 20, marginTop: 8 }}>
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm font-mono font-bold" style={{ color: '#e8e0d4' }}>Composite Rules</span>
          <button
            onClick={() => setShowCompositeForm(prev => !prev)}
            style={{
              background: 'rgba(224,159,62,0.08)',
              border: '1px solid rgba(224,159,62,0.2)',
              borderRadius: 8,
              color: '#e09f3e',
              padding: '4px 10px',
              fontSize: 11,
              fontWeight: 600,
            }}
            className="font-mono flex items-center gap-1 transition-colors hover:border-[#e09f3e]"
          >
            <span className="material-symbols-outlined" style={{ fontSize: 14 }}>
              {showCompositeForm ? 'close' : 'add'}
            </span>
            {showCompositeForm ? 'Cancel' : 'Add'}
          </button>
        </div>

        {/* Add Composite Rule Form */}
        {showCompositeForm && (
          <div
            className="rounded-lg border p-4 mb-3 space-y-3"
            style={{
              backgroundColor: 'rgba(224,159,62,0.04)',
              borderColor: 'rgba(224,159,62,0.12)',
              borderRadius: 10,
            }}
          >
            {/* Name */}
            <div>
              <label className="text-[10px] font-mono font-bold uppercase tracking-wider block mb-1" style={{ color: '#64748b' }}>
                Rule Name
              </label>
              <input
                type="text"
                value={compositeForm.name}
                onChange={e => setCompositeForm(prev => ({ ...prev, name: e.target.value }))}
                placeholder="e.g. High CPU + Memory Pressure"
                className="w-full px-3 py-1.5 rounded text-xs font-mono"
                style={{
                  backgroundColor: '#0a1a1e',
                  border: '1px solid #3d3528',
                  color: '#e8e0d4',
                  outline: 'none',
                }}
              />
            </div>

            {/* Operator Toggle */}
            <div>
              <label className="text-[10px] font-mono font-bold uppercase tracking-wider block mb-1" style={{ color: '#64748b' }}>
                Logic Operator
              </label>
              <div className="flex gap-2">
                {(['AND', 'OR'] as const).map(op => (
                  <button
                    key={op}
                    onClick={() => setCompositeForm(prev => ({ ...prev, operator: op }))}
                    className="px-3 py-1 rounded text-xs font-mono font-bold transition-colors"
                    style={{
                      backgroundColor: compositeForm.operator === op ? 'rgba(224,159,62,0.15)' : 'transparent',
                      color: compositeForm.operator === op ? '#e09f3e' : '#64748b',
                      border: `1px solid ${compositeForm.operator === op ? '#e09f3e' : '#3d3528'}`,
                    }}
                  >
                    {op}
                  </button>
                ))}
              </div>
            </div>

            {/* Conditions */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="text-[10px] font-mono font-bold uppercase tracking-wider" style={{ color: '#64748b' }}>
                  Conditions
                </label>
                <button
                  onClick={() =>
                    setCompositeForm(prev => ({
                      ...prev,
                      conditions: [...prev.conditions, { metric: '', operator: '>', threshold: 0 }],
                    }))
                  }
                  className="text-[10px] font-mono flex items-center gap-0.5 transition-colors"
                  style={{ color: '#e09f3e' }}
                >
                  <span className="material-symbols-outlined" style={{ fontSize: 12 }}>add</span>
                  Add Condition
                </button>
              </div>
              <div className="space-y-2">
                {compositeForm.conditions.map((cond, idx) => (
                  <div key={idx} className="flex items-center gap-2">
                    <input
                      type="text"
                      value={cond.metric}
                      onChange={e => {
                        const next = [...compositeForm.conditions];
                        next[idx] = { ...next[idx], metric: e.target.value };
                        setCompositeForm(prev => ({ ...prev, conditions: next }));
                      }}
                      placeholder="metric name"
                      className="flex-1 px-2 py-1 rounded text-xs font-mono"
                      style={{ backgroundColor: '#0a1a1e', border: '1px solid #3d3528', color: '#e8e0d4', outline: 'none' }}
                    />
                    <select
                      value={cond.operator}
                      onChange={e => {
                        const next = [...compositeForm.conditions];
                        next[idx] = { ...next[idx], operator: e.target.value as CompositeAlertCondition['operator'] };
                        setCompositeForm(prev => ({ ...prev, conditions: next }));
                      }}
                      className="px-2 py-1 rounded text-xs font-mono"
                      style={{ backgroundColor: '#0a1a1e', border: '1px solid #3d3528', color: '#e8e0d4', outline: 'none' }}
                    >
                      {['>', '<', '>=', '<=', '==', '!='].map(op => (
                        <option key={op} value={op}>{op}</option>
                      ))}
                    </select>
                    <input
                      type="number"
                      value={cond.threshold}
                      onChange={e => {
                        const next = [...compositeForm.conditions];
                        next[idx] = { ...next[idx], threshold: parseFloat(e.target.value) || 0 };
                        setCompositeForm(prev => ({ ...prev, conditions: next }));
                      }}
                      className="w-20 px-2 py-1 rounded text-xs font-mono"
                      style={{ backgroundColor: '#0a1a1e', border: '1px solid #3d3528', color: '#e8e0d4', outline: 'none' }}
                    />
                    {compositeForm.conditions.length > 1 && (
                      <button
                        onClick={() => {
                          const next = compositeForm.conditions.filter((_, i) => i !== idx);
                          setCompositeForm(prev => ({ ...prev, conditions: next }));
                        }}
                        className="transition-colors"
                        style={{ color: '#ef4444' }}
                      >
                        <span className="material-symbols-outlined" style={{ fontSize: 16 }}>remove_circle</span>
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* Duration */}
            <div>
              <label className="text-[10px] font-mono font-bold uppercase tracking-wider block mb-1" style={{ color: '#64748b' }}>
                Duration (seconds)
              </label>
              <input
                type="number"
                value={compositeForm.duration_seconds}
                onChange={e => setCompositeForm(prev => ({ ...prev, duration_seconds: parseInt(e.target.value) || 0 }))}
                className="w-32 px-3 py-1.5 rounded text-xs font-mono"
                style={{ backgroundColor: '#0a1a1e', border: '1px solid #3d3528', color: '#e8e0d4', outline: 'none' }}
              />
            </div>

            {/* Actions */}
            <div className="flex gap-2 pt-1">
              <button
                onClick={handleCreateComposite}
                disabled={!compositeForm.name || compositeForm.conditions.some(c => !c.metric)}
                className="px-4 py-1.5 rounded text-xs font-mono font-bold transition-colors"
                style={{
                  backgroundColor: !compositeForm.name || compositeForm.conditions.some(c => !c.metric) ? '#1a3a40' : '#e09f3e',
                  color: !compositeForm.name || compositeForm.conditions.some(c => !c.metric) ? '#64748b' : '#1a1814',
                  border: 'none',
                  cursor: !compositeForm.name || compositeForm.conditions.some(c => !c.metric) ? 'not-allowed' : 'pointer',
                }}
              >
                Create
              </button>
              <button
                onClick={() => setShowCompositeForm(false)}
                className="px-4 py-1.5 rounded text-xs font-mono transition-colors"
                style={{ border: '1px solid #3d3528', color: '#64748b', background: 'transparent' }}
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {/* Composite Rules List */}
        {compositeRules.length === 0 && !showCompositeForm ? (
          <div className="text-center py-6">
            <span className="text-xs font-mono" style={{ color: '#4a5568' }}>No composite rules defined</span>
          </div>
        ) : (
          <div className="space-y-2">
            {compositeRules.map(rule => (
              <div
                key={rule.id}
                className="rounded-lg border p-3 flex items-start justify-between"
                style={{
                  backgroundColor: 'rgba(224,159,62,0.04)',
                  borderColor: 'rgba(224,159,62,0.12)',
                  borderRadius: 10,
                }}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm font-mono font-bold" style={{ color: '#e8e0d4' }}>{rule.name}</span>
                    <span
                      className="text-[9px] font-mono font-bold px-1.5 py-0.5 rounded"
                      style={{
                        backgroundColor: rule.logic === 'AND' ? 'rgba(224,159,62,0.15)' : 'rgba(245,158,11,0.15)',
                        color: rule.logic === 'AND' ? '#e09f3e' : '#f59e0b',
                      }}
                    >
                      {rule.logic}
                    </span>
                    {rule.severity && (
                      <span
                        className="text-[9px] font-mono font-bold px-1.5 py-0.5 rounded"
                        style={{
                          backgroundColor: (severityColors[rule.severity] || '#3d3528') + '20',
                          color: severityColors[rule.severity] || '#e8e0d4',
                        }}
                      >
                        {rule.severity.toUpperCase()}
                      </span>
                    )}
                  </div>
                  <div className="space-y-0.5">
                    {rule.conditions.map((c, i) => (
                      <div key={i} className="text-[11px] font-mono" style={{ color: '#8a7e6b' }}>
                        <span style={{ color: '#e09f3e' }}>{c.metric}</span>{' '}
                        <span style={{ color: '#64748b' }}>{c.operator}</span>{' '}
                        <span style={{ color: '#e8e0d4' }}>{c.threshold}</span>
                        {i < rule.conditions.length - 1 && (
                          <span style={{ color: '#4a5568', marginLeft: 6 }}>{rule.logic}</span>
                        )}
                      </div>
                    ))}
                  </div>
                  <div className="text-[10px] font-mono mt-1" style={{ color: '#4a5568' }}>
                    Duration: {rule.duration_seconds}s
                    {rule.created_at && <> &middot; Created {new Date(rule.created_at).toLocaleDateString()}</>}
                  </div>
                </div>
                <button
                  onClick={() => handleDeleteComposite(rule.id)}
                  className="ml-2 transition-colors hover:text-red-400"
                  style={{ color: '#64748b' }}
                  title="Delete rule"
                >
                  <span className="material-symbols-outlined" style={{ fontSize: 16 }}>delete</span>
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default AlertsTab;
