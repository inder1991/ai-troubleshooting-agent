import React from 'react';
import { t } from '../../../styles/tokens';
import type { ClusterProfile } from '../../../types/profiles';

interface Props {
  profiles: ClusterProfile[];
  selectedId: string | null;    // null means "use a different cluster"
  onSelect: (profileId: string | null) => void;
  loading?: boolean;
}

const STATUS_COLOR: Record<string, string> = {
  connected:     t.green,
  warning:       t.amber,
  unreachable:   t.red,
  pending_setup: t.textMuted,
};

const STATUS_LABEL: Record<string, string> = {
  connected:     '✓ connected',
  warning:       '⚠ warning',
  unreachable:   '✗ unreachable',
  pending_setup: '─ pending',
};

const ENV_STYLE: Record<string, { background: string; color: string }> = {
  prod:    { background: t.redBg,   color: t.red },
  staging: { background: t.amberBg, color: t.amber },
  dev:     { background: t.bgTrack, color: t.textMuted },
};

// Suppress unused variable warning — kept for potential future use in rich option rendering
void STATUS_COLOR;
void ENV_STYLE;

export function ClusterProfileSelector({ profiles, selectedId, onSelect, loading }: Props) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <label style={{
        fontSize: 11, fontWeight: 600, color: t.textSecondary,
        textTransform: 'uppercase', letterSpacing: '0.05em',
      }}>
        Cluster
      </label>
      <select
        value={selectedId ?? '__temp__'}
        onChange={e => onSelect(e.target.value === '__temp__' ? null : e.target.value)}
        disabled={loading}
        style={{
          background: t.bgDeep,
          border: `1px solid ${t.borderDefault}`,
          borderRadius: 6,
          color: t.textPrimary,
          padding: '8px 10px',
          fontSize: 13,
          width: '100%',
          cursor: loading ? 'not-allowed' : 'pointer',
        }}
      >
        {profiles.map(p => {
          const statusLabel = STATUS_LABEL[p.status] ?? '─ pending';
          const envLabel = p.environment ? `[${p.environment}]` : '';
          const roleLabel = (p as any).role ? ` · ${(p as any).role}` : '';
          const versionLabel = p.cluster_version ? ` · ${p.cluster_version}` : '';
          return (
            <option key={p.id} value={p.id}>
              {p.name} {envLabel}{roleLabel}{versionLabel} · {statusLabel}
            </option>
          );
        })}
        <option value="__temp__">── Use a different cluster (one-time) ──</option>
      </select>
    </div>
  );
}
