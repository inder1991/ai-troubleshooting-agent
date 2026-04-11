/**
 * DBConnections — Profile CRUD: list, create, edit, delete connection profiles.
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  fetchDBProfiles,
  createDBProfile,
  updateDBProfile,
  deleteDBProfile,
  fetchDBProfileHealth,
} from '../../services/api';

interface DBProfile {
  id: string;
  name: string;
  engine: string;
  host: string;
  port: number;
  database: string;
  username: string;
  created_at: string;
  tags: Record<string, string>;
}

interface ProfileFormData {
  name: string;
  engine: string;
  host: string;
  port: number;
  database: string;
  username: string;
  password: string;
  connection_uri: string;
}

const defaultForm: ProfileFormData = {
  name: '', engine: 'postgresql', host: 'localhost', port: 5432,
  database: '', username: '', password: '', connection_uri: '',
};

const DBConnections: React.FC = () => {
  const [profiles, setProfiles] = useState<DBProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<ProfileFormData>(defaultForm);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [testingId, setTestingId] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, { status: string; latency_ms?: number }>>({});
  const [showAdvanced, setShowAdvanced] = useState(false);

  const loadProfiles = useCallback(async () => {
    setLoading(true);
    try {
      setProfiles(await fetchDBProfiles());
    } catch {
      setProfiles([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadProfiles(); }, [loadProfiles]);

  const handleSave = async () => {
    setError('');
    setSaving(true);
    try {
      if (editingId) {
        await updateDBProfile(editingId, { ...form });
      } else {
        await createDBProfile({ ...form });
      }
      setShowForm(false);
      setEditingId(null);
      setForm(defaultForm);
      await loadProfiles();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this connection profile?')) return;
    try {
      await deleteDBProfile(id);
      await loadProfiles();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Delete failed');
    }
  };

  const handleEdit = (p: DBProfile) => {
    setEditingId(p.id);
    setForm({
      name: p.name, engine: p.engine, host: p.host, port: p.port,
      database: p.database, username: p.username, password: '',
      connection_uri: (p as DBProfile & { connection_uri?: string }).connection_uri || '',
    });
    setShowAdvanced(p.engine !== 'mongodb' || !((p as DBProfile & { connection_uri?: string }).connection_uri));
    setShowForm(true);
  };

  const handleTestConnection = async (id: string) => {
    setTestingId(id);
    try {
      const h = await fetchDBProfileHealth(id);
      setTestResults((prev) => ({ ...prev, [id]: { status: h.status, latency_ms: h.latency_ms } }));
    } catch {
      setTestResults((prev) => ({ ...prev, [id]: { status: 'error' } }));
    } finally {
      setTestingId(null);
    }
  };

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-slate-100">Connection Profiles</h2>
        <button
          onClick={() => { setEditingId(null); setForm(defaultForm); setShowForm(true); setError(''); }}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-amber-600 hover:bg-amber-500 text-white rounded-lg transition-colors"
        >
          <span className="material-symbols-outlined text-[16px]">add</span>
          Add Connection
        </button>
      </div>

      {/* Profile list */}
      {loading ? (
        <div className="text-center text-slate-400 py-12">
          <span className="material-symbols-outlined animate-spin">progress_activity</span>
        </div>
      ) : profiles.length === 0 ? (
        <div className="text-center text-slate-400 py-12">
          <span className="material-symbols-outlined text-4xl mb-2 block">database</span>
          No connection profiles yet. Click "Add Connection" to get started.
        </div>
      ) : (
        <div className="space-y-2">
          {profiles.map((p) => (
            <div key={p.id} className="flex items-center justify-between px-4 py-3 rounded-lg border border-slate-700/50 bg-[#0d2328] hover:border-slate-600/50 transition-colors">
              <div className="flex items-center gap-3">
                <span className="material-symbols-outlined text-amber-400">storage</span>
                <div>
                  <p className="text-sm font-medium text-slate-100">{p.name}</p>
                  <p className="text-xs text-slate-500">{p.engine} • {p.host}:{p.port}/{p.database} • {p.username}</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {/* Test result badge */}
                {testResults[p.id] && (
                  <span className={`text-xs px-2 py-0.5 rounded ${
                    testResults[p.id].status === 'healthy'
                      ? 'bg-emerald-500/20 text-emerald-400'
                      : 'bg-red-500/20 text-red-400'
                  }`}>
                    {testResults[p.id].status === 'healthy'
                      ? `OK ${testResults[p.id].latency_ms}ms`
                      : 'Failed'}
                  </span>
                )}
                <button
                  onClick={() => handleTestConnection(p.id)}
                  disabled={testingId === p.id}
                  className="p-1.5 text-slate-400 hover:text-amber-400 transition-colors"
                  title="Test connection"
                >
                  <span className={`material-symbols-outlined text-[18px] ${testingId === p.id ? 'animate-spin' : ''}`}>
                    {testingId === p.id ? 'progress_activity' : 'bolt'}
                  </span>
                </button>
                <button
                  onClick={() => handleEdit(p)}
                  className="p-1.5 text-slate-400 hover:text-slate-200 transition-colors"
                  title="Edit"
                >
                  <span className="material-symbols-outlined text-[18px]">edit</span>
                </button>
                <button
                  onClick={() => handleDelete(p.id)}
                  className="p-1.5 text-slate-400 hover:text-red-400 transition-colors"
                  title="Delete"
                >
                  <span className="material-symbols-outlined text-[18px]">delete</span>
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create/Edit modal */}
      {showForm && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={() => setShowForm(false)}>
          <div className="bg-[#0d2328] border border-slate-700/50 rounded-xl w-full max-w-md p-6 space-y-4" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-base font-semibold text-slate-100">
              {editingId ? 'Edit Connection' : 'New Connection'}
            </h3>

            {error && <p className="text-xs text-red-400 bg-red-500/10 rounded px-2 py-1">{error}</p>}

            <div className="space-y-3">
              <div>
                <label className="block text-xs text-slate-400 mb-1">Name</label>
                <input
                  value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-600 text-sm text-slate-100 focus:border-amber-500 outline-none"
                  placeholder={form.engine === 'mongodb' ? 'My MongoDB' : 'My PostgreSQL'}
                />
              </div>
              <div>
                <label className="block text-xs text-slate-400 mb-1">Engine</label>
                <select
                  value={form.engine} onChange={(e) => {
                    const engine = e.target.value;
                    const port = engine === 'mongodb' ? 27017 : 5432;
                    setForm({ ...form, engine, port, connection_uri: '' });
                    setShowAdvanced(engine !== 'mongodb');
                  }}
                  className="w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-600 text-sm text-slate-100 focus:border-amber-500 outline-none"
                >
                  <option value="postgresql">PostgreSQL</option>
                  <option value="mongodb">MongoDB</option>
                  <option value="mysql" disabled>MySQL (coming soon)</option>
                </select>
              </div>

              {/* Connection URI — MongoDB primary mode */}
              {form.engine === 'mongodb' && (
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Connection URI</label>
                  <input
                    value={form.connection_uri}
                    onChange={(e) => setForm({ ...form, connection_uri: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-600 text-sm text-slate-100 focus:border-amber-500 outline-none"
                    placeholder="mongodb+srv://user:pass@cluster0.example.net/mydb"
                  />
                  <p className="text-body-xs text-slate-500 mt-1">
                    Supports mongodb:// and mongodb+srv:// URIs.
                  </p>
                </div>
              )}

              {/* Advanced toggle for MongoDB */}
              {form.engine === 'mongodb' && (
                <button
                  type="button"
                  onClick={() => setShowAdvanced(!showAdvanced)}
                  className="flex items-center gap-1 text-xs text-slate-400 hover:text-slate-200 transition-colors"
                >
                  <span className="material-symbols-outlined text-[14px]">
                    {showAdvanced ? 'expand_less' : 'expand_more'}
                  </span>
                  {showAdvanced ? 'Hide' : 'Show'} individual fields
                </button>
              )}

              {/* Individual fields — always shown for PG, togglable for MongoDB */}
              {(form.engine !== 'mongodb' || showAdvanced) && (
                <>
                  <div className="grid grid-cols-3 gap-2">
                    <div className="col-span-2">
                      <label className="block text-xs text-slate-400 mb-1">Host</label>
                      <input
                        value={form.host} onChange={(e) => setForm({ ...form, host: e.target.value })}
                        className="w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-600 text-sm text-slate-100 focus:border-amber-500 outline-none"
                        placeholder="localhost"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-slate-400 mb-1">Port</label>
                      <input
                        type="number" value={form.port}
                        onChange={(e) => setForm({ ...form, port: parseInt(e.target.value) || (form.engine === 'mongodb' ? 27017 : 5432) })}
                        className="w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-600 text-sm text-slate-100 focus:border-amber-500 outline-none"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">Database</label>
                    <input
                      value={form.database} onChange={(e) => setForm({ ...form, database: e.target.value })}
                      className="w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-600 text-sm text-slate-100 focus:border-amber-500 outline-none"
                      placeholder="mydb"
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="block text-xs text-slate-400 mb-1">Username</label>
                      <input
                        value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })}
                        className="w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-600 text-sm text-slate-100 focus:border-amber-500 outline-none"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-slate-400 mb-1">Password</label>
                      <input
                        type="password" value={form.password}
                        onChange={(e) => setForm({ ...form, password: e.target.value })}
                        className="w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-600 text-sm text-slate-100 focus:border-amber-500 outline-none"
                      />
                    </div>
                  </div>
                </>
              )}
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setShowForm(false)}
                className="px-4 py-2 text-sm text-slate-400 hover:text-slate-200 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={saving || !form.name || (form.engine === 'mongodb' ? (!form.connection_uri && (!form.host || !form.database)) : (!form.host || !form.database || !form.username))}
                className="px-4 py-2 text-sm bg-amber-600 hover:bg-amber-500 disabled:opacity-50 text-white rounded-lg transition-colors"
              >
                {saving ? 'Saving...' : editingId ? 'Update' : 'Create'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default DBConnections;
