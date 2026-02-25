import React, { createContext, useContext, useState, useCallback, useMemo } from 'react';
import type { RemediationCampaign, TelescopeData } from '../types/campaign';

const API_BASE = 'http://localhost:8000';

interface CampaignState {
  campaign: RemediationCampaign | null;
  telescopeRepo: string | null;
  telescopeData: TelescopeData | null;
  hoveredRepo: string | null;
  loadingRepos: Set<string>;
  globalLoading: boolean;
  errorByRepo: Map<string, string>;
  /** Backward-compat computed: globalLoading || loadingRepos.size > 0 */
  isLoading: boolean;
}

interface CampaignContextValue extends CampaignState {
  setCampaign: (campaign: RemediationCampaign | null) => void;
  approveRepo: (repoUrl: string) => Promise<void>;
  rejectRepo: (repoUrl: string) => Promise<void>;
  revokeRepo: (repoUrl: string) => Promise<void>;
  executeCampaign: () => Promise<void>;
  openTelescope: (repoUrl: string) => Promise<void>;
  closeTelescope: () => void;
  setHoveredRepo: (repoUrl: string | null) => void;
  refreshCampaign: () => Promise<void>;
  isRepoLoading: (repoUrl: string) => boolean;
  clearRepoError: (repoUrl: string) => void;
}

const CampaignContext = createContext<CampaignContextValue | null>(null);

export function useCampaignContext(): CampaignContextValue {
  const ctx = useContext(CampaignContext);
  if (!ctx) {
    // Return a safe no-op default when outside provider
    return {
      campaign: null,
      telescopeRepo: null,
      telescopeData: null,
      hoveredRepo: null,
      loadingRepos: new Set(),
      globalLoading: false,
      errorByRepo: new Map(),
      isLoading: false,
      setCampaign: () => {},
      approveRepo: async () => {},
      rejectRepo: async () => {},
      revokeRepo: async () => {},
      executeCampaign: async () => {},
      openTelescope: async () => {},
      closeTelescope: () => {},
      setHoveredRepo: () => {},
      refreshCampaign: async () => {},
      isRepoLoading: () => false,
      clearRepoError: () => {},
    };
  }
  return ctx;
}

interface CampaignProviderProps {
  sessionId: string | null;
  children: React.ReactNode;
}

