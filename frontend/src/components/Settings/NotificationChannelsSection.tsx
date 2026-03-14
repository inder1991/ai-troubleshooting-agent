import React, { useState, useEffect, useCallback } from 'react';
import {
  fetchNotificationChannels,
  createNotificationChannel,
  deleteNotificationChannel,
  fetchAlertRoutings,
  createAlertRouting,
  deleteAlertRouting,
  fetchEscalationPolicies,
  createEscalationPolicy,
  deleteEscalationPolicy,
} from '../../services/api';
import type {
  NotificationChannel,
  AlertRouting,
  EscalationPolicy,
  EscalationStep,
} from '../../types';

// ── Shared inline styles ────────────────────────────────────────────
const inputStyle: React.CSSProperties = {
  backgroundColor: 'rgba(30,47,51,0.6)',
  border: '1px solid #3d3528',
  borderRadius: '0.375rem',
  color: '#fff',
  padding: '6px 12px',
  fontSize: '0.8125rem',
  outline: 'none',
  width: '100%',
};

const selectStyle: React.CSSProperties = {
  ...inputStyle,
  cursor: 'pointer',
};

const sectionHeadingStyle: React.CSSProperties = {
  color: '#e09f3e',
  fontSize: '0.8125rem',
  fontWeight: 700,
  textTransform: 'uppercase' as const,
  letterSpacing: '0.05em',
  marginBottom: '0.75rem',
};

const tableHeaderStyle: React.CSSProperties = {
  color: '#8fc3cc',
  fontSize: '0.6875rem',
  fontWeight: 700,
  textTransform: 'uppercase' as const,
  letterSpacing: '0.08em',
  padding: '8px 12px',
  textAlign: 'left' as const,
  borderBottom: '1px solid #3d3528',
};

const tableCellStyle: React.CSSProperties = {
  padding: '10px 12px',
  fontSize: '0.8125rem',
  color: '#e8e0d4',
  borderBottom: '1px solid rgba(34,67,73,0.5)',
};

const cardStyle: React.CSSProperties = {
  backgroundColor: 'rgba(15,32,35,0.6)',
  border: '1px solid #3d3528',
  borderRadius: '0.75rem',
  padding: '1.25rem',
  marginBottom: '1.5rem',
};

const addBtnStyle: React.CSSProperties = {
  backgroundColor: '#e09f3e',
  color: '#1a1814',
  border: 'none',
  borderRadius: '0.375rem',
  padding: '6px 16px',
  fontSize: '0.75rem',
  fontWeight: 700,
  cursor: 'pointer',
  textTransform: 'uppercase' as const,
  letterSpacing: '0.03em',
};

const deleteBtnStyle: React.CSSProperties = {
  backgroundColor: 'transparent',
  border: '1px solid rgba(239,68,68,0.3)',
  borderRadius: '0.375rem',
  padding: '4px 10px',
  fontSize: '0.6875rem',
  fontWeight: 700,
  color: '#f87171',
  cursor: 'pointer',
  textTransform: 'uppercase' as const,
};

const badgeStyle = (type: string): React.CSSProperties => {
  const colors: Record<string, string> = {
    slack: '#4A154B',
    email: '#1e40af',
    webhook: '#854d0e',
    pagerduty: '#047857',
  };
  return {
    display: 'inline-block',
    backgroundColor: `${colors[type] || '#334155'}33`,
    color: type === 'slack' ? '#c084fc' : type === 'email' ? '#60a5fa' : type === 'webhook' ? '#fbbf24' : '#34d399',
    border: `1px solid ${colors[type] || '#334155'}55`,
    borderRadius: '0.25rem',
    padding: '2px 8px',
    fontSize: '0.6875rem',
    fontWeight: 600,
    textTransform: 'uppercase' as const,
    letterSpacing: '0.04em',
  };
};

