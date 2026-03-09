/**
 * OperationFormModal — Modal for manually triggering database operations.
 * Dynamic form fields based on selected action type.
 */
import React, { useState } from 'react';

interface OperationFormModalProps {
  onClose: () => void;
  onCreate: (action: string, params: Record<string, unknown>) => void;
}

type ActionType = 'kill_query' | 'vacuum' | 'reindex' | 'create_index' | 'drop_index' | 'alter_config';

const ACTION_OPTIONS: { value: ActionType; label: string }[] = [
  { value: 'kill_query', label: 'Kill Query' },
  { value: 'vacuum', label: 'Vacuum' },
  { value: 'reindex', label: 'Reindex' },
  { value: 'create_index', label: 'Create Index' },
  { value: 'drop_index', label: 'Drop Index' },
  { value: 'alter_config', label: 'Alter Config' },
];

const CONFIG_ALLOWLIST = [
  'shared_buffers',
  'work_mem',
  'maintenance_work_mem',
  'effective_cache_size',
  'max_connections',
  'max_worker_processes',
  'max_parallel_workers_per_gather',
  'random_page_cost',
  'effective_io_concurrency',
  'checkpoint_completion_target',
  'wal_buffers',
  'min_wal_size',
  'max_wal_size',
  'log_min_duration_statement',
  'statement_timeout',
  'idle_in_transaction_session_timeout',
];

const inputClass =
  'w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-600 text-sm text-slate-100 placeholder-slate-500 focus:border-cyan-500 outline-none';
const labelClass = 'block text-xs font-medium text-slate-400 mb-1';

