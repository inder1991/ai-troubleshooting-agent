import React, { useState, useEffect, useCallback } from 'react';
import type { ClusterProfile, GlobalIntegration } from '../../types/profiles';
import {
  listProfiles,
  createProfile,
  updateProfile,
  deleteProfile,
  activateProfile,
  testEndpoint,
  listGlobalIntegrations,
  updateGlobalIntegration,
  testGlobalIntegration,
  saveAllGlobalIntegrations,
} from '../../services/profileApi';
import ClusterProfilesTable from './ClusterProfilesTable';
import ClusterConnectionForm from './ClusterConnectionForm';
import GlobalIntegrationsSection from './GlobalIntegrationsSection';

interface IntegrationHubProps {
  onBack: () => void;
}

const IntegrationHub: React.FC<IntegrationHubProps> = ({ onBack }) => {
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
      console.error('Failed to load integration data:', err);
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
    if (editingProfile) {
      await updateProfile(editingProfile.id, data);
    } else {
      await createProfile(data);
    }
    setShowForm(false);
    setEditingProfile(null);
    await loadData();
  };

  const handleDeleteProfile = async (id: string) => {
    await deleteProfile(id);
    await loadData();
  };

  const handleActivateProfile = async (id: string) => {
    await activateProfile(id);
    await loadData();
  };

  const handleTestEndpoint = async (profileId: string, endpointName: string) => {
    setTestingEndpoint(endpointName);
    try {
      await testEndpoint(profileId, endpointName);
      await loadData();
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
      await testGlobalIntegration(id);
      await loadData();
    } finally {
      setTestingGlobalId(null);
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
      await loadData();
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
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="h-12 bg-[#1e2f33]/50 border-b border-[#224349] flex items-center justify-between px-4">
        <div className="flex items-center">
          <button
            onClick={onBack}
            className="text-gray-400 hover:text-white text-xs mr-3 transition-colors flex items-center gap-1"
          >
            <span
              className="material-symbols-outlined text-xs"
              style={{ fontFamily: 'Material Symbols Outlined' }}
            >
              arrow_back
            </span>
            Home
          </button>
          <span
            className="material-symbols-outlined text-base mr-2"
            style={{ fontFamily: 'Material Symbols Outlined', color: '#07b6d5' }}
          >
            hub
          </span>
          <h1 className="text-sm font-semibold text-white">
            Integrations & Cluster Management
          </h1>
        </div>
        <div className="relative">
          <span
            className="material-symbols-outlined text-gray-500 absolute left-3 top-1/2 -translate-y-1/2 text-sm"
            style={{ fontFamily: 'Material Symbols Outlined' }}
          >
            search
          </span>
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className={`${inputClass} pl-9 w-64`}
            placeholder="Search clusters..."
          />
        </div>
      </div>

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto pb-24">
        <div className="max-w-5xl mx-auto p-6 space-y-8">
          {loading ? (
            <div className="text-center text-gray-500 text-sm py-12">
              Loading integrations...
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
                  testingEndpoint={testingEndpoint}
                />
              )}

              {/* Section 3: Global Ecosystem Integrations */}
              <GlobalIntegrationsSection
                integrations={globalIntegrations}
                onUpdate={handleGlobalUpdate}
                onTest={handleTestGlobal}
                testingId={testingGlobalId}
              />
            </>
          )}
        </div>
      </div>

      {/* Sticky Footer */}
      <div className="fixed bottom-0 left-0 right-0 bg-[#0a1a1d]/95 backdrop-blur-md border-t border-[#224349] px-6 py-3 flex items-center justify-end gap-3 z-30">
        <button
          onClick={handleDiscard}
          disabled={!hasUnsavedChanges}
          className="px-4 py-2 text-gray-400 hover:text-white text-sm transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
        >
          Discard Changes
        </button>
        <button
          onClick={handleSaveAll}
          disabled={saving}
          className="px-6 py-2 bg-[#07b6d5] hover:bg-[#07b6d5]/90 text-[#0f2023] rounded-lg text-sm font-bold transition-colors shadow-[0_0_20px_rgba(7,182,213,0.3)] disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {saving ? 'Saving...' : 'SAVE CONFIGURATION'}
        </button>
      </div>
    </div>
  );
};

export default IntegrationHub;
