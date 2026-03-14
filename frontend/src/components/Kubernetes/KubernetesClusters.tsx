import React, { useState, useEffect, useCallback } from 'react';
import type { ClusterProfile } from '../../types/profiles';
import { useToast } from '../Toast/ToastContext';
import {
  listProfiles,
  createProfile,
  updateProfile,
  deleteProfile,
  activateProfile,
  testEndpoint,
  probeProfile,
} from '../../services/profileApi';
import ClusterProfilesTable from '../Settings/ClusterProfilesTable';
import ClusterConnectionForm from '../Settings/ClusterConnectionForm';

const KubernetesClusters: React.FC = () => {
  const { addToast } = useToast();
  const [profiles, setProfiles] = useState<ClusterProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingProfile, setEditingProfile] = useState<ClusterProfile | null>(null);
  const [testingEndpoint, setTestingEndpoint] = useState<string | null>(null);
  const [probingId, setProbingId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

  const loadProfiles = useCallback(async () => {
    try {
      setLoading(true);
      const data = await listProfiles();
      setProfiles(data);
    } catch {
      addToast('error', 'Failed to load cluster profiles');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadProfiles();
  }, [loadProfiles]);

  const handleSaveProfile = async (data: Record<string, unknown>) => {
    try {
      if (editingProfile) {
        await updateProfile(editingProfile.id, data);
        addToast('success', 'Cluster updated');
      } else {
        await createProfile(data);
        addToast('success', 'Cluster added');
      }
      setShowForm(false);
      setEditingProfile(null);
      await loadProfiles();
    } catch (err) {
      addToast('error', err instanceof Error ? err.message : 'Failed to save cluster');
    }
  };

  const handleDeleteProfile = async (id: string) => {
    try {
      await deleteProfile(id);
      addToast('success', 'Cluster deleted');
      await loadProfiles();
    } catch (err) {
      addToast('error', err instanceof Error ? err.message : 'Failed to delete cluster');
    }
  };

  const handleActivateProfile = async (id: string) => {
    await activateProfile(id);
    await loadProfiles();
  };

  const handleTestEndpoint = async (profileId: string, endpointName: string, url: string) => {
    setTestingEndpoint(endpointName);
    try {
      const result = await testEndpoint(profileId, endpointName, url);
      addToast(
        result.reachable ? 'success' : 'warning',
        result.reachable ? `${endpointName}: reachable (${result.latency_ms}ms)` : `${endpointName}: ${result.error}`
      );
    } catch (err) {
      addToast('error', err instanceof Error ? err.message : 'Test failed');
    } finally {
      setTestingEndpoint(null);
    }
  };

  const handleProbeProfile = async (id: string) => {
    setProbingId(id);
    try {
      const result = await probeProfile(id);
      const probeData = result as { reachable?: boolean; errors?: string[] };
      if (probeData.reachable) {
        addToast('success', 'Cluster connected successfully');
      } else {
        addToast('error', probeData.errors?.[0] || 'Connection failed');
      }
      await loadProfiles();
    } catch (err) {
      addToast('error', err instanceof Error ? err.message : 'Probe failed');
    } finally {
      setProbingId(null);
    }
  };

  const filteredProfiles = profiles.filter(
    (p) =>
      !searchQuery ||
      p.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      p.cluster_url.toLowerCase().includes(searchQuery.toLowerCase()) ||
      p.environment.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Header */}
      <header className="h-14 border-b border-[#3d3528] flex items-center justify-between px-8 bg-[#1a1814]/50 backdrop-blur-md flex-shrink-0">
        <div className="flex items-center gap-3">
          <span className="material-symbols-outlined text-amber-400 text-xl">dns</span>
          <h2 className="text-lg font-bold text-white">Kubernetes Clusters</h2>
          <span className="text-xs text-slate-500 ml-2">{profiles.length} cluster{profiles.length !== 1 ? 's' : ''}</span>
        </div>
        <div className="flex items-center gap-3">
          <div className="relative">
            <span
              className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-[18px]"
              style={{ color: '#8fc3cc' }}
            >
              search
            </span>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="bg-[#183034] border-none rounded-lg pl-9 pr-4 py-1.5 text-sm w-56 focus:ring-1 focus:ring-[#e09f3e] placeholder-[#8fc3cc]/50 text-white"
              placeholder="Search clusters..."
            />
          </div>
        </div>
      </header>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-8">
        <div className="max-w-6xl mx-auto space-y-6">
          {loading ? (
            <div className="space-y-4">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-16 bg-[#252118] rounded-lg animate-pulse" />
              ))}
            </div>
          ) : (
            <>
              <ClusterProfilesTable
                profiles={filteredProfiles}
                onEdit={(p) => { setEditingProfile(p); setShowForm(true); }}
                onDelete={handleDeleteProfile}
                onActivate={handleActivateProfile}
                onAddNew={() => { setEditingProfile(null); setShowForm(true); }}
                onProbe={handleProbeProfile}
                probingId={probingId}
              />

              {showForm && (
                <ClusterConnectionForm
                  profile={editingProfile}
                  onSave={handleSaveProfile}
                  onCancel={() => { setShowForm(false); setEditingProfile(null); }}
                  onTestEndpoint={handleTestEndpoint}
                  onProbe={handleProbeProfile}
                  testingEndpoint={testingEndpoint}
                  probingId={probingId}
                />
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default KubernetesClusters;
