/**
 * DBSchema — Schema browser with tree navigation and table detail drill-down.
 */
import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  fetchDBProfiles,
  fetchDBSchema,
  fetchDBTableDetail,
} from '../../services/api';

interface Column {
  name: string;
  data_type: string;
  nullable: boolean;
  default: string | null;
  is_pk: boolean;
}

interface Index {
  name: string;
  columns: string[];
  unique: boolean;
  size_bytes: number;
}

interface TableDetail {
  name: string;
  schema_name: string;
  columns: Column[];
  indexes: Index[];
  row_estimate: number;
  total_size_bytes: number;
  bloat_ratio: number;
}

interface SchemaTable {
  name: string;
  row_estimate?: number;
  total_size_bytes?: number;
}

interface SchemaSnapshot {
  tables: SchemaTable[];
  views?: string[];
  functions?: string[];
  total_size_bytes: number;
}

interface Profile {
  id: string;
  name: string;
  engine: string;
}

const formatBytes = (bytes: number): string => {
  if (bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(i > 0 ? 1 : 0)} ${units[i]}`;
};

const DBSchema: React.FC = () => {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [selectedProfileId, setSelectedProfileId] = useState('');
  const [schema, setSchema] = useState<SchemaSnapshot | null>(null);
  const [selectedTable, setSelectedTable] = useState<string | null>(null);
  const [tableDetail, setTableDetail] = useState<TableDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [filter, setFilter] = useState('');
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set(['Tables']));

  // Load profiles
  useEffect(() => {
    fetchDBProfiles().then((list: Profile[]) => {
      setProfiles(list);
      if (list.length > 0 && !selectedProfileId) setSelectedProfileId(list[0].id);
    }).catch(() => setProfiles([]));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Load schema when profile changes
  const loadSchema = useCallback(async () => {
    if (!selectedProfileId) return;
    setLoading(true);
    setSelectedTable(null);
    setTableDetail(null);
    try {
      setSchema(await fetchDBSchema(selectedProfileId));
    } catch {
      setSchema(null);
    } finally {
      setLoading(false);
    }
  }, [selectedProfileId]);

  useEffect(() => { loadSchema(); }, [loadSchema]);

  // Load table detail
  const loadTableDetail = useCallback(async (tableName: string) => {
    if (!selectedProfileId) return;
    setSelectedTable(tableName);
    setDetailLoading(true);
    try {
      setTableDetail(await fetchDBTableDetail(selectedProfileId, tableName));
    } catch {
      setTableDetail(null);
    } finally {
      setDetailLoading(false);
    }
  }, [selectedProfileId]);

  // Filter tables
  const filteredTables = useMemo(() => {
    if (!schema?.tables) return [];
    if (!filter) return schema.tables;
    const lower = filter.toLowerCase();
    return schema.tables.filter((t) => t.name.toLowerCase().includes(lower));
  }, [schema, filter]);

  const toggleGroup = (group: string) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(group)) next.delete(group);
      else next.add(group);
      return next;
    });
  };

  return (
    <div className="flex h-full overflow-hidden">
      {/* Left panel — tree */}
      <div className="w-[30%] min-w-[220px] border-r border-slate-700/50 flex flex-col">
        {/* Header */}
        <div className="p-3 border-b border-slate-700/50 space-y-2">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-slate-200">Schema Browser</h3>
          </div>
          <select
            value={selectedProfileId}
            onChange={(e) => setSelectedProfileId(e.target.value)}
            className="w-full px-2 py-1.5 rounded-lg bg-slate-800 border border-slate-600 text-xs text-slate-100 focus:border-amber-500 outline-none"
          >
            {profiles.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter tables..."
            className="w-full px-2 py-1.5 rounded-lg bg-slate-800 border border-slate-600 text-xs text-slate-100 focus:border-amber-500 outline-none placeholder:text-slate-500"
          />
        </div>

        {/* Tree */}
        <div className="flex-1 overflow-auto p-2">
          {loading ? (
            <div className="flex items-center justify-center py-8 text-slate-400">
              <span className="material-symbols-outlined animate-spin text-[18px]">progress_activity</span>
            </div>
          ) : !schema ? (
            <p className="text-xs text-slate-500 text-center py-8">Select a profile to browse schema</p>
          ) : (
            <>
              {/* Tables group */}
              <div>
                <button
                  onClick={() => toggleGroup('Tables')}
                  className="flex items-center gap-1.5 w-full text-left px-2 py-1.5 text-xs font-medium text-slate-400 hover:text-slate-200 transition-colors"
                >
                  <span className="material-symbols-outlined text-[14px]" style={{ transform: expandedGroups.has('Tables') ? 'rotate(90deg)' : 'rotate(0deg)', transition: 'transform 0.15s' }}>
                    chevron_right
                  </span>
                  <span className="material-symbols-outlined text-[14px] text-amber-400">table_chart</span>
                  Tables
                  <span className="ml-auto text-slate-500">{filteredTables.length}</span>
                </button>
                {expandedGroups.has('Tables') && (
                  <div className="ml-4 space-y-0.5">
                    {filteredTables.map((t) => (
                      <button
                        key={t.name}
                        onClick={() => loadTableDetail(t.name)}
                        className={`flex items-center justify-between w-full text-left px-2 py-1 rounded text-xs transition-colors ${
                          selectedTable === t.name ? 'bg-amber-500/10 text-amber-400' : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
                        }`}
                      >
                        <span className="truncate">{t.name}</span>
                        <div className="flex items-center gap-1.5 flex-shrink-0 ml-2">
                          {t.row_estimate !== undefined && (
                            <span className="text-body-xs text-slate-500">{t.row_estimate.toLocaleString()} rows</span>
                          )}
                          {t.total_size_bytes !== undefined && t.total_size_bytes > 0 && (
                            <span className="text-body-xs bg-slate-700/50 rounded px-1 py-0.5 text-slate-400">{formatBytes(t.total_size_bytes)}</span>
                          )}
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* Views group */}
              {schema.views && schema.views.length > 0 && (
                <div className="mt-2">
                  <button
                    onClick={() => toggleGroup('Views')}
                    className="flex items-center gap-1.5 w-full text-left px-2 py-1.5 text-xs font-medium text-slate-400 hover:text-slate-200 transition-colors"
                  >
                    <span className="material-symbols-outlined text-[14px]" style={{ transform: expandedGroups.has('Views') ? 'rotate(90deg)' : 'rotate(0deg)', transition: 'transform 0.15s' }}>
                      chevron_right
                    </span>
                    <span className="material-symbols-outlined text-[14px] text-amber-400">visibility</span>
                    Views
                    <span className="ml-auto text-slate-500">{schema.views.length}</span>
                  </button>
                  {expandedGroups.has('Views') && (
                    <div className="ml-4 space-y-0.5">
                      {schema.views.map((v) => (
                        <div key={v} className="px-2 py-1 text-xs text-slate-400">{v}</div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Functions group */}
              {schema.functions && schema.functions.length > 0 && (
                <div className="mt-2">
                  <button
                    onClick={() => toggleGroup('Functions')}
                    className="flex items-center gap-1.5 w-full text-left px-2 py-1.5 text-xs font-medium text-slate-400 hover:text-slate-200 transition-colors"
                  >
                    <span className="material-symbols-outlined text-[14px]" style={{ transform: expandedGroups.has('Functions') ? 'rotate(90deg)' : 'rotate(0deg)', transition: 'transform 0.15s' }}>
                      chevron_right
                    </span>
                    <span className="material-symbols-outlined text-[14px] text-emerald-400">function</span>
                    Functions
                    <span className="ml-auto text-slate-500">{schema.functions.length}</span>
                  </button>
                  {expandedGroups.has('Functions') && (
                    <div className="ml-4 space-y-0.5">
                      {schema.functions.map((f) => (
                        <div key={f} className="px-2 py-1 text-xs text-slate-400">{f}</div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Total size */}
              {schema.total_size_bytes > 0 && (
                <div className="mt-4 pt-2 border-t border-slate-700/30 px-2">
                  <span className="text-body-xs text-slate-500">Total: {formatBytes(schema.total_size_bytes)}</span>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Right panel — detail */}
      <div className="flex-1 overflow-auto">
        {detailLoading ? (
          <div className="flex items-center justify-center h-full text-slate-400">
            <span className="material-symbols-outlined animate-spin mr-2">progress_activity</span>
            Loading table detail...
          </div>
        ) : !tableDetail ? (
          <div className="flex flex-col items-center justify-center h-full text-slate-400 gap-2">
            <span className="material-symbols-outlined text-3xl">table_chart</span>
            <p className="text-sm">Select a table to view details</p>
          </div>
        ) : (
          <div className="p-5 space-y-5">
            {/* Header stats */}
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-base font-semibold text-slate-100">{tableDetail.schema_name}.{tableDetail.name}</h3>
              </div>
              <div className="flex items-center gap-4 text-xs text-slate-400">
                <span>{tableDetail.row_estimate.toLocaleString()} rows</span>
                <span>{formatBytes(tableDetail.total_size_bytes)}</span>
                {tableDetail.bloat_ratio > 0 && (
                  <span className={tableDetail.bloat_ratio > 0.2 ? 'text-amber-400' : ''}>
                    {(tableDetail.bloat_ratio * 100).toFixed(1)}% bloat
                  </span>
                )}
              </div>
            </div>

            {/* Columns */}
            <div>
              <h4 className="text-sm font-medium text-slate-400 mb-2">Columns ({tableDetail.columns.length})</h4>
              <div className="rounded-xl border border-slate-700/50 bg-[#0d2328] overflow-hidden">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-700/50 text-xs text-slate-400">
                      <th className="text-left px-4 py-2 font-medium">Name</th>
                      <th className="text-left px-4 py-2 font-medium">Type</th>
                      <th className="text-center px-4 py-2 font-medium">Nullable</th>
                      <th className="text-left px-4 py-2 font-medium">Default</th>
                      <th className="text-center px-4 py-2 font-medium">PK</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tableDetail.columns.map((c) => (
                      <tr key={c.name} className="border-b border-slate-700/30 last:border-0 hover:bg-slate-800/30">
                        <td className="px-4 py-1.5 font-mono text-xs text-slate-200">{c.name}</td>
                        <td className="px-4 py-1.5 font-mono text-xs text-amber-400/80">{c.data_type}</td>
                        <td className="px-4 py-1.5 text-center text-xs text-slate-400">{c.nullable ? 'YES' : 'NO'}</td>
                        <td className="px-4 py-1.5 font-mono text-xs text-slate-400">{c.default || '-'}</td>
                        <td className="px-4 py-1.5 text-center">
                          {c.is_pk && <span className="material-symbols-outlined text-[14px] text-amber-400">key</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Indexes */}
            {tableDetail.indexes.length > 0 && (
              <div>
                <h4 className="text-sm font-medium text-slate-400 mb-2">Indexes ({tableDetail.indexes.length})</h4>
                <div className="rounded-xl border border-slate-700/50 bg-[#0d2328] overflow-hidden">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-slate-700/50 text-xs text-slate-400">
                        <th className="text-left px-4 py-2 font-medium">Name</th>
                        <th className="text-left px-4 py-2 font-medium">Columns</th>
                        <th className="text-center px-4 py-2 font-medium">Unique</th>
                        <th className="text-right px-4 py-2 font-medium">Size</th>
                      </tr>
                    </thead>
                    <tbody>
                      {tableDetail.indexes.map((idx) => (
                        <tr key={idx.name} className="border-b border-slate-700/30 last:border-0 hover:bg-slate-800/30">
                          <td className="px-4 py-1.5 font-mono text-xs text-slate-200">{idx.name}</td>
                          <td className="px-4 py-1.5 font-mono text-xs text-slate-400">{idx.columns.join(', ')}</td>
                          <td className="px-4 py-1.5 text-center">
                            {idx.unique && <span className="text-xs bg-amber-500/20 text-amber-400 px-1.5 py-0.5 rounded">UNIQUE</span>}
                          </td>
                          <td className="px-4 py-1.5 text-right text-xs text-slate-400">{formatBytes(idx.size_bytes)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default DBSchema;
