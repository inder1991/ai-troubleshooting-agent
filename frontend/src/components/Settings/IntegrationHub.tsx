import React, { useState, useEffect, useCallback } from 'react';
import type { ClusterProfile, GlobalIntegration, EndpointTestResult } from '../../types/profiles';
import { useToast } from '../Toast/ToastContext';
import {
  listProfiles,
  createProfile,
  updateProfile,
  deleteProfile,
  activateProfile,
  testEndpoint,
  probeProfile,
  listGlobalIntegrations,
  createGlobalIntegration,
  deleteGlobalIntegration,
  updateGlobalIntegration,
  testGlobalIntegration,
  saveAllGlobalIntegrations,
} from '../../services/profileApi';
import ClusterProfilesTable from './ClusterProfilesTable';
import ClusterConnectionForm from './ClusterConnectionForm';
import GlobalIntegrationsSection from './GlobalIntegrationsSection';
import SkeletonTable from '../Skeletons/SkeletonTable';
import SkeletonCard from '../Skeletons/SkeletonCard';

interface IntegrationHubProps {
  onBack: () => void;
}

const IntegrationHub: React.FC<IntegrationHubProps> = ({ onBack }) => {
  const { addToast } = useToast();
  const [profiles, setProfiles] = useState<ClusterProfile[]>([]);
  const [globalIntegrations, setGlobalIntegrations] = useState<GlobalIntegration[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');

  // Form state
  const [showForm, setShowForm] = useState(false);
  const [editingProfile, setEditingProfile] = useState<ClusterProfile | null>(null);
  const [testingEndpoint, setTestingEndpoint] = useState<string | null>(null);
  const [testingGlobalId, setTestingGlobalId] = useState<string | null>(null);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [saving, setSaving] = useState(false);
  const [showAddGlobalForm, setShowAddGlobalForm] = useState(false);
  const [endpointTestResults, setEndpointTestResults] = useState<Record<string, EndpointTestResult>>({});
  const [globalTestResults, setGlobalTestResults] = useState<Record<string, EndpointTestResult>>({});
  const [probingId, setProbingId] = useState<string | null>(null);

  // Track global integration local edits
  const [globalEdits, setGlobalEdits] = useState<Record<string, Record<string, unknown>>>({});

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const [profileData, giData] = await Promise.all([
        listProfiles(),
        listGlobalIntegrations(),
      ]);
      setProfiles(profileData);
      setGlobalIntegrations(giData);
    } catch (err) {
      addToast('error', 'Failed to load integration data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // --- Profile actions ---

  const handleAddNew = () => {
    setEditingProfile(null);
    setShowForm(true);
  };

  const handleEdit = (profile: ClusterProfile) => {
    setEditingProfile(profile);
    setShowForm(true);
  };

  const handleSaveProfile = async (data: Record<string, unknown>) => {
    try {
      if (editingProfile) {
        await updateProfile(editingProfile.id, data);
        addToast('success', 'Profile updated');
      } else {
        await createProfile(data);
        addToast('success', 'Profile created');
      }
      setShowForm(false);
      setEditingProfile(null);
      await loadData();
    } catch (err) {
      addToast('error', err instanceof Error ? err.message : 'Failed to save profile');
    }
  };

  const handleDeleteProfile = async (id: string) => {
    try {
      await deleteProfile(id);
      addToast('success', 'Profile deleted');
      await loadData();
    } catch (err) {
      addToast('error', err instanceof Error ? err.message : 'Failed to delete profile');
    }
  };

  const handleActivateProfile = async (id: string) => {
    await activateProfile(id);
    await loadData();
  };

  const handleTestEndpoint = async (profileId: string, endpointName: string) => {
    setTestingEndpoint(endpointName);
    try {
      const result = await testEndpoint(profileId, endpointName);
      setEndpointTestResults((prev) => ({ ...prev, [endpointName]: result }));
      addToast(result.reachable ? 'success' : 'warning', result.reachable ? `${endpointName}: reachable (${result.latency_ms}ms)` : `${endpointName}: ${result.error}`);
      await loadData();
    } catch (err) {
      addToast('error', err instanceof Error ? err.message : 'Test failed');
    } finally {
      setTestingEndpoint(null);
    }
  };

  // --- Global integration actions ---

  const handleGlobalUpdate = (id: string, data: Record<string, unknown>) => {
    setGlobalEdits((prev) => ({
      ...prev,
      [id]: { ...(prev[id] || {}), ...data },
    }));
    setHasUnsavedChanges(true);
  };

  const handleTestGlobal = async (id: string) => {
    // Save pending edits for this integration first
    const edits = globalEdits[id];
    if (edits && Object.keys(edits).length > 0) {
      await updateGlobalIntegration(id, edits);
    }
    setTestingGlobalId(id);
    try {
      const result = await testGlobalIntegration(id);
      setGlobalTestResults((prev) => ({ ...prev, [id]: result }));
      addToast(result.reachable ? 'success' : 'warning', result.reachable ? `Connected (${result.latency_ms}ms)` : `Connection failed: ${result.error}`);
      await loadData();
    } catch (err) {
      addToast('error', err instanceof Error ? err.message : 'Test failed');
    } finally {
      setTestingGlobalId(null);
    }
  };

  const handleProbeProfile = async (id: string) => {
    setProbingId(id);
    try {
      await probeProfile(id);
      addToast('success', 'Probe complete');
      await loadData();
    } catch (err) {
      addToast('error', err instanceof Error ? err.message : 'Probe failed');
    } finally {
      setProbingId(null);
    }
  };

  const handleAddGlobalIntegration = async (data: Record<string, unknown>) => {
    try {
      await createGlobalIntegration(data);
      addToast('success', 'Integration added');
      setShowAddGlobalForm(false);
      await loadData();
    } catch (err) {
      addToast('error', err instanceof Error ? err.message : 'Failed to add integration');
    }
  };

  const handleDeleteGlobalIntegration = async (id: string) => {
    try {
      await deleteGlobalIntegration(id);
      addToast('success', 'Integration deleted');
      await loadData();
    } catch (err) {
      addToast('error', err instanceof Error ? err.message : 'Failed to delete integration');
    }
  };

  const handleSaveAll = async () => {
    setSaving(true);
    try {
      // Build batch update from globalEdits
      const updates = Object.entries(globalEdits).map(([id, data]) => ({
        id,
        ...data,
      }));
      if (updates.length > 0) {
        await saveAllGlobalIntegrations(updates);
      }
      setGlobalEdits({});
      setHasUnsavedChanges(false);
      addToast('success', 'Configuration saved');
      await loadData();
    } catch (err) {
      addToast('error', err instanceof Error ? err.message : 'Failed to save configuration');
    } finally {
      setSaving(false);
    }
  };

  const handleDiscard = () => {
    setGlobalEdits({});
    setHasUnsavedChanges(false);
    loadData();
  };

  // --- Search filter ---
  const filteredProfiles = profiles.filter(
    (p) =>
      !searchQuery ||
      p.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      p.cluster_url.toLowerCase().includes(searchQuery.toLowerCase()) ||
      p.environment.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const inputClass =
    'px-3 py-2 bg-[#0f2023] border border-[#224349] rounded-lg text-sm text-white placeholder-gray-600 focus:border-[#07b6d5] focus:outline-none focus:ring-1 focus:ring-[#07b6d5]/30 transition-colors';

  return (
    <div className="flex-1 flex flex-col overflow-hidden relative">
      {/* Header */}
      <header className="h-16 border-b border-[#224349] flex items-center justify-between px-8 bg-[#0f2023]/50 backdrop-blur-md sticky top-0 z-10">
        <div className="flex items-center gap-4">
          <h2 className="text-xl font-bold tracking-tight text-white">Integrations &amp; Cluster Management</h2>
        </div>
        <div className="flex items-center gap-4">
          <div className="relative">
            <span
              className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-[20px]"
              style={{ fontFamily: 'Material Symbols Outlined', color: '#8fc3cc' }}
            >
              search
            </span>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="bg-[#183034] border-none rounded-lg pl-10 pr-4 py-1.5 text-sm w-64 focus:ring-1 focus:ring-[#07b6d5] placeholder-[#8fc3cc]/50 text-white"
              placeholder="Search clusters..."
            />
          </div>
          <button className="text-[#8fc3cc] hover:text-white transition-colors relative">
            <span className="material-symbols-outlined" style={{ fontFamily: 'Material Symbols Outlined' }}>notifications</span>
            <span className="absolute top-0 right-0 w-2 h-2 bg-[#07b6d5] rounded-full border border-[#0f2023]" />
          </button>
          <div className="h-8 w-8 rounded-full bg-[#183034] border border-[#224349] flex items-center justify-center">
            <span className="material-symbols-outlined text-[#8fc3cc] text-sm" style={{ fontFamily: 'Material Symbols Outlined' }}>person</span>
          </div>
        </div>
      </header>

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto pb-24">
        <div className="max-w-6xl mx-auto p-8 space-y-8">
          {loading ? (
            <div className="space-y-8">
              <div>
                <div className="flex items-center justify-between mb-3">
                  <div className="h-4 bg-[#1e2f33] rounded animate-pulse w-48" />
                  <div className="h-7 bg-[#1e2f33] rounded-lg animate-pulse w-32" />
                </div>
                <SkeletonTable />
              </div>
              <div>
                <div className="h-4 bg-[#1e2f33] rounded animate-pulse w-56 mb-3" />
                <SkeletonCard />
              </div>
            </div>
          ) : (
            <>
              {/* Section 1: Cluster Profiles Table */}
              <ClusterProfilesTable
                profiles={filteredProfiles}
                onEdit={handleEdit}
                onDelete={handleDeleteProfile}
                onActivate={handleActivateProfile}
                onAddNew={handleAddNew}
                onProbe={handleProbeProfile}
                probingId={probingId}
              />

              {/* Section 2: Add/Edit Cluster Connection Form */}
              {showForm && (
                <ClusterConnectionForm
                  profile={editingProfile}
                  onSave={handleSaveProfile}
                  onCancel={() => {
                    setShowForm(false);
                    setEditingProfile(null);
                  }}
                  onTestEndpoint={handleTestEndpoint}
                  onProbe={handleProbeProfile}
                  testingEndpoint={testingEndpoint}
                  probingId={probingId}
                />
              )}

              {/* Section 3: Global Ecosystem Integrations */}
              <GlobalIntegrationsSection
                integrations={globalIntegrations}
                onUpdate={handleGlobalUpdate}
                onTest={handleTestGlobal}
                testingId={testingGlobalId}
                onAdd={handleAddGlobalIntegration}
                onDelete={handleDeleteGlobalIntegration}
                showAddForm={showAddGlobalForm}
                onShowAddForm={setShowAddGlobalForm}
                testResults={globalTestResults}
              />
            </>
          )}
        </div>
      </div>

      {/* Sticky Footer */}
      <footer className="absolute bottom-0 left-0 right-0 h-20 bg-[#0f2023] border-t border-[#224349] flex items-center justify-end px-8 gap-4 z-20 backdrop-blur-lg bg-opacity-90">
        <button
          onClick={handleDiscard}
          disabled={!hasUnsavedChanges}
          className="px-6 py-2.5 rounded-lg text-sm font-bold text-[#8fc3cc] hover:text-white transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
        >
          Discard Changes
        </button>
        <button
          onClick={handleSaveAll}
          disabled={saving}
          className="bg-[#07b6d5] text-[#0f2023] px-8 py-2.5 rounded-lg text-sm font-black shadow-[0_0_20px_rgba(7,182,213,0.3)] hover:scale-[1.02] active:scale-95 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {saving ? 'Saving...' : 'SAVE CONFIGURATION'}
        </button>
      </footer>
    </div>
  );
};

export default IntegrationHub;
