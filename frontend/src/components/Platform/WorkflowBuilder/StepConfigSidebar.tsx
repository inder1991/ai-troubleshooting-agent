import React, { useState, useEffect, useRef } from 'react';
import { WorkflowStep } from './workflowParser';
import { t } from '../../../styles/tokens';

interface Props {
  step: WorkflowStep;
  allSteps: WorkflowStep[];
  onUpdate: (updated: WorkflowStep) => void;
  onDelete: (stepId: string) => void;
  onClose: () => void;
  onOpenAgentPicker: () => void;
}

// ── Shared input style helpers ────────────────────────────────────────────────
const inputBase: React.CSSProperties = {
  background: t.bgDeep,
  border: `1px solid ${t.borderDefault}`,
  borderRadius: 5,
  color: t.textPrimary,
  fontSize: 11,
  fontFamily: 'inherit',
  padding: '5px 8px',
  width: '100%',
  boxSizing: 'border-box',
  outline: 'none',
  transition: 'border-color 0.12s',
};

const focusBorder = (el: HTMLElement) => { el.style.borderColor = t.cyanBorder; };
const blurBorder  = (el: HTMLElement) => { el.style.borderColor = t.borderDefault; };

// ── Section header ────────────────────────────────────────────────────────────
const SectionHeader: React.FC<{ label: string }> = ({ label }) => (
  <div
    style={{
      fontSize: 10,
      textTransform: 'uppercase',
      letterSpacing: '0.12em',
      color: t.textFaint,
      marginBottom: 8,
      fontFamily: 'inherit',
    }}
  >
    {label}
  </div>
);

// ── Field row ─────────────────────────────────────────────────────────────────
const FieldRow: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div style={{ marginBottom: 10 }}>
    <div style={{ fontSize: 10, color: t.textSecondary, marginBottom: 4, fontFamily: 'inherit' }}>
      {label}
    </div>
    {children}
  </div>
);

// ── Section divider ───────────────────────────────────────────────────────────
const Divider: React.FC = () => (
  <div style={{ borderTop: `1px solid ${t.borderSubtle}`, margin: '14px 0' }} />
);

// ── Toggle switch ─────────────────────────────────────────────────────────────
const Toggle: React.FC<{ checked: boolean; onChange: (val: boolean) => void; id: string }> = ({
  checked,
  onChange,
  id,
}) => (
  <button
    role="switch"
    aria-checked={checked}
    id={id}
    onClick={() => onChange(!checked)}
    style={{
      width: 32,
      height: 18,
      borderRadius: 9,
      background: checked ? t.cyan : t.bgTrack,
      border: `1px solid ${checked ? t.cyanBorder : t.borderDefault}`,
      position: 'relative',
      flexShrink: 0,
      cursor: 'pointer',
      transition: 'background 0.15s, border-color 0.15s',
      outline: 'none',
    }}
    onFocus={e => { e.currentTarget.style.boxShadow = `0 0 0 2px ${t.cyanBorder}`; }}
    onBlur={e => { e.currentTarget.style.boxShadow = 'none'; }}
  >
    <span
      style={{
        position: 'absolute',
        top: 2,
        left: checked ? 14 : 2,
        width: 12,
        height: 12,
        borderRadius: '50%',
        background: t.textPrimary,
        transition: 'left 0.15s',
      }}
    />
  </button>
);

