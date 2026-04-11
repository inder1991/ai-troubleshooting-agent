import React, { useState, useEffect } from 'react';
import type { DatabaseDiagnosticsForm } from '../../../types';
import { fetchDBProfiles } from '../../../services/api';

interface DatabaseDiagnosticsFieldsProps {
  data: DatabaseDiagnosticsForm;
  onChange: (data: DatabaseDiagnosticsForm) => void;
}

interface DBProfile {
  id: string;
  name: string;
  engine: string;
  host: string;
  port: number;
  database: string;
}

const FOCUS_OPTIONS: { value: DatabaseDiagnosticsForm['focus'][number]; label: string; icon: string; mongoLabel?: string }[] = [
  { value: 'queries', label: 'Queries', icon: 'query_stats' },
  { value: 'connections', label: 'Connections', icon: 'cable' },
  { value: 'replication', label: 'Replication', icon: 'sync' },
  { value: 'storage', label: 'Storage', icon: 'storage' },
  { value: 'schema', label: 'Schema', icon: 'account_tree', mongoLabel: 'Collections' },
];

const inputClass =
  'w-full rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-gray-600 bg-[#1a1814] border border-[#3d3528] focus:border-[#e09f3e] focus:ring-1 focus:ring-[#e09f3e]/30 outline-none transition-colors';