const OperationFormModal: React.FC<OperationFormModalProps> = ({ onClose, onCreate }) => {
  const [action, setAction] = useState<ActionType>('kill_query');

  // kill_query
  const [pid, setPid] = useState('');

  // vacuum
  const [vacuumTable, setVacuumTable] = useState('');
  const [vacuumFull, setVacuumFull] = useState(false);
  const [vacuumAnalyze, setVacuumAnalyze] = useState(true);

  // reindex
  const [reindexTable, setReindexTable] = useState('');

  // create_index
  const [ciTable, setCiTable] = useState('');
  const [ciColumns, setCiColumns] = useState('');
  const [ciUnique, setCiUnique] = useState(false);
  const [ciName, setCiName] = useState('');

  // drop_index
  const [diName, setDiName] = useState('');

  // alter_config
  const [configParam, setConfigParam] = useState(CONFIG_ALLOWLIST[0]);
  const [configValue, setConfigValue] = useState('');

  const handleSubmit = () => {
    let params: Record<string, unknown> = {};
    switch (action) {
      case 'kill_query':
        if (!pid) { alert('PID is required'); return; }
        params = { pid: Number(pid) };
        break;
      case 'vacuum':
        if (!vacuumTable) { alert('Table name is required'); return; }
        params = { table: vacuumTable, full: vacuumFull, analyze: vacuumAnalyze };
        break;
      case 'reindex':
        if (!reindexTable) { alert('Table name is required'); return; }
        params = { table: reindexTable };
        break;
      case 'create_index':
        if (!ciTable || !ciColumns) { alert('Table and columns are required'); return; }
        params = {
          table: ciTable,
          columns: ciColumns.split(',').map((c) => c.trim()).filter(Boolean),
          unique: ciUnique,
          index_name: ciName || undefined,
        };
        break;
      case 'drop_index':
        if (!diName) { alert('Index name is required'); return; }
        params = { index_name: diName };
        break;
      case 'alter_config':
        if (!configValue) { alert('Value is required'); return; }
        params = { param: configParam, value: configValue };
        break;
    }
    onCreate(action, params);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-[#0d2329] border border-slate-700/50 rounded-xl shadow-2xl w-full max-w-lg mx-4">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-700/50">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-cyan-400">build</span>
            <h3 className="text-sm font-semibold text-slate-200">New Operation</h3>
          </div>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-300 transition-colors">
            <span className="material-symbols-outlined text-[20px]">close</span>
          </button>
        </div>

        {/* Body */}
        <div className="px-5 py-4 space-y-4 max-h-[60vh] overflow-y-auto">
          {/* Action selector */}
          <div>
            <label className={labelClass}>Action Type</label>
            <select
              value={action}
              onChange={(e) => setAction(e.target.value as ActionType)}
              className={inputClass}
            >
              {ACTION_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>

          {/* Dynamic fields */}
          {action === 'kill_query' && (
            <div>
              <label className={labelClass}>Process ID (PID)</label>
              <input
                type="number"
                value={pid}
                onChange={(e) => setPid(e.target.value)}
                placeholder="e.g. 12345"
                className={inputClass}
              />
            </div>
          )}

          {action === 'vacuum' && (
            <>
              <div>
                <label className={labelClass}>Table Name</label>
                <input
                  type="text"
                  value={vacuumTable}
                  onChange={(e) => setVacuumTable(e.target.value)}
                  placeholder="e.g. public.orders"
                  className={inputClass}
                />
              </div>
              <div className="flex items-center gap-4">
                <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={vacuumFull}
                    onChange={(e) => setVacuumFull(e.target.checked)}
                    className="rounded border-slate-600 bg-slate-800 text-cyan-500 focus:ring-cyan-500"
                  />
                  FULL
                </label>
                <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={vacuumAnalyze}
                    onChange={(e) => setVacuumAnalyze(e.target.checked)}
                    className="rounded border-slate-600 bg-slate-800 text-cyan-500 focus:ring-cyan-500"
                  />
                  ANALYZE
                </label>
              </div>
            </>
          )}

          {action === 'reindex' && (
            <div>
              <label className={labelClass}>Table Name</label>
              <input
                type="text"
                value={reindexTable}
                onChange={(e) => setReindexTable(e.target.value)}
                placeholder="e.g. public.orders"
                className={inputClass}
              />
            </div>
          )}

          {action === 'create_index' && (
            <>
              <div>
                <label className={labelClass}>Table Name</label>
                <input
                  type="text"
                  value={ciTable}
                  onChange={(e) => setCiTable(e.target.value)}
                  placeholder="e.g. public.orders"
                  className={inputClass}
                />
              </div>
              <div>
                <label className={labelClass}>Columns (comma-separated)</label>
                <input
                  type="text"
                  value={ciColumns}
                  onChange={(e) => setCiColumns(e.target.value)}
                  placeholder="e.g. user_id, created_at"
                  className={inputClass}
                />
              </div>
              <div>
                <label className={labelClass}>Index Name (optional)</label>
                <input
                  type="text"
                  value={ciName}
                  onChange={(e) => setCiName(e.target.value)}
                  placeholder="e.g. idx_orders_user_created"
                  className={inputClass}
                />
              </div>
              <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={ciUnique}
                  onChange={(e) => setCiUnique(e.target.checked)}
                  className="rounded border-slate-600 bg-slate-800 text-cyan-500 focus:ring-cyan-500"
                />
                Unique index
              </label>
            </>
          )}

          {action === 'drop_index' && (
            <div>
              <label className={labelClass}>Index Name</label>
              <input
                type="text"
                value={diName}
                onChange={(e) => setDiName(e.target.value)}
                placeholder="e.g. idx_orders_user_created"
                className={inputClass}
              />
            </div>
          )}

          {action === 'alter_config' && (
            <>
              <div>
                <label className={labelClass}>Parameter</label>
                <select
                  value={configParam}
                  onChange={(e) => setConfigParam(e.target.value)}
                  className={inputClass}
                >
                  {CONFIG_ALLOWLIST.map((p) => (
                    <option key={p} value={p}>{p}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className={labelClass}>Value</label>
                <input
                  type="text"
                  value={configValue}
                  onChange={(e) => setConfigValue(e.target.value)}
                  placeholder="e.g. 256MB"
                  className={inputClass}
                />
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 px-5 py-4 border-t border-slate-700/50">
          <button
            onClick={onClose}
            className="px-4 py-2 text-xs rounded-lg bg-slate-700/50 hover:bg-slate-600/60 text-slate-300 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            className="px-4 py-2 text-xs rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white transition-colors"
          >
            <span className="flex items-center gap-1">
              <span className="material-symbols-outlined text-[14px]">add</span>
              Create Plan
            </span>
          </button>
        </div>
      </div>
    </div>
  );
};

export default OperationFormModal;
