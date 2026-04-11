import { useState, useEffect } from 'react';
import type { TopologyDesign, DesignStatus } from '../../types';
import { listTopologyDesigns, createTopologyDesign, deleteTopologyDesign } from '../../services/api';

interface DesignManagerPanelProps {
  onOpen: (designId: string) => void;
  onCreateNew: (designId: string) => void;
  onClose: () => void;
}

const STATUS_COLORS: Record<DesignStatus, string> = {
  draft: '#8a7e6b',
  reviewed: '#60a5fa',
  simulated: '#c084fc',
  approved: '#4ade80',
  parked: '#fbbf24',
  applied: '#34d399',
  verified: '#e09f3e',
};

type FilterTab = 'all' | 'draft' | 'approved' | 'applied';

export default function DesignManagerPanel({ onOpen, onCreateNew, onClose }: DesignManagerPanelProps) {
  const [designs, setDesigns] = useState<TopologyDesign[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<FilterTab>('all');
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState('');

  const fetchDesigns = async () => {
    setLoading(true);
    try {
      const status = filter === 'all' ? undefined : filter;
      const res = await listTopologyDesigns(status);
      setDesigns(res.designs || []);
    } catch {
      setDesigns([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDesigns();
  }, [filter]);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    try {
      const res = await createTopologyDesign(newName.trim());
      setCreating(false);
      setNewName('');
      onCreateNew(res.id);
    } catch (e: any) {
      alert(e.message || 'Failed to create design');
    }
  };

  const handleDelete = async (id: string, name: string) => {
    if (!confirm(`Delete design "${name}"? This cannot be undone.`)) return;
    try {
      await deleteTopologyDesign(id);
      fetchDesigns();
    } catch (e: any) {
      alert(e.message || 'Failed to delete design');
    }
  };

  const tabs: { key: FilterTab; label: string }[] = [
    { key: 'all', label: 'All' },
    { key: 'draft', label: 'Draft' },
    { key: 'approved', label: 'Approved' },
    { key: 'applied', label: 'Applied' },
  ];

  return (
    <div
      className="fixed right-0 top-0 h-full w-[420px] z-40 border-l shadow-2xl overflow-y-auto"
      style={{ background: '#0b1a1f', borderColor: 'rgba(224,159,62,0.15)' }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b" style={{ borderColor: 'rgba(224,159,62,0.1)' }}>
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-amber-400" style={{ fontSize: 20 }}>folder_open</span>
          <h2 className="text-sm font-semibold text-white">Design Manager</h2>
        </div>
        <button onClick={onClose} className="text-gray-500 hover:text-white transition-colors">
          <span className="material-symbols-outlined" style={{ fontSize: 18 }}>close</span>
        </button>
      </div>

      <div className="p-4 space-y-4">
        {/* New Design */}
        {creating ? (
          <div className="flex items-center gap-2">
            <input
              autoFocus
              placeholder="Design name"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
              className="flex-1 bg-transparent border rounded px-2 py-1.5 text-xs text-white placeholder-gray-600 outline-none"
              style={{ borderColor: 'rgba(224,159,62,0.3)' }}
            />
            <button
              onClick={handleCreate}
              className="px-3 py-1.5 rounded text-xs font-medium"
              style={{ background: 'rgba(224,159,62,0.2)', color: '#e09f3e' }}
            >
              Create
            </button>
            <button
              onClick={() => { setCreating(false); setNewName(''); }}
              className="text-gray-500 hover:text-white text-xs"
            >
              Cancel
            </button>
          </div>
        ) : (
          <button
            onClick={() => setCreating(true)}
            className="w-full flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all"
            style={{ background: 'rgba(224,159,62,0.15)', color: '#e09f3e' }}
          >
            <span className="material-symbols-outlined" style={{ fontSize: 16 }}>add</span>
            New Design
          </button>
        )}

        {/* Filter Tabs */}
        <div className="flex gap-1">
          {tabs.map((t) => (
            <button
              key={t.key}
              onClick={() => setFilter(t.key)}
              className="px-3 py-1 rounded text-xs font-medium transition-colors"
              style={{
                background: filter === t.key ? 'rgba(224,159,62,0.2)' : 'transparent',
                color: filter === t.key ? '#e09f3e' : '#64748b',
              }}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Designs List */}
        {loading ? (
          <div className="flex items-center justify-center py-8">
            <span className="material-symbols-outlined animate-spin text-gray-600" style={{ fontSize: 24 }}>progress_activity</span>
          </div>
        ) : designs.length === 0 ? (
          <p className="text-center text-xs text-gray-600 py-8">No designs found</p>
        ) : (
          <div className="space-y-2">
            {designs.map((d) => (
              <div
                key={d.id}
                className="rounded-lg border p-3 hover:border-amber-800/50 transition-colors"
                style={{ background: 'rgba(15,32,35,0.6)', borderColor: 'rgba(100,116,139,0.12)' }}
              >
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-sm text-white font-medium truncate mr-2">{d.name}</span>
                  <span
                    className="text-body-xs font-semibold px-1.5 py-0.5 rounded-full uppercase tracking-wide shrink-0"
                    style={{
                      background: `${STATUS_COLORS[d.status]}20`,
                      color: STATUS_COLORS[d.status],
                    }}
                  >
                    {d.status}
                  </span>
                </div>
                {d.description && (
                  <p className="text-xs text-gray-500 mb-2 line-clamp-1">{d.description}</p>
                )}
                <div className="flex items-center justify-between">
                  <span className="text-body-xs text-gray-600">
                    {new Date(d.updated_at).toLocaleDateString()} · v{d.version}
                  </span>
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => onOpen(d.id)}
                      className="px-2 py-0.5 rounded text-body-xs font-medium transition-colors"
                      style={{ background: 'rgba(224,159,62,0.12)', color: '#e09f3e' }}
                    >
                      Open
                    </button>
                    <button
                      onClick={() => handleDelete(d.id, d.name)}
                      className="px-2 py-0.5 rounded text-body-xs font-medium text-gray-600 hover:text-red-400 transition-colors"
                      style={{ background: 'rgba(100,116,139,0.08)' }}
                    >
                      Delete
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