export const CampaignProvider: React.FC<CampaignProviderProps> = ({ sessionId, children }) => {
  const [campaign, setCampaign] = useState<RemediationCampaign | null>(null);
  const [telescopeRepo, setTelescopeRepo] = useState<string | null>(null);
  const [telescopeData, setTelescopeData] = useState<TelescopeData | null>(null);
  const [hoveredRepo, setHoveredRepo] = useState<string | null>(null);
  const [loadingRepos, setLoadingRepos] = useState<Set<string>>(new Set());
  const [globalLoading, setGlobalLoading] = useState(false);
  const [errorByRepo, setErrorByRepo] = useState<Map<string, string>>(new Map());

  const addLoadingRepo = useCallback((url: string) => {
    setLoadingRepos(prev => new Set(prev).add(url));
  }, []);

  const removeLoadingRepo = useCallback((url: string) => {
    setLoadingRepos(prev => {
      const next = new Set(prev);
      next.delete(url);
      return next;
    });
  }, []);

  const setRepoError = useCallback((url: string, message: string) => {
    setErrorByRepo(prev => new Map(prev).set(url, message));
  }, []);

  const clearRepoError = useCallback((url: string) => {
    setErrorByRepo(prev => {
      const next = new Map(prev);
      next.delete(url);
      return next;
    });
  }, []);

  const isRepoLoading = useCallback((repoUrl: string) => {
    return loadingRepos.has(repoUrl);
  }, [loadingRepos]);

  const refreshCampaign = useCallback(async () => {
    if (!sessionId) return;
    try {
      const res = await fetch(`${API_BASE}/api/v4/session/${sessionId}/campaign/status`);
      if (res.ok) {
        const data = await res.json();
        setCampaign(data);
      }
    } catch {
      // Silently fail — campaign may not exist yet
    }
  }, [sessionId]);

  const approveRepo = useCallback(async (repoUrl: string) => {
    if (!sessionId) return;
    addLoadingRepo(repoUrl);
    try {
      const encoded = encodeURIComponent(repoUrl);
      await fetch(`${API_BASE}/api/v4/session/${sessionId}/campaign/${encoded}/decide`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decision: 'approve' }),
      });
      await refreshCampaign();
    } catch (err) {
      setRepoError(repoUrl, err instanceof Error ? err.message : 'Failed to approve repo');
    } finally {
      removeLoadingRepo(repoUrl);
    }
  }, [sessionId, refreshCampaign, addLoadingRepo, removeLoadingRepo, setRepoError]);

  const rejectRepo = useCallback(async (repoUrl: string) => {
    if (!sessionId) return;
    addLoadingRepo(repoUrl);
    try {
      const encoded = encodeURIComponent(repoUrl);
      await fetch(`${API_BASE}/api/v4/session/${sessionId}/campaign/${encoded}/decide`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decision: 'reject' }),
      });
      await refreshCampaign();
    } catch (err) {
      setRepoError(repoUrl, err instanceof Error ? err.message : 'Failed to reject repo');
    } finally {
      removeLoadingRepo(repoUrl);
    }
  }, [sessionId, refreshCampaign, addLoadingRepo, removeLoadingRepo, setRepoError]);

  const revokeRepo = useCallback(async (repoUrl: string) => {
    if (!sessionId) return;
    addLoadingRepo(repoUrl);
    try {
      const encoded = encodeURIComponent(repoUrl);
      await fetch(`${API_BASE}/api/v4/session/${sessionId}/campaign/${encoded}/decide`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decision: 'revoke' }),
      });
      await refreshCampaign();
    } catch (err) {
      setRepoError(repoUrl, err instanceof Error ? err.message : 'Failed to revoke repo');
    } finally {
      removeLoadingRepo(repoUrl);
    }
  }, [sessionId, refreshCampaign, addLoadingRepo, removeLoadingRepo, setRepoError]);

  const executeCampaign = useCallback(async () => {
    if (!sessionId) return;
    setGlobalLoading(true);
    try {
      await fetch(`${API_BASE}/api/v4/session/${sessionId}/campaign/execute`, {
        method: 'POST',
      });
      await refreshCampaign();
    } finally {
      setGlobalLoading(false);
    }
  }, [sessionId, refreshCampaign]);

  const openTelescope = useCallback(async (repoUrl: string) => {
    if (!sessionId) return;
    addLoadingRepo(repoUrl);
    try {
      const encoded = encodeURIComponent(repoUrl);
      const res = await fetch(`${API_BASE}/api/v4/session/${sessionId}/campaign/${encoded}/telescope`);
      if (res.ok) {
        const data = await res.json();
        setTelescopeData(data);
        setTelescopeRepo(repoUrl);
      }
    } catch (err) {
      setRepoError(repoUrl, err instanceof Error ? err.message : 'Failed to open telescope');
    } finally {
      removeLoadingRepo(repoUrl);
    }
  }, [sessionId, addLoadingRepo, removeLoadingRepo, setRepoError]);

  const closeTelescope = useCallback(() => {
    setTelescopeRepo(null);
    setTelescopeData(null);
  }, []);

  const isLoading = globalLoading || loadingRepos.size > 0;

  const value = useMemo<CampaignContextValue>(() => ({
    campaign,
    telescopeRepo,
    telescopeData,
    hoveredRepo,
    loadingRepos,
    globalLoading,
    errorByRepo,
    isLoading,
    setCampaign,
    approveRepo,
    rejectRepo,
    revokeRepo,
    executeCampaign,
    openTelescope,
    closeTelescope,
    setHoveredRepo,
    refreshCampaign,
    isRepoLoading,
    clearRepoError,
  }), [
    campaign, telescopeRepo, telescopeData, hoveredRepo,
    loadingRepos, globalLoading, errorByRepo, isLoading,
    approveRepo, rejectRepo, revokeRepo, executeCampaign,
    openTelescope, closeTelescope, refreshCampaign,
    isRepoLoading, clearRepoError,
  ]);

  return (
    <CampaignContext.Provider value={value}>
      {children}
    </CampaignContext.Provider>
  );
};