const DatabaseDiagnosticsFields: React.FC<DatabaseDiagnosticsFieldsProps> = ({
  data,
  onChange,
}) => {
  const [profiles, setProfiles] = useState<DBProfile[]>([]);

  useEffect(() => {
    fetchDBProfiles().then(setProfiles).catch(() => {});
  }, []);

  // Auto-detect engine from selected profile
  const selectedProfile = profiles.find((p) => p.id === data.profile_id);
  const isMongo = selectedProfile?.engine === 'mongodb' || data.database_type === 'mongodb';

  const handleProfileChange = (profileId: string) => {
    const profile = profiles.find((p) => p.id === profileId);
    const dbType = profile?.engine === 'mongodb' ? 'mongodb' : 'postgres';
    onChange({ ...data, profile_id: profileId, database_type: dbType as 'postgres' | 'mongodb' });
  };

  const toggleFocus = (area: DatabaseDiagnosticsForm['focus'][number]) => {
    const current = data.focus || [];
    const next = current.includes(area)
      ? current.filter((f) => f !== area)
      : [...current, area];
    onChange({ ...data, focus: next });
  };

  const samplingDescriptions: Record<string, string> = isMongo
    ? {
        deep: 'Deep: Runs explain("executionStats") on operations. Most thorough.',
        standard: 'Standard: Collects serverStatus + currentOp metrics. Balanced.',
        light: 'Light: Quick health check with cached snapshots. Minimal load.',
      }
    : {
        deep: 'Deep: Runs EXPLAIN ANALYZE on replica. Most thorough but adds DB load.',
        standard: 'Standard: Collects pg_stat data + EXPLAIN (no ANALYZE). Balanced.',
        light: 'Light: Quick health check with cached snapshots. Minimal DB load.',
      };

  return (
    <div className="space-y-5">
      {/* Database Profile */}
      <div>
        <label className="block text-xs font-bold text-duck-muted uppercase tracking-wider mb-2">
          Database Profile *
        </label>
        <select
          className={inputClass}
          value={data.profile_id || ''}
          onChange={(e) => handleProfileChange(e.target.value)}
          required
        >
          <option value="">Select a database profile...</option>
          {profiles.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name} ({p.engine} — {p.host}:{p.port}/{p.database})
            </option>
          ))}
        </select>
      </div>

      {/* Connection URI (MongoDB only) */}
      {isMongo && (
        <div>
          <label className="block text-xs font-bold text-duck-muted uppercase tracking-wider mb-2">
            Connection URI (optional)
          </label>
          <input
            className={inputClass}
            placeholder="mongodb+srv://user:pass@cluster0.example.net/mydb"
            value={data.connection_uri || ''}
            onChange={(e) => onChange({ ...data, connection_uri: e.target.value || undefined })}
          />
          <p className="text-body-xs text-slate-500 mt-1">
            Overrides host/port from profile. Supports mongodb:// and mongodb+srv:// URIs.
          </p>
        </div>
      )}

      {/* Time Window */}
      <div>
        <label className="block text-xs font-bold text-duck-muted uppercase tracking-wider mb-2">
          Time Window
        </label>
        <select
          className={inputClass}
          value={data.time_window}
          onChange={(e) =>
            onChange({ ...data, time_window: e.target.value as DatabaseDiagnosticsForm['time_window'] })
          }
        >
          <option value="15m">Last 15 minutes</option>
          <option value="1h">Last 1 hour</option>
          <option value="6h">Last 6 hours</option>
          <option value="24h">Last 24 hours</option>
        </select>
      </div>

      {/* Focus Areas */}
      <div>
        <label className="block text-xs font-bold text-duck-muted uppercase tracking-wider mb-2">
          Focus Areas
        </label>
        <div className="flex flex-wrap gap-2">
          {FOCUS_OPTIONS.map((opt) => {
            const active = data.focus?.includes(opt.value);
            const label = isMongo && opt.mongoLabel ? opt.mongoLabel : opt.label;
            return (
              <button
                key={opt.value}
                type="button"
                onClick={() => toggleFocus(opt.value)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-all ${
                  active
                    ? 'bg-duck-accent/20 border-duck-accent text-duck-accent'
                    : 'bg-duck-surface border-duck-border text-slate-400 hover:text-white hover:border-slate-500'
                }`}
              >
                <span className="material-symbols-outlined text-[14px]">{opt.icon}</span>
                {label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Sampling Mode */}
      <div>
        <label className="block text-xs font-bold text-duck-muted uppercase tracking-wider mb-2">
          Sampling Depth
        </label>
        <div className="flex gap-3">
          {(['light', 'standard', 'deep'] as const).map((mode) => (
            <button
              key={mode}
              type="button"
              onClick={() => onChange({ ...data, sampling_mode: mode })}
              className={`flex-1 py-2 rounded-lg text-xs font-bold uppercase tracking-wider border transition-all ${
                data.sampling_mode === mode
                  ? 'bg-duck-accent/20 border-duck-accent text-duck-accent'
                  : 'bg-duck-surface border-duck-border text-slate-400 hover:text-white'
              }`}
            >
              {mode}
            </button>
          ))}
        </div>
        <p className="text-body-xs text-slate-500 mt-1">
          {samplingDescriptions[data.sampling_mode]}
        </p>
      </div>

      {/* Include Explain Plans (PostgreSQL deep mode only) */}
      {!isMongo && data.sampling_mode === 'deep' && (
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={data.include_explain_plans}
            onChange={(e) => onChange({ ...data, include_explain_plans: e.target.checked })}
            className="rounded border-duck-border bg-duck-surface text-duck-accent focus:ring-duck-accent/30"
          />
          <span className="text-sm text-slate-300">
            Include EXPLAIN ANALYZE (runs on replica only)
          </span>
        </label>
      )}

      {/* Table/Collection Filter */}
      <div>
        <label className="block text-xs font-bold text-duck-muted uppercase tracking-wider mb-2">
          {isMongo ? 'Collection Filter (optional)' : 'Table Filter (optional)'}
        </label>
        <input
          className={inputClass}
          placeholder={isMongo ? 'orders, users, sessions (comma-separated)' : 'orders, payments, users (comma-separated)'}
          value={data.table_filter?.join(', ') || ''}
          onChange={(e) =>
            onChange({
              ...data,
              table_filter: e.target.value
                ? e.target.value.split(',').map((s) => s.trim()).filter(Boolean)
                : undefined,
            })
          }
        />
      </div>

      {/* Related App Session */}
      <div>
        <label className="block text-xs font-bold text-duck-muted uppercase tracking-wider mb-2">
          Related App Session (optional)
        </label>
        <input
          className={inputClass}
          placeholder="e.g. APP-184 (auto-fills in contextual mode)"
          value={data.parent_session_id || ''}
          onChange={(e) =>
            onChange({
              ...data,
              parent_session_id: e.target.value || undefined,
              context_source: e.target.value ? 'user_selected' : undefined,
            })
          }
        />
        <p className="text-body-xs text-slate-500 mt-1">
          Link to an app investigation to focus agents on that service's queries and connections.
        </p>
      </div>
    </div>
  );
};

export default DatabaseDiagnosticsFields;