const errorBannerStyle: React.CSSProperties = {
  backgroundColor: 'rgba(239,68,68,0.1)',
  border: '1px solid rgba(239,68,68,0.3)',
  borderRadius: '0.5rem',
  padding: '8px 12px',
  color: '#f87171',
  fontSize: '0.75rem',
  marginBottom: '0.75rem',
};

const dividerStyle: React.CSSProperties = {
  borderTop: '1px solid #3d3528',
  margin: '4px 0',
};

// ── Channel type options ────────────────────────────────────────────
const CHANNEL_TYPES = ['slack', 'email', 'webhook', 'pagerduty'] as const;

// ── Main component ──────────────────────────────────────────────────
const NotificationChannelsSection: React.FC = () => {
  // ── Data state ──
  const [channels, setChannels] = useState<NotificationChannel[]>([]);
  const [routings, setRoutings] = useState<AlertRouting[]>([]);
  const [policies, setPolicies] = useState<EscalationPolicy[]>([]);

  // ── Loading / error ──
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // ── Add channel form ──
  const [chName, setChName] = useState('');
  const [chType, setChType] = useState<typeof CHANNEL_TYPES[number]>('slack');
  const [chUrl, setChUrl] = useState('');

  // ── Add routing form ──
  const [rtRuleId, setRtRuleId] = useState('');
  const [rtChannelId, setRtChannelId] = useState('');

  // ── Add escalation policy form ──
  const [epName, setEpName] = useState('');
  const [epSteps, setEpSteps] = useState<EscalationStep[]>([
    { level: 1, channel_id: '', wait_minutes: 5 },
  ]);

  // ── Load all data ──
  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [ch, rt, ep] = await Promise.all([
        fetchNotificationChannels(),
        fetchAlertRoutings(),
        fetchEscalationPolicies(),
      ]);
      setChannels(ch);
      setRoutings(rt);
      setPolicies(ep);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load notification data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // ── Handlers: Channels ──
  const handleAddChannel = async () => {
    if (!chName.trim() || !chUrl.trim()) return;
    setError(null);
    try {
      const created = await createNotificationChannel({
        name: chName.trim(),
        type: chType,
        config: { url: chUrl.trim() },
      });
      setChannels((prev) => [...prev, created]);
      setChName('');
      setChUrl('');
      setChType('slack');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to create channel');
    }
  };

  const handleDeleteChannel = async (id: string) => {
    setError(null);
    try {
      await deleteNotificationChannel(id);
      setChannels((prev) => prev.filter((c) => c.id !== id));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to delete channel');
    }
  };

  // ── Handlers: Routings ──
  const handleAddRouting = async () => {
    if (!rtRuleId.trim() || !rtChannelId.trim()) return;
    setError(null);
    try {
      const created = await createAlertRouting({
        rule_id: rtRuleId.trim(),
        channel_id: rtChannelId.trim(),
      });
      setRoutings((prev) => [...prev, created]);
      setRtRuleId('');
      setRtChannelId('');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to create routing');
    }
  };

  const handleDeleteRouting = async (id: string) => {
    setError(null);
    try {
      await deleteAlertRouting(id);
      setRoutings((prev) => prev.filter((r) => r.id !== id));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to delete routing');
    }
  };

  // ── Handlers: Escalation Policies ──
  const handleAddStep = () => {
    setEpSteps((prev) => [
      ...prev,
      { level: prev.length + 1, channel_id: '', wait_minutes: 5 },
    ]);
  };

  const handleRemoveStep = (index: number) => {
    setEpSteps((prev) =>
      prev
        .filter((_, i) => i !== index)
        .map((s, i) => ({ ...s, level: i + 1 })),
    );
  };

  const handleStepChange = (
    index: number,
    field: 'channel_id' | 'wait_minutes',
    value: string,
  ) => {
    setEpSteps((prev) =>
      prev.map((s, i) =>
        i === index
          ? {
              ...s,
              [field]: field === 'wait_minutes' ? parseInt(value, 10) || 0 : value,
            }
          : s,
      ),
    );
  };

  const handleAddPolicy = async () => {
    if (!epName.trim() || epSteps.length === 0) return;
    const hasEmptyChannel = epSteps.some((s) => !s.channel_id.trim());
    if (hasEmptyChannel) return;
    setError(null);
    try {
      const created = await createEscalationPolicy({
        name: epName.trim(),
        steps: epSteps.map((s) => ({
          level: s.level,
          channel_id: s.channel_id.trim(),
          wait_minutes: s.wait_minutes,
        })),
      });
      setPolicies((prev) => [...prev, created]);
      setEpName('');
      setEpSteps([{ level: 1, channel_id: '', wait_minutes: 5 }]);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to create escalation policy');
    }
  };

  const handleDeletePolicy = async (id: string) => {
    setError(null);
    try {
      await deleteEscalationPolicy(id);
      setPolicies((prev) => prev.filter((p) => p.id !== id));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to delete escalation policy');
    }
  };

  // ── Resolve channel name helper ──
  const channelNameById = (id: string): string => {
    const ch = channels.find((c) => c.id === id);
    return ch ? ch.name : id;
  };

  // ── Render ──
  if (loading) {
    return (
      <div style={cardStyle}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span
            className="material-symbols-outlined text-lg"
            style={{ color: '#e09f3e' }}
          >
            notifications
          </span>
          <h2 style={sectionHeadingStyle}>Notification Channels</h2>
        </div>
        <p style={{ color: '#8fc3cc', fontSize: '0.8125rem' }}>Loading...</p>
      </div>
    );
  }

  return (
    <div>
      {/* Error banner */}
      {error && (
        <div style={errorBannerStyle}>
          <span className="material-symbols-outlined text-sm" style={{ verticalAlign: 'middle', marginRight: 6 }}>
            error
          </span>
          {error}
        </div>
      )}

      {/* ────────────────────────────────────────────────────────────────
          Section 1: Notification Channels List
         ──────────────────────────────────────────────────────────────── */}
      <div style={cardStyle}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
          <span
            className="material-symbols-outlined text-lg"
            style={{ color: '#e09f3e' }}
          >
            notifications
          </span>
          <h2 style={{ ...sectionHeadingStyle, marginBottom: 0 }}>Notification Channels</h2>
        </div>

        {channels.length === 0 ? (
          <p style={{ color: '#8fc3cc', fontSize: '0.75rem', fontStyle: 'italic' }}>
            No channels configured yet. Add one below.
          </p>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  <th style={tableHeaderStyle}>Name</th>
                  <th style={tableHeaderStyle}>Type</th>
                  <th style={tableHeaderStyle}>Config URL</th>
                  <th style={{ ...tableHeaderStyle, textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {channels.map((ch) => (
                  <tr key={ch.id}>
                    <td style={tableCellStyle}>
                      <span style={{ fontWeight: 600, color: '#fff' }}>{ch.name}</span>
                    </td>
                    <td style={tableCellStyle}>
                      <span style={badgeStyle(ch.type)}>{ch.type}</span>
                    </td>
                    <td style={tableCellStyle}>
                      <span style={{ fontFamily: 'monospace', fontSize: '0.75rem', color: '#8a7e6b' }}>
                        {ch.config?.url || ch.config?.endpoint || Object.values(ch.config)[0] || '-'}
                      </span>
                    </td>
                    <td style={{ ...tableCellStyle, textAlign: 'right' }}>
                      <button
                        onClick={() => handleDeleteChannel(ch.id)}
                        style={deleteBtnStyle}
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* ── Add Channel form ── */}
        <div style={{ ...dividerStyle, margin: '16px 0' }} />
        <h3 style={{ ...sectionHeadingStyle, fontSize: '0.6875rem', color: '#8fc3cc' }}>
          Add Channel
        </h3>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <div style={{ flex: '1 1 160px', minWidth: 120 }}>
            <label style={{ display: 'block', color: '#8fc3cc', fontSize: '0.6875rem', marginBottom: 4 }}>
              Name
            </label>
            <input
              type="text"
              value={chName}
              onChange={(e) => setChName(e.target.value)}
              placeholder="e.g. #ops-alerts"
              style={inputStyle}
            />
          </div>
          <div style={{ flex: '0 0 140px' }}>
            <label style={{ display: 'block', color: '#8fc3cc', fontSize: '0.6875rem', marginBottom: 4 }}>
              Type
            </label>
            <select
              value={chType}
              onChange={(e) => setChType(e.target.value as typeof CHANNEL_TYPES[number])}
              style={selectStyle}
            >
              {CHANNEL_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>
          <div style={{ flex: '2 1 200px', minWidth: 160 }}>
            <label style={{ display: 'block', color: '#8fc3cc', fontSize: '0.6875rem', marginBottom: 4 }}>
              URL / Endpoint
            </label>
            <input
              type="text"
              value={chUrl}
              onChange={(e) => setChUrl(e.target.value)}
              placeholder="https://hooks.slack.com/services/..."
              style={inputStyle}
            />
          </div>
          <div style={{ flex: '0 0 auto' }}>
            <button
              onClick={handleAddChannel}
              disabled={!chName.trim() || !chUrl.trim()}
              style={{
                ...addBtnStyle,
                opacity: !chName.trim() || !chUrl.trim() ? 0.5 : 1,
                cursor: !chName.trim() || !chUrl.trim() ? 'not-allowed' : 'pointer',
              }}
            >
              Add
            </button>
          </div>
        </div>
      </div>

      {/* ────────────────────────────────────────────────────────────────
          Section 2: Alert Routing List
         ──────────────────────────────────────────────────────────────── */}
      <div style={cardStyle}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
          <span
            className="material-symbols-outlined text-lg"
            style={{ color: '#e09f3e' }}
          >
            route
          </span>
          <h2 style={{ ...sectionHeadingStyle, marginBottom: 0 }}>Alert Routing</h2>
        </div>

        {routings.length === 0 ? (
          <p style={{ color: '#8fc3cc', fontSize: '0.75rem', fontStyle: 'italic' }}>
            No routing rules configured yet.
          </p>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  <th style={tableHeaderStyle}>Rule</th>
                  <th style={tableHeaderStyle}>
                    <span className="material-symbols-outlined text-xs" style={{ verticalAlign: 'middle', marginRight: 4 }}>
                      arrow_forward
                    </span>
                    Channel
                  </th>
                  <th style={{ ...tableHeaderStyle, textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {routings.map((rt) => (
                  <tr key={rt.id}>
                    <td style={tableCellStyle}>
                      <span style={{ fontFamily: 'monospace', fontSize: '0.75rem', color: '#fbbf24' }}>
                        {rt.rule_name || rt.rule_id}
                      </span>
                    </td>
                    <td style={tableCellStyle}>
                      <span style={{ color: '#fff', fontWeight: 600 }}>
                        {rt.channel_name || channelNameById(rt.channel_id)}
                      </span>
                    </td>
                    <td style={{ ...tableCellStyle, textAlign: 'right' }}>
                      <button
                        onClick={() => handleDeleteRouting(rt.id)}
                        style={deleteBtnStyle}
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* ── Add Routing form ── */}
        <div style={{ ...dividerStyle, margin: '16px 0' }} />
        <h3 style={{ ...sectionHeadingStyle, fontSize: '0.6875rem', color: '#8fc3cc' }}>
          Add Routing
        </h3>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <div style={{ flex: '1 1 180px', minWidth: 140 }}>
            <label style={{ display: 'block', color: '#8fc3cc', fontSize: '0.6875rem', marginBottom: 4 }}>
              Rule ID
            </label>
            <input
              type="text"
              value={rtRuleId}
              onChange={(e) => setRtRuleId(e.target.value)}
              placeholder="alert-rule-uuid"
              style={inputStyle}
            />
          </div>
          <div style={{ flex: '1 1 180px', minWidth: 140 }}>
            <label style={{ display: 'block', color: '#8fc3cc', fontSize: '0.6875rem', marginBottom: 4 }}>
              Channel ID
            </label>
            <input
              type="text"
              value={rtChannelId}
              onChange={(e) => setRtChannelId(e.target.value)}
              placeholder="channel-uuid"
              style={inputStyle}
            />
          </div>
          <div style={{ flex: '0 0 auto' }}>
            <button
              onClick={handleAddRouting}
              disabled={!rtRuleId.trim() || !rtChannelId.trim()}
              style={{
                ...addBtnStyle,
                opacity: !rtRuleId.trim() || !rtChannelId.trim() ? 0.5 : 1,
                cursor: !rtRuleId.trim() || !rtChannelId.trim() ? 'not-allowed' : 'pointer',
              }}
            >
              Add
            </button>
          </div>
        </div>
      </div>

      {/* ────────────────────────────────────────────────────────────────
          Section 3: Escalation Policies
         ──────────────────────────────────────────────────────────────── */}
      <div style={cardStyle}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
          <span
            className="material-symbols-outlined text-lg"
            style={{ color: '#e09f3e' }}
          >
            escalator_warning
          </span>
          <h2 style={{ ...sectionHeadingStyle, marginBottom: 0 }}>Escalation Policies</h2>
        </div>

        {policies.length === 0 ? (
          <p style={{ color: '#8fc3cc', fontSize: '0.75rem', fontStyle: 'italic' }}>
            No escalation policies defined yet.
          </p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {policies.map((policy) => (
              <div
                key={policy.id}
                style={{
                  backgroundColor: 'rgba(24,48,52,0.3)',
                  border: '1px solid #3d3528',
                  borderRadius: '0.5rem',
                  padding: '1rem',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                  <span style={{ color: '#fff', fontWeight: 700, fontSize: '0.875rem' }}>
                    {policy.name}
                  </span>
                  <button
                    onClick={() => handleDeletePolicy(policy.id)}
                    style={deleteBtnStyle}
                  >
                    Delete
                  </button>
                </div>

                {/* Steps visualization */}
                <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '0.5rem' }}>
                  {policy.steps
                    .sort((a, b) => a.level - b.level)
                    .map((step, idx) => (
                      <React.Fragment key={idx}>
                        <div
                          style={{
                            backgroundColor: 'rgba(224,159,62,0.08)',
                            border: '1px solid rgba(224,159,62,0.2)',
                            borderRadius: '0.375rem',
                            padding: '6px 12px',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '0.375rem',
                          }}
                        >
                          <span style={{
                            color: '#e09f3e',
                            fontSize: '0.625rem',
                            fontWeight: 700,
                            textTransform: 'uppercase',
                            letterSpacing: '0.06em',
                          }}>
                            L{step.level}
                          </span>
                          <span style={{ color: '#e8e0d4', fontSize: '0.75rem', fontWeight: 600 }}>
                            {step.channel_name || channelNameById(step.channel_id)}
                          </span>
                        </div>

                        {idx < policy.steps.length - 1 && (
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', color: '#8fc3cc' }}>
                            <span style={{ fontSize: '0.625rem' }}>
                              wait {step.wait_minutes}m
                            </span>
                            <span
                              className="material-symbols-outlined"
                              style={{ fontSize: '14px', color: '#8fc3cc' }}
                            >
                              arrow_forward
                            </span>
                          </div>
                        )}
                      </React.Fragment>
                    ))}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* ── Add Escalation Policy form ── */}
        <div style={{ ...dividerStyle, margin: '16px 0' }} />
        <h3 style={{ ...sectionHeadingStyle, fontSize: '0.6875rem', color: '#8fc3cc' }}>
          Add Escalation Policy
        </h3>

        <div style={{ marginBottom: '0.75rem' }}>
          <label style={{ display: 'block', color: '#8fc3cc', fontSize: '0.6875rem', marginBottom: 4 }}>
            Policy Name
          </label>
          <input
            type="text"
            value={epName}
            onChange={(e) => setEpName(e.target.value)}
            placeholder="e.g. Production Critical Path"
            style={{ ...inputStyle, maxWidth: 360 }}
          />
        </div>

        {/* Steps builder */}
        <div style={{ marginBottom: '0.75rem' }}>
          <label style={{ display: 'block', color: '#8fc3cc', fontSize: '0.6875rem', marginBottom: 8 }}>
            Escalation Steps
          </label>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {epSteps.map((step, idx) => (
              <div
                key={idx}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  flexWrap: 'wrap',
                }}
              >
                {/* Level badge */}
                <span
                  style={{
                    color: '#e09f3e',
                    fontSize: '0.6875rem',
                    fontWeight: 700,
                    minWidth: 28,
                    textAlign: 'center',
                  }}
                >
                  L{step.level}
                </span>

                {/* Channel ID input */}
                <input
                  type="text"
                  value={step.channel_id}
                  onChange={(e) => handleStepChange(idx, 'channel_id', e.target.value)}
                  placeholder="channel-uuid"
                  style={{ ...inputStyle, flex: '1 1 160px', minWidth: 120 }}
                />

                {/* Wait minutes */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                  <span style={{ color: '#8fc3cc', fontSize: '0.6875rem', whiteSpace: 'nowrap' }}>
                    wait
                  </span>
                  <input
                    type="number"
                    value={step.wait_minutes}
                    onChange={(e) => handleStepChange(idx, 'wait_minutes', e.target.value)}
                    min={0}
                    style={{ ...inputStyle, width: 60, textAlign: 'center' }}
                  />
                  <span style={{ color: '#8fc3cc', fontSize: '0.6875rem' }}>min</span>
                </div>

                {/* Remove step button */}
                {epSteps.length > 1 && (
                  <button
                    onClick={() => handleRemoveStep(idx)}
                    style={{
                      background: 'transparent',
                      border: 'none',
                      color: '#f87171',
                      cursor: 'pointer',
                      padding: '2px 4px',
                      display: 'flex',
                      alignItems: 'center',
                    }}
                    title="Remove step"
                  >
                    <span className="material-symbols-outlined" style={{ fontSize: '18px' }}>
                      close
                    </span>
                  </button>
                )}
              </div>
            ))}
          </div>

          {/* Add step button */}
          <button
            onClick={handleAddStep}
            style={{
              backgroundColor: 'transparent',
              border: '1px dashed #3d3528',
              borderRadius: '0.375rem',
              padding: '6px 12px',
              color: '#8fc3cc',
              fontSize: '0.6875rem',
              fontWeight: 600,
              cursor: 'pointer',
              marginTop: '0.5rem',
              display: 'flex',
              alignItems: 'center',
              gap: '0.25rem',
            }}
          >
            <span className="material-symbols-outlined" style={{ fontSize: '14px' }}>
              add
            </span>
            Add Step
          </button>
        </div>

        <button
          onClick={handleAddPolicy}
          disabled={!epName.trim() || epSteps.some((s) => !s.channel_id.trim())}
          style={{
            ...addBtnStyle,
            opacity: !epName.trim() || epSteps.some((s) => !s.channel_id.trim()) ? 0.5 : 1,
            cursor: !epName.trim() || epSteps.some((s) => !s.channel_id.trim()) ? 'not-allowed' : 'pointer',
          }}
        >
          Create Policy
        </button>
      </div>
    </div>
  );
};

export default NotificationChannelsSection;
