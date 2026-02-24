import React, { createContext, useContext, useState, useCallback, useMemo } from 'react';
import type { RemediationCampaign, TelescopeData } from '../types/campaign';

const API_BASE = 'http://localhost:8000';

interface CampaignState {
  campaign: RemediationCampaign | null;
  telescopeRepo: string | null;
  telescopeData: TelescopeData | null;
  hoveredRepo: string | null;
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
  const [isLoading, setIsLoading] = useState(false);

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
    setIsLoading(true);
    try {
      const encoded = encodeURIComponent(repoUrl);
      await fetch(`${API_BASE}/api/v4/session/${sessionId}/campaign/${encoded}/decide`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decision: 'approve' }),
      });
      await refreshCampaign();
    } finally {
      setIsLoading(false);
    }
  }, [sessionId, refreshCampaign]);

  const rejectRepo = useCallback(async (repoUrl: string) => {
    if (!sessionId) return;
    setIsLoading(true);
    try {
      const encoded = encodeURIComponent(repoUrl);
      await fetch(`${API_BASE}/api/v4/session/${sessionId}/campaign/${encoded}/decide`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decision: 'reject' }),
      });
      await refreshCampaign();
    } finally {
      setIsLoading(false);
    }
  }, [sessionId, refreshCampaign]);

  const revokeRepo = useCallback(async (repoUrl: string) => {
    if (!sessionId) return;
    setIsLoading(true);
    try {
      const encoded = encodeURIComponent(repoUrl);
      await fetch(`${API_BASE}/api/v4/session/${sessionId}/campaign/${encoded}/decide`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decision: 'revoke' }),
      });
      await refreshCampaign();
    } finally {
      setIsLoading(false);
    }
  }, [sessionId, refreshCampaign]);

  const executeCampaign = useCallback(async () => {
    if (!sessionId) return;
    setIsLoading(true);
    try {
      await fetch(`${API_BASE}/api/v4/session/${sessionId}/campaign/execute`, {
        method: 'POST',
      });
      await refreshCampaign();
    } finally {
      setIsLoading(false);
    }
  }, [sessionId, refreshCampaign]);

  const openTelescope = useCallback(async (repoUrl: string) => {
    if (!sessionId) return;
    setIsLoading(true);
    try {
      const encoded = encodeURIComponent(repoUrl);
      const res = await fetch(`${API_BASE}/api/v4/session/${sessionId}/campaign/${encoded}/telescope`);
      if (res.ok) {
        const data = await res.json();
        setTelescopeData(data);
        setTelescopeRepo(repoUrl);
      }
    } finally {
      setIsLoading(false);
    }
  }, [sessionId]);

  const closeTelescope = useCallback(() => {
    setTelescopeRepo(null);
    setTelescopeData(null);
  }, []);

  const value = useMemo<CampaignContextValue>(() => ({
    campaign,
    telescopeRepo,
    telescopeData,
    hoveredRepo,
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
  }), [
    campaign, telescopeRepo, telescopeData, hoveredRepo, isLoading,
    approveRepo, rejectRepo, revokeRepo, executeCampaign,
    openTelescope, closeTelescope, refreshCampaign,
  ]);

  return (
    <CampaignContext.Provider value={value}>
      {children}
    </CampaignContext.Provider>
  );
};