// ── Main component ────────────────────────────────────────────────────────────
const StepConfigSidebar: React.FC<Props> = ({
  step,
  allSteps,
  onUpdate,
  onDelete,
  onClose,
  onOpenAgentPicker,
}) => {
  const [confirmDelete, setConfirmDelete]     = useState(false);
  const [depDropdownOpen, setDepDropdownOpen] = useState(false);
  const depDropdownRef                         = useRef<HTMLDivElement>(null);

  // Close dep dropdown on outside click
  useEffect(() => {
    if (!depDropdownOpen) return;
    const handler = (e: MouseEvent) => {
      if (depDropdownRef.current && !depDropdownRef.current.contains(e.target as Node)) {
        setDepDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [depDropdownOpen]);

  // Reset confirm delete when step changes
  useEffect(() => {
    setConfirmDelete(false);
    setDepDropdownOpen(false);
  }, [step.id]);

  // ── Helpers ────────────────────────────────────────────────────────────────
  const update = (patch: Partial<WorkflowStep>) => onUpdate({ ...step, ...patch });

  const removeDep = (depId: string) =>
    update({ depends_on: step.depends_on.filter(d => d !== depId) });

  const addDep = (depId: string) => {
    if (!step.depends_on.includes(depId)) {
      update({ depends_on: [...step.depends_on, depId] });
    }
    setDepDropdownOpen(false);
  };

  const availableDeps = allSteps.filter(
    s => s.id !== step.id && !step.depends_on.includes(s.id),
  );

  const depLabel = (depId: string) => {
    const found = allSteps.find(s => s.id === depId);
    return found?.label || found?.id || depId;
  };

  // Agent parameters
  const [params, setParams] = useState<{ key: string; value: string; _id: string }[]>(() =>
    Object.entries(step.parameters ?? {}).map(([k, v]) => ({
      key: k,
      value: v,
      _id: Math.random().toString(36).slice(2),
    }))
  );

  // Reset params when step changes
  useEffect(() => {
    setParams(
      Object.entries(step.parameters ?? {}).map(([k, v]) => ({
        key: k,
        value: v,
        _id: Math.random().toString(36).slice(2),
      }))
    );
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step.id]);

  const addParam = () =>
    setParams(prev => [...prev, { key: '', value: '', _id: Math.random().toString(36).slice(2) }]);

  const updateParam = (idx: number, key: string, value: string) => {
    setParams(prev => prev.map((p, i) => (i === idx ? { ...p, key, value } : p)));
    const next = params.map((p, i) => (i === idx ? { ...p, key, value } : p));
    update({
      parameters:
        next.filter(p => p.key !== '').length > 0
          ? Object.fromEntries(next.filter(p => p.key !== '').map(p => [p.key, p.value]))
          : undefined,
    });
  };

  const removeParam = (idx: number) => {
    const next = params.filter((_, i) => i !== idx);
    setParams(next);
    update({
      parameters:
        next.filter(p => p.key !== '').length > 0
          ? Object.fromEntries(next.filter(p => p.key !== '').map(p => [p.key, p.value]))
          : undefined,
    });
  };

  // Retries segmented control (squares 1–5)
  const currentRetries = step.retries ?? 0;
  const setRetries = (n: number) => update({ retries: n === currentRetries ? 0 : n });

  return (
    <div
      style={{
        width: 320,
        flexShrink: 0,
        background: t.bgSurface,
        borderLeft: `1px solid ${t.borderDefault}`,
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        overflow: 'hidden',
      }}
      role="complementary"
      aria-label="Step configuration"
    >
      {/* ── Header ──────────────────────────────────────────────────────────── */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '12px 14px',
          borderBottom: `1px solid ${t.borderDefault}`,
          flexShrink: 0,
        }}
      >
        <span
          style={{
            fontSize: 13,
            fontFamily: 'var(--font-display, inherit)',
            fontWeight: 600,
            color: t.textPrimary,
          }}
        >
          Configure Step
        </span>
        <button
          onClick={onClose}
          aria-label="Close step config"
          style={{
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            color: t.textMuted,
            fontSize: 18,
            lineHeight: 1,
            padding: 2,
            borderRadius: 3,
          }}
          onFocus={e => { e.currentTarget.style.outline = `2px solid ${t.cyanBorder}`; }}
          onBlur={e => { e.currentTarget.style.outline = 'none'; }}
        >
          ×
        </button>
      </div>

      {/* ── Scrollable body ─────────────────────────────────────────────────── */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '14px 14px 20px' }}>

        {/* ── BASIC ─────────────────────────────────────────────────────────── */}
        <SectionHeader label="Basic" />

        {/* Step ID (read-only badge) */}
        <FieldRow label="Step ID">
          <span
            style={{
              fontFamily: 'monospace',
              fontSize: 11,
              color: t.textMuted,
              background: t.bgDeep,
              border: `1px solid ${t.borderSubtle}`,
              borderRadius: 4,
              padding: '4px 8px',
              display: 'inline-block',
            }}
          >
            {step.id}
          </span>
        </FieldRow>

        <FieldRow label="Label">
          <input
            type="text"
            placeholder="Human-readable name"
            value={step.label ?? ''}
            onChange={e => update({ label: e.target.value || undefined })}
            style={{ ...inputBase }}
            onFocus={e => focusBorder(e.currentTarget)}
            onBlur={e => blurBorder(e.currentTarget)}
            aria-label="Step label"
          />
        </FieldRow>

        <FieldRow label="Agent">
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span
              style={{
                fontFamily: 'monospace',
                fontSize: 11,
                color: t.textMuted,
                flex: 1,
                minWidth: 0,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                background: t.bgDeep,
                border: `1px solid ${t.borderSubtle}`,
                borderRadius: 4,
                padding: '5px 8px',
                display: 'block',
              }}
            >
              {step.agent || <span style={{ color: t.textFaint }}>none</span>}
            </span>
            <button
              onClick={onOpenAgentPicker}
              aria-label="Change agent"
              style={{
                flexShrink: 0,
                fontSize: 10,
                fontFamily: 'inherit',
                color: t.cyan,
                background: t.cyanBg,
                border: `1px solid ${t.cyanBorder}`,
                borderRadius: 4,
                padding: '4px 8px',
                cursor: 'pointer',
                whiteSpace: 'nowrap',
              }}
              onFocus={e => { e.currentTarget.style.boxShadow = `0 0 0 2px ${t.cyanBorder}`; }}
              onBlur={e => { e.currentTarget.style.boxShadow = 'none'; }}
            >
              Change
            </button>
          </div>
        </FieldRow>

        <FieldRow label="Description">
          <textarea
            rows={2}
            placeholder="Optional description"
            value={step.description ?? ''}
            onChange={e => update({ description: e.target.value || undefined })}
            style={{
              ...inputBase,
              resize: 'vertical',
              minHeight: 46,
              fontFamily: 'inherit',
            }}
            onFocus={e => focusBorder(e.currentTarget)}
            onBlur={e => blurBorder(e.currentTarget)}
            aria-label="Step description"
          />
        </FieldRow>

        <Divider />

        {/* ── DEPENDENCIES ──────────────────────────────────────────────────── */}
        <SectionHeader label="Dependencies" />

        <div style={{ marginBottom: 8 }}>
          <div style={{ fontSize: 10, color: t.textSecondary, marginBottom: 6 }}>Depends on</div>

          {/* Dep chips */}
          {step.depends_on.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 6 }}>
              {step.depends_on.map(depId => (
                <span
                  key={depId}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 4,
                    fontSize: 10,
                    fontFamily: 'monospace',
                    color: t.textPrimary,
                    background: t.bgTrack,
                    border: `1px solid ${t.borderDefault}`,
                    borderRadius: 4,
                    padding: '3px 6px',
                  }}
                >
                  {depLabel(depId)}
                  <button
                    onClick={() => removeDep(depId)}
                    aria-label={`Remove dependency ${depId}`}
                    style={{
                      background: 'none',
                      border: 'none',
                      cursor: 'pointer',
                      color: t.textFaint,
                      padding: 0,
                      lineHeight: 1,
                      fontSize: 12,
                    }}
                    onFocus={e => { e.currentTarget.style.color = t.red; }}
                    onBlur={e => { e.currentTarget.style.color = t.textFaint; }}
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          )}

          {/* Add dep button + dropdown */}
          <div style={{ position: 'relative' }} ref={depDropdownRef}>
            <button
              onClick={() => setDepDropdownOpen(v => !v)}
              disabled={availableDeps.length === 0}
              style={{
                fontSize: 10,
                fontFamily: 'inherit',
                color: availableDeps.length === 0 ? t.textFaint : t.textSecondary,
                background: 'none',
                border: `1px dashed ${availableDeps.length === 0 ? t.borderFaint : t.borderDefault}`,
                borderRadius: 4,
                padding: '4px 8px',
                cursor: availableDeps.length === 0 ? 'default' : 'pointer',
              }}
              onFocus={e => { if (availableDeps.length > 0) e.currentTarget.style.borderColor = t.cyanBorder; }}
              onBlur={e => { e.currentTarget.style.borderColor = availableDeps.length === 0 ? t.borderFaint : t.borderDefault; }}
              aria-haspopup="listbox"
              aria-expanded={depDropdownOpen}
            >
              + Add dependency
            </button>

            {depDropdownOpen && availableDeps.length > 0 && (
              <div
                style={{
                  position: 'absolute',
                  top: 'calc(100% + 4px)',
                  left: 0,
                  zIndex: 30,
                  background: t.bgSurface,
                  border: `1px solid ${t.borderDefault}`,
                  borderRadius: 6,
                  minWidth: 180,
                  boxShadow: '0 8px 20px rgba(0,0,0,0.4)',
                  overflow: 'hidden',
                }}
                role="listbox"
                aria-label="Available steps"
              >
                {availableDeps.map(s => (
                  <button
                    key={s.id}
                    role="option"
                    aria-selected={false}
                    onClick={() => addDep(s.id)}
                    style={{
                      display: 'block',
                      width: '100%',
                      textAlign: 'left',
                      padding: '7px 10px',
                      fontSize: 11,
                      fontFamily: 'monospace',
                      color: t.textPrimary,
                      background: 'none',
                      border: 'none',
                      borderBottom: `1px solid ${t.borderFaint}`,
                      cursor: 'pointer',
                    }}
                    onMouseEnter={e => { e.currentTarget.style.background = t.cyanHover; }}
                    onMouseLeave={e => { e.currentTarget.style.background = 'none'; }}
                    onFocus={e => { e.currentTarget.style.background = t.cyanHover; }}
                    onBlur={e => { e.currentTarget.style.background = 'none'; }}
                  >
                    <div style={{ color: t.textPrimary }}>{s.label || s.id}</div>
                    {s.label && (
                      <div style={{ fontSize: 9, color: t.textMuted, marginTop: 1 }}>{s.id}</div>
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        <Divider />

        {/* ── EXECUTION ─────────────────────────────────────────────────────── */}
        <SectionHeader label="Execution" />

        {/* Timeout */}
        <FieldRow label="Timeout">
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <input
              type="number"
              min={0}
              placeholder="—"
              value={step.timeout ?? ''}
              onChange={e => update({ timeout: e.target.value === '' ? undefined : Number(e.target.value) })}
              style={{ ...inputBase, width: 80 }}
              onFocus={e => focusBorder(e.currentTarget)}
              onBlur={e => blurBorder(e.currentTarget)}
              aria-label="Timeout in seconds"
            />
            <span style={{ fontSize: 10, color: t.textFaint, fontFamily: 'inherit' }}>seconds</span>
          </div>
        </FieldRow>

        {/* Retries segmented control */}
        <FieldRow label="Retries">
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            {[1, 2, 3, 4, 5].map(n => {
              const filled = currentRetries >= n;
              return (
                <button
                  key={n}
                  onClick={() => setRetries(n)}
                  aria-label={`Set retries to ${n}`}
                  aria-pressed={filled}
                  style={{
                    width: 28,
                    height: 28,
                    borderRadius: 4,
                    background: filled ? t.cyanBg : t.bgTrack,
                    border: `1px solid ${filled ? t.cyanBorder : t.borderDefault}`,
                    color: filled ? t.cyan : t.textFaint,
                    fontSize: 11,
                    fontFamily: 'monospace',
                    cursor: 'pointer',
                    fontWeight: filled ? 600 : 400,
                    transition: 'background 0.1s, border-color 0.1s, color 0.1s',
                  }}
                  onFocus={e => { e.currentTarget.style.boxShadow = `0 0 0 2px ${t.cyanBorder}`; }}
                  onBlur={e => { e.currentTarget.style.boxShadow = 'none'; }}
                >
                  {n}
                </button>
              );
            })}
            <span style={{ fontSize: 10, color: t.textFaint, marginLeft: 4, fontFamily: 'inherit' }}>
              {currentRetries === 0 ? 'no retries' : `${currentRetries} retr${currentRetries === 1 ? 'y' : 'ies'}`}
            </span>
          </div>
        </FieldRow>

        {/* Retry delay */}
        <FieldRow label="Retry delay">
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <input
              type="number"
              min={0}
              placeholder="—"
              value={step.retry_delay ?? ''}
              onChange={e => update({ retry_delay: e.target.value === '' ? undefined : Number(e.target.value) })}
              style={{ ...inputBase, width: 80 }}
              onFocus={e => focusBorder(e.currentTarget)}
              onBlur={e => blurBorder(e.currentTarget)}
              aria-label="Retry delay in seconds"
            />
            <span style={{ fontSize: 10, color: t.textFaint, fontFamily: 'inherit' }}>seconds</span>
          </div>
        </FieldRow>

        <Divider />

        {/* ── CONTROL FLOW ──────────────────────────────────────────────────── */}
        <SectionHeader label="Control Flow" />

        {/* Human Gate toggle */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
          <label
            htmlFor="human-gate-toggle"
            style={{ fontSize: 11, color: t.textSecondary, cursor: 'pointer', fontFamily: 'inherit' }}
          >
            Human Gate
          </label>
          <Toggle
            id="human-gate-toggle"
            checked={!!step.human_gate}
            onChange={val =>
              update({
                human_gate: val || undefined,
                gate: val ? 'human_approval' : undefined,
              })
            }
          />
        </div>

        <FieldRow label="Skip if">
          <input
            type="text"
            placeholder="e.g. prev.confidence > 0.9"
            value={step.skip_if ?? ''}
            onChange={e => update({ skip_if: e.target.value || undefined })}
            style={{ ...inputBase, fontFamily: 'monospace' }}
            onFocus={e => focusBorder(e.currentTarget)}
            onBlur={e => blurBorder(e.currentTarget)}
            aria-label="Skip if expression"
          />
        </FieldRow>

        <Divider />

        {/* ── AGENT PARAMETERS ──────────────────────────────────────────────── */}
        <SectionHeader label="Agent Parameters" />

        {params.map((p, idx) => (
          <div key={p._id} style={{ display: 'flex', gap: 4, alignItems: 'center', marginBottom: 6 }}>
            <input
              type="text"
              placeholder="key"
              value={p.key}
              onChange={e => updateParam(idx, e.target.value, p.value)}
              style={{ ...inputBase, fontFamily: 'monospace', width: '42%' }}
              onFocus={e => focusBorder(e.currentTarget)}
              onBlur={e => blurBorder(e.currentTarget)}
              aria-label={`Parameter ${idx + 1} key`}
            />
            <input
              type="text"
              placeholder="value"
              value={p.value}
              onChange={e => updateParam(idx, p.key, e.target.value)}
              style={{ ...inputBase, fontFamily: 'monospace', flex: 1 }}
              onFocus={e => focusBorder(e.currentTarget)}
              onBlur={e => blurBorder(e.currentTarget)}
              aria-label={`Parameter ${idx + 1} value`}
            />
            <button
              onClick={() => removeParam(idx)}
              aria-label={`Remove parameter ${p.key || idx + 1}`}
              style={{
                flexShrink: 0,
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                color: t.textFaint,
                fontSize: 15,
                lineHeight: 1,
                padding: '2px 4px',
              }}
              onFocus={e => { e.currentTarget.style.color = t.red; }}
              onBlur={e => { e.currentTarget.style.color = t.textFaint; }}
            >
              ×
            </button>
          </div>
        ))}

        <button
          onClick={addParam}
          aria-label="Add parameter"
          style={{
            fontSize: 10,
            fontFamily: 'inherit',
            color: t.textSecondary,
            background: 'none',
            border: `1px dashed ${t.borderDefault}`,
            borderRadius: 4,
            padding: '4px 8px',
            cursor: 'pointer',
            marginBottom: 4,
          }}
          onFocus={e => { e.currentTarget.style.borderColor = t.cyanBorder; }}
          onBlur={e => { e.currentTarget.style.borderColor = t.borderDefault; }}
        >
          + Add parameter
        </button>

        <Divider />

        {/* ── DANGER ZONE ───────────────────────────────────────────────────── */}
        <SectionHeader label="Danger Zone" />

        {!confirmDelete ? (
          <button
            onClick={() => setConfirmDelete(true)}
            style={{
              fontSize: 11,
              fontFamily: 'inherit',
              color: t.red,
              background: t.redBg,
              border: `1px solid ${t.redBorder}`,
              borderRadius: 5,
              padding: '6px 12px',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 5,
            }}
            onFocus={e => { e.currentTarget.style.boxShadow = `0 0 0 2px ${t.redBorder}`; }}
            onBlur={e => { e.currentTarget.style.boxShadow = 'none'; }}
          >
            <span role="img" aria-label="delete">🗑</span> Delete Step
          </button>
        ) : (
          <div
            style={{
              background: t.redBg,
              border: `1px solid ${t.redBorder}`,
              borderRadius: 6,
              padding: '10px 12px',
            }}
          >
            <div style={{ fontSize: 11, color: t.red, marginBottom: 10, fontFamily: 'inherit' }}>
              Are you sure? This cannot be undone.
            </div>
            <div style={{ display: 'flex', gap: 6 }}>
              <button
                onClick={() => setConfirmDelete(false)}
                style={{
                  flex: 1,
                  fontSize: 11,
                  fontFamily: 'inherit',
                  color: t.textSecondary,
                  background: t.bgDeep,
                  border: `1px solid ${t.borderDefault}`,
                  borderRadius: 4,
                  padding: '5px 0',
                  cursor: 'pointer',
                }}
                onFocus={e => { e.currentTarget.style.borderColor = t.cyanBorder; }}
                onBlur={e => { e.currentTarget.style.borderColor = t.borderDefault; }}
              >
                Cancel
              </button>
              <button
                onClick={() => { onDelete(step.id); setConfirmDelete(false); }}
                style={{
                  flex: 1,
                  fontSize: 11,
                  fontFamily: 'inherit',
                  color: t.textPrimary,
                  background: t.red,
                  border: `1px solid ${t.redBorder}`,
                  borderRadius: 4,
                  padding: '5px 0',
                  cursor: 'pointer',
                  fontWeight: 600,
                }}
                onFocus={e => { e.currentTarget.style.boxShadow = `0 0 0 2px ${t.redBorder}`; }}
                onBlur={e => { e.currentTarget.style.boxShadow = 'none'; }}
              >
                Delete
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default StepConfigSidebar;
