import React, { useState, useCallback, useMemo, useRef, useEffect } from 'react';
import type {
  V4Session,
  ChatMessage,
  TaskEvent,
  DiagnosticPhase,
  TokenUsage,
  CapabilityType,
  CapabilityFormData,
  TroubleshootAppForm,
  ClusterDiagnosticsForm,
  NetworkTroubleshootingForm,
  AttestationGateData,
  DiagnosticScope,
} from './types';
import { useWebSocketV4 } from './hooks/useWebSocket';
import type { ChatStreamEndPayload } from './hooks/useWebSocket';
import { useKeyboardShortcuts } from './hooks/useKeyboardShortcuts';
import { API_BASE_URL, getSessionStatus, startSessionV4, submitAttestation } from './services/api';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { ToastProvider, useToast } from './components/Toast/ToastContext';
import { ChatProvider } from './contexts/ChatContext';
import { CampaignProvider } from './contexts/CampaignContext';
import SidebarNav from './components/Layout/SidebarNav';
import type { NavView } from './components/Layout/SidebarNav';
import HomePage from './components/Home/HomePage';
import CapabilityForm from './components/ActionCenter/CapabilityForm';
import InvestigationView from './components/Investigation/InvestigationView';
import SessionManagerView from './components/Sessions/SessionManagerView';
import IntegrationSettings from './components/Settings/IntegrationSettings';
import SettingsView from './components/Settings/SettingsView';
import ErrorBoundary from './components/ui/ErrorBoundary';
import ErrorBanner from './components/ui/ErrorBanner';
import ForemanHUD from './components/Foreman/ForemanHUD';
import PostMortemDossierView from './components/Investigation/PostMortemDossierView';
import ClusterWarRoom from './components/ClusterDiagnostic/ClusterWarRoom';
import AgentMatrixView from './components/AgentMatrix/AgentMatrixView';
import TopologyEditorView from './components/TopologyEditor/TopologyEditorView';
import IPAMDashboard from './components/IPAM/IPAMDashboard';
import NetworkWarRoom from './components/NetworkTroubleshooting/NetworkWarRoom';
import ReachabilityMatrix from './components/NetworkTroubleshooting/ReachabilityMatrix';
import NetworkAdaptersView from './components/Network/NetworkAdaptersView';
import DeviceMonitoring from './components/Network/DeviceMonitoring';
import ObservatoryView from './components/Observatory/ObservatoryView';
import DBOverview from './components/Database/DBOverview';
import DBConnections from './components/Database/DBConnections';
import DBDiagnostics from './components/Database/DBDiagnostics';
import DBMonitoring from './components/Database/DBMonitoring';
import DBSchema from './components/Database/DBSchema';
import DBOperations from './components/Database/DBOperations';
import KubernetesClusters from './components/Kubernetes/KubernetesClusters';
import { Breadcrumbs } from './components/shared';


type ViewState = 'home' | 'form' | 'investigation' | 'sessions' | 'integrations' | 'settings' | 'dossier' | 'cluster-diagnostics' | 'agent-matrix' | 'network-troubleshooting' | 'network-topology' | 'network-adapters' | 'device-monitoring' | 'ipam' | 'matrix' | 'observatory' | 'db-overview' | 'db-connections' | 'db-diagnostics' | 'db-monitoring' | 'db-schema' | 'db-operations' | 'k8s-clusters';

function AppInner() {
  const { addToast } = useToast();
  const [viewState, setViewState] = useState<ViewState>('home');
  const [selectedCapability, setSelectedCapability] = useState<CapabilityType | null>(null);
  const [sessions, setSessions] = useState<V4Session[]>([]);
  const [activeSession, setActiveSession] = useState<V4Session | null>(null);
  const [taskEvents, setTaskEvents] = useState<Record<string, TaskEvent[]>>({});
  const [wsConnected, setWsConnected] = useState(false);
  const [currentPhase, setCurrentPhase] = useState<DiagnosticPhase | null>(null);
  const [confidence, setConfidence] = useState(0);
  const [tokenUsage, setTokenUsage] = useState<TokenUsage[]>([]);
  const [attestationGate, setAttestationGate] = useState<AttestationGateData | null>(null);
  const [wsMaxReconnectsHit, setWsMaxReconnectsHit] = useState(false);
  const activeSessionId = activeSession?.session_id ?? null;

  // Refresh session status
  const refreshStatus = useCallback(async (sessionId: string) => {
    try {
      const status = await getSessionStatus(sessionId);
      setCurrentPhase(status.phase);
      setConfidence(status.confidence);
      setTokenUsage(status.token_usage);
    } catch {
      // silent
    }
  }, []);

  // WebSocket handlers
  const handleTaskEvent = useCallback(
    (event: TaskEvent) => {
      const sid = event.session_id || activeSessionId;
      if (!sid) return;

      // C3: Cap events per session at 500 to prevent unbounded memory growth
      setTaskEvents((prev) => {
        const existing = prev[sid] || [];
        const updated = [...existing, event];
        return { ...prev, [sid]: updated.length > 500 ? updated.slice(-500) : updated };
      });

      // Extract phase from phase_change events directly (instant update)
      if (event.event_type === 'phase_change' && event.details?.phase) {
        setCurrentPhase(event.details.phase as DiagnosticPhase);
      }

      // Extract confidence from summary events directly
      if (event.event_type === 'summary' && event.details?.confidence != null) {
        setConfidence(event.details.confidence as number);
      }

      // Handle attestation gate
      if (event.event_type === 'attestation_required' && event.details) {
        setAttestationGate({
          gate_type: event.details.gate_type as AttestationGateData['gate_type'],
          human_decision: null,
          decided_by: null,
          decided_at: null,
          proposed_action: event.details.proposed_action as string,
          findings_count: event.details.findings_count as number,
          confidence: event.details.confidence as number,
        });
      }

      // Handle waiting_for_input — refresh status to pick up latest state
      if (event.event_type === 'waiting_for_input') {
        refreshStatus(sid);
      }

      // Refresh full status on key events (summary, finding, phase_change, success)
      if (['summary', 'finding', 'phase_change', 'success'].includes(event.event_type)) {
        refreshStatus(sid);
      }
    },
    [activeSessionId, refreshStatus]
  );

  // Chat responses bridged to ChatContext via ref callback
  const chatResponseRef = useRef<((msg: ChatMessage) => void) | null>(null);
  const handleChatResponse = useCallback((message: ChatMessage) => {
    chatResponseRef.current?.(message);
  }, []);

  // Streaming bridged to ChatContext via ref callbacks
  const streamStartRef = useRef<(() => void) | null>(null);
  const streamAppendRef = useRef<((chunk: string) => void) | null>(null);
  const streamFinishRef = useRef<((full: string, meta?: ChatMessage['metadata']) => void) | null>(null);

  const handleChatChunk = useCallback((chunk: string) => {
    // Auto-start stream on first chunk if not already streaming
    streamStartRef.current?.();
    streamAppendRef.current?.(chunk);
  }, []);

  const handleChatStreamEnd = useCallback((payload: ChatStreamEndPayload) => {
    const meta: ChatMessage['metadata'] = {};
    if (payload.phase) {
      meta.newPhase = payload.phase;
      meta.newConfidence = payload.confidence ?? 0;
    }
    streamFinishRef.current?.(payload.full_response, meta);
    // Instant phase sync
    if (payload.phase) {
      setCurrentPhase(payload.phase as DiagnosticPhase);
      setConfidence(payload.confidence ?? 0);
    }
  }, []);

  // Instant phase/confidence sync from chat response metadata (eliminates 5s stale window)
  const handleChatPhaseUpdate = useCallback((phase: string, conf: number) => {
    setCurrentPhase(phase as DiagnosticPhase);
    setConfidence(conf);
  }, []);

  const handleWsConnect = useCallback(() => {
    setWsConnected(true);
    setWsMaxReconnectsHit(false);
  }, []);
  const handleWsDisconnect = useCallback(() => setWsConnected(false), []);
  const handleWsMaxReconnects = useCallback(() => {
    setWsMaxReconnectsHit(true);
    addToast('warning', 'Live connection lost — showing cached data');
  }, [addToast]);

  useWebSocketV4(activeSessionId, {
    onTaskEvent: handleTaskEvent,
    onChatResponse: handleChatResponse,
    onChatChunk: handleChatChunk,
    onChatStreamEnd: handleChatStreamEnd,
    onConnect: handleWsConnect,
    onDisconnect: handleWsDisconnect,
    onMaxReconnectsExhausted: handleWsMaxReconnects,
  });

  // Navigation
  const handleNavigate = useCallback((view: NavView) => {
    if (view === 'agents') {
      setViewState('agent-matrix');
    } else if (view === 'app-diagnostics') {
      setSelectedCapability('troubleshoot_app');
      setViewState('form');
    } else if (view === 'k8s-diagnostics') {
      setSelectedCapability('cluster_diagnostics');
      setViewState('form');
    } else if (view === 'network-troubleshooting') {
      setSelectedCapability('network_troubleshooting');
      setViewState('form');
    } else if (view === 'pr-review') {
      setSelectedCapability('pr_review');
      setViewState('form');
    } else if (view === 'github-issue-fix') {
      setSelectedCapability('github_issue_fix');
      setViewState('form');
    } else {
      setViewState(view as ViewState);
    }
    if (view === 'home') {
      setSelectedCapability(null);
      setActiveSession(null);
    }
  }, []);

  const handleSelectCapability = useCallback((capability: CapabilityType) => {
    setSelectedCapability(capability);
    setViewState('form');
  }, []);

  // C5: Reset ALL investigation-related state atomically on session switch
  const handleGoHome = useCallback(() => {
    setViewState('home');
    setSelectedCapability(null);
    setActiveSession(null);
    setCurrentPhase(null);
    setConfidence(0);
    setAttestationGate(null);
    setTaskEvents({});
  }, []);

  const handleNavigateToDossier = useCallback(() => {
    setViewState('dossier');
  }, []);

  const handleDossierBack = useCallback(() => {
    setViewState('investigation');
  }, []);

  const handleSelectSession = useCallback(
    (session: V4Session) => {
      setActiveSession(session);
      setCurrentPhase(session.status);
      setConfidence(session.confidence);
      // Route to the correct view based on capability
      if (session.capability === 'cluster_diagnostics') {
        setViewState('cluster-diagnostics');
      } else if (session.capability === 'network_troubleshooting') {
        setViewState('network-troubleshooting');
      } else {
        setViewState('investigation');
      }
      refreshStatus(session.session_id);
    },
    [refreshStatus]
  );

  const handleFormSubmit = useCallback(
    async (data: CapabilityFormData) => {
      try {
        if (data.capability === 'troubleshoot_app') {
          const session = await startSessionV4({
            service_name: data.service_name,
            time_window: data.time_window,
            trace_id: data.trace_id,
            namespace: data.namespace,
            elk_index: (data as TroubleshootAppForm).elk_index,
            repo_url: data.repo_url,
            profileId: (data as TroubleshootAppForm).profile_id,
          });
          const sessionWithCap = { ...session, capability: 'troubleshoot_app' as const };
          setSessions((prev) => [sessionWithCap, ...prev]);
          setActiveSession(sessionWithCap);
          setCurrentPhase(session.status);
          setConfidence(session.confidence);
          setViewState('investigation');
          refreshStatus(session.session_id);
        } else if (data.capability === 'cluster_diagnostics') {
          const clusterData = data as ClusterDiagnosticsForm;
          let profileId = clusterData.profile_id;

          // Inline profile creation if "Save this cluster" is checked and no profile selected
          if (!profileId && (clusterData.save_cluster ?? true) && clusterData.cluster_url) {
            try {
              const { createProfile } = await import('./services/profileApi');
              const newProfile = await createProfile({
                name: clusterData.cluster_name || new URL(clusterData.cluster_url).hostname,
                cluster_url: clusterData.cluster_url,
                cluster_type: 'kubernetes',
                environment: 'prod',
                auth_method: clusterData.auth_method || 'token',
                auth_credential: clusterData.auth_token || '',
              });
              profileId = newProfile.id;
              addToast('success', 'Cluster saved to profiles');
            } catch (err) {
              console.warn('Failed to save cluster profile:', err);
              addToast('warning', 'Could not save profile — proceeding with one-time credentials');
            }
          }

          // Build diagnostic scope from form selections
          const includeCtrlPlane = clusterData.include_control_plane ?? true;
          const scope: DiagnosticScope = {
            level: (clusterData.resource_type && clusterData.workload) ? 'workload'
              : clusterData.namespace ? 'namespace' : 'cluster',
            namespaces: clusterData.namespace ? [clusterData.namespace] : [],
            workload_key: clusterData.resource_type && clusterData.workload
              ? `${clusterData.resource_type}/${clusterData.workload}` : undefined,
            domains: includeCtrlPlane
              ? ['ctrl_plane', 'node', 'network', 'storage']
              : ['node', 'network', 'storage'],
            include_control_plane: includeCtrlPlane,
          };

          const session = await startSessionV4({
            service_name: 'Cluster Diagnostics',
            time_window: '1h',
            namespace: clusterData.namespace || '',
            cluster_url: clusterData.cluster_url,
            capability: 'cluster_diagnostics',
            profile_id: profileId,
            scope,
            // Ad-hoc auth fields (used when no profile)
            ...((!profileId && clusterData.auth_token) ? {
              auth_token: clusterData.auth_token,
              auth_method: clusterData.auth_method || 'token',
            } : {}),
          });
          const clusterSession = { ...session, capability: 'cluster_diagnostics' as const };
          setSessions((prev) => [clusterSession, ...prev]);
          setActiveSession(clusterSession);
          setCurrentPhase(session.status);
          setConfidence(session.confidence);
          setViewState('cluster-diagnostics');
          refreshStatus(session.session_id);
        } else if (data.capability === 'network_troubleshooting') {
          const nd = data as NetworkTroubleshootingForm;
          const response = await fetch(`${API_BASE_URL}/api/v4/network/diagnose`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              src_ip: nd.src_ip,
              dst_ip: nd.dst_ip,
              port: parseInt(nd.port),
              protocol: nd.protocol,
            }),
          });
          if (!response.ok) {
            const errText = await response.text().catch(() => response.statusText);
            throw new Error(`Network diagnosis failed: ${errText}`);
          }
          const result = await response.json();

          const session: V4Session = {
            session_id: result.session_id,
            service_name: `Network: ${nd.src_ip} \u2192 ${nd.dst_ip}`,
            status: (result.status || 'initial') as DiagnosticPhase,
            confidence: 0,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            incident_id: result.flow_id || '',
            capability: 'network_troubleshooting',
          };

          setSessions((prev) => [session, ...prev]);
          setActiveSession(session);
          setCurrentPhase(session.status);
          setConfidence(session.confidence);
          setViewState('network-troubleshooting');
        } else if (data.capability === 'pr_review' || data.capability === 'github_issue_fix') {
          // PR Review and Issue Fixer use the standard session API
          const session = await startSessionV4({
            service_name: data.capability === 'pr_review' ? 'PR Review' : 'Issue Fix',
            time_window: '1h',
            capability: data.capability,
            ...(data.capability === 'pr_review' ? { repo_url: (data as import('./types').PRReviewForm).repo_url } : {}),
            ...(data.capability === 'github_issue_fix' ? { repo_url: (data as import('./types').GithubIssueFixForm).repo_url } : {}),
          });
          setSessions((prev) => [{ ...session, capability: data.capability }, ...prev]);
          setActiveSession({ ...session, capability: data.capability });
          setCurrentPhase(session.status);
          setConfidence(session.confidence);
          setViewState('investigation');
          refreshStatus(session.session_id);
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Failed to start session';
        addToast('error', msg);
      }
    },
    [refreshStatus]
  );

  const handleAttestationDecision = useCallback(
    (decision: string) => {
      if (activeSessionId && attestationGate) {
        submitAttestation(activeSessionId, attestationGate.gate_type, decision, 'user').catch((err) => {
          addToast('error', err instanceof Error ? err.message : 'Failed to submit attestation');
        });
      }
      setAttestationGate(null);
    },
    [activeSessionId, attestationGate, addToast]
  );

  const currentTaskEvents = activeSessionId ? taskEvents[activeSessionId] || [] : [];

  // Keyboard shortcuts
  const shortcutHandlers = useMemo(
    () => ({
      onNewSession: () => handleGoHome(),
      onSelectCapability: handleSelectCapability,
      onGoHome: handleGoHome,
    }),
    [handleGoHome, handleSelectCapability]
  );

  useKeyboardShortcuts(shortcutHandlers);

  // Derive nav view from viewState
  const capabilityToNav: Record<string, NavView> = {
    troubleshoot_app: 'app-diagnostics',
    cluster_diagnostics: 'k8s-diagnostics',
    network_troubleshooting: 'network-troubleshooting',
    pr_review: 'pr-review',
    github_issue_fix: 'github-issue-fix',
  };

  const viewToNav: Record<string, NavView> = {
    sessions: 'sessions', integrations: 'integrations', settings: 'settings',
    'agent-matrix': 'agents', 'cluster-diagnostics': 'k8s-diagnostics',
    'k8s-clusters': 'k8s-clusters', 'network-topology': 'network-topology',
    'network-adapters': 'network-adapters', 'device-monitoring': 'device-monitoring',
    ipam: 'ipam', matrix: 'matrix',
    observatory: 'observatory',
    'db-overview': 'db-overview', 'db-connections': 'db-connections',
    'db-diagnostics': 'db-diagnostics', 'db-monitoring': 'db-monitoring',
    'db-schema': 'db-schema', 'db-operations': 'db-operations',
  };

  const navView: NavView =
    viewState === 'form' && selectedCapability ? (capabilityToNav[selectedCapability] || 'home')
    : viewToNav[viewState] || 'home';

  const showSidebar = viewState !== 'investigation' && viewState !== 'dossier' && viewState !== 'cluster-diagnostics' && viewState !== 'agent-matrix' && viewState !== 'network-troubleshooting';

  // Pin-responsive layout: shift main content when flyout is pinned
  const [isSidebarPinned, setIsSidebarPinned] = useState(() => {
    try { return localStorage.getItem('sidebar-pinned') === 'true'; } catch { return false; }
  });
  useEffect(() => {
    const handlePinChange = () => {
      try { setIsSidebarPinned(localStorage.getItem('sidebar-pinned') === 'true'); } catch { /* noop */ }
    };
    window.addEventListener('sidebar-pin-change', handlePinChange);
    return () => window.removeEventListener('sidebar-pin-change', handlePinChange);
  }, []);

  // Group parents are non-clickable text labels (no route)
  const breadcrumbMap: Record<string, { label: string; parent?: string }> = {
    home: { label: 'Dashboard' },
    // Diagnostics group
    sessions: { label: 'Sessions', parent: 'home' },
    'app-diagnostics': { label: 'App Diagnostics', parent: 'home' },
    'k8s-diagnostics': { label: 'Cluster Diagnostics', parent: 'home' },
    'k8s-clusters': { label: 'Clusters', parent: 'home' },
    'network-troubleshooting': { label: 'Network Path', parent: 'home' },
    // Code group
    'pr-review': { label: 'PR Review', parent: 'home' },
    'github-issue-fix': { label: 'Issue Fixer', parent: 'home' },
    // Database group
    'db-overview': { label: 'Overview', parent: 'home' },
    'db-connections': { label: 'Connections', parent: 'home' },
    'db-diagnostics': { label: 'Diagnostics', parent: 'home' },
    'db-monitoring': { label: 'Monitoring', parent: 'home' },
    'db-schema': { label: 'Schema', parent: 'home' },
    'db-operations': { label: 'Operations', parent: 'home' },
    // Networking group
    'network-topology': { label: 'Topology', parent: 'home' },
    'network-adapters': { label: 'Adapters', parent: 'home' },
    'device-monitoring': { label: 'Device Monitoring', parent: 'home' },
    ipam: { label: 'IPAM', parent: 'home' },
    matrix: { label: 'Matrix', parent: 'home' },
    observatory: { label: 'Observatory', parent: 'home' },
    // Configuration group
    integrations: { label: 'Integrations', parent: 'home' },
    settings: { label: 'Settings', parent: 'home' },
    agents: { label: 'Agent Matrix', parent: 'home' },
  };

  const getBreadcrumbs = () => {
    // Use navView for breadcrumbs — it resolves form+capability to the correct nav item
    const key = viewState === 'form' ? navView : viewState;
    const entry = breadcrumbMap[key];
    if (!entry) return [];
    const items: { label: string; onClick?: () => void }[] = [];
    if (entry.parent) {
      const parentEntry = breadcrumbMap[entry.parent];
      if (parentEntry) {
        items.push({ label: parentEntry.label, onClick: () => handleNavigate('home') });
      }
    }
    items.push({ label: entry.label });
    return items;
  };

  return (
    <div className="flex h-screen w-full overflow-hidden text-slate-100 antialiased" style={{ backgroundColor: '#0f2023' }}>
      {/* Sidebar Nav - hidden during investigation (war room is full width) */}
      {showSidebar && (
        <SidebarNav
          activeView={navView}
          onNavigate={handleNavigate}
          onNewMission={() => {
            setSelectedCapability(null);
            setViewState('home');
          }}
        />
      )}

      {/* Main content */}
      <div
        className="flex-1 flex flex-col min-w-0 overflow-hidden transition-all duration-300 ease-out"
        style={{ paddingLeft: showSidebar && isSidebarPinned ? 215 : 0 }}
      >
        {showSidebar && <Breadcrumbs items={getBreadcrumbs()} />}

        {viewState === 'home' && (
          <HomePage
            onSelectCapability={handleSelectCapability}
            sessions={sessions}
            onSessionsChange={setSessions}
            onSelectSession={handleSelectSession}
            wsConnected={wsConnected}
          />
        )}

        {viewState === 'sessions' && (
          <SessionManagerView
            sessions={sessions}
            onSessionsChange={setSessions}
            onSelectSession={handleSelectSession}
          />
        )}

        {viewState === 'integrations' && (
          <IntegrationSettings onBack={handleGoHome} />
        )}

        {viewState === 'settings' && (
          <SettingsView />
        )}

        {viewState === 'network-topology' && (
          <TopologyEditorView />
        )}

        {viewState === 'network-adapters' && (
          <NetworkAdaptersView />
        )}

        {viewState === 'device-monitoring' && (
          <DeviceMonitoring />
        )}

        {viewState === 'ipam' && (
          <IPAMDashboard />
        )}

        {viewState === 'matrix' && (
          <ReachabilityMatrix />
        )}

        {viewState === 'observatory' && (
          <ObservatoryView />
        )}

        {viewState === 'db-overview' && <DBOverview />}
        {viewState === 'db-connections' && <DBConnections />}
        {viewState === 'db-diagnostics' && <DBDiagnostics />}
        {viewState === 'db-monitoring' && <DBMonitoring />}
        {viewState === 'db-schema' && <DBSchema />}
        {viewState === 'db-operations' && <DBOperations />}

        {viewState === 'k8s-clusters' && <KubernetesClusters />}

        {viewState === 'form' && selectedCapability && (
          <CapabilityForm
            capability={selectedCapability}
            onBack={handleGoHome}
            onSubmit={handleFormSubmit}
          />
        )}

        {viewState === 'investigation' && activeSession && (
          <ChatProvider sessionId={activeSessionId} events={currentTaskEvents} onRegisterChatHandler={chatResponseRef} onRegisterStreamStart={streamStartRef} onRegisterStreamAppend={streamAppendRef} onRegisterStreamFinish={streamFinishRef} onPhaseUpdate={handleChatPhaseUpdate}>
          <CampaignProvider sessionId={activeSessionId}>
            {/* Foreman HUD Header */}
            <ForemanHUD
              sessionId={activeSession.session_id}
              serviceName={activeSession.service_name}
              phase={currentPhase}
              confidence={confidence}
              events={currentTaskEvents}
              wsConnected={wsConnected}
              needsInput={false}
              onGoHome={handleGoHome}
              onOpenChat={() => {/* ChatContext handles open */}}
            />

            {/* WS disconnect banner */}
            {wsMaxReconnectsHit && (
              <div className="px-6 py-0">
                <ErrorBanner
                  message="Live connection lost — showing cached data"
                  severity="warning"
                  onDismiss={() => setWsMaxReconnectsHit(false)}
                  onRetry={() => window.location.reload()}
                />
              </div>
            )}

            {/* 3-column investigation layout + bottom progress bar */}
            <div className="flex-1 overflow-hidden">
              <ErrorBoundary>
                <InvestigationView
                  session={activeSession}
                  events={currentTaskEvents}
                  wsConnected={wsConnected}
                  phase={currentPhase}
                  confidence={confidence}
                  tokenUsage={tokenUsage}
                  attestationGate={attestationGate}
                  onAttestationDecision={handleAttestationDecision}
                  onNavigateToDossier={handleNavigateToDossier}
                />
              </ErrorBoundary>
            </div>
          </CampaignProvider>
          </ChatProvider>
        )}

        {viewState === 'dossier' && activeSession && (
          <PostMortemDossierView
            sessionId={activeSession.session_id}
            onBack={handleDossierBack}
          />
        )}

        {viewState === 'cluster-diagnostics' && activeSession && (
          <ChatProvider sessionId={activeSessionId} events={currentTaskEvents} onRegisterChatHandler={chatResponseRef} onRegisterStreamStart={streamStartRef} onRegisterStreamAppend={streamAppendRef} onRegisterStreamFinish={streamFinishRef} onPhaseUpdate={handleChatPhaseUpdate}>
            <ClusterWarRoom
              session={activeSession}
              events={currentTaskEvents}
              wsConnected={wsConnected}
              phase={currentPhase}
              confidence={confidence}
              onGoHome={handleGoHome}
            />
          </ChatProvider>
        )}

        {viewState === 'agent-matrix' && (
          <AgentMatrixView onGoHome={handleGoHome} />
        )}

        {viewState === 'network-troubleshooting' && activeSession && (
          <NetworkWarRoom
            session={activeSession}
            onGoHome={handleGoHome}
          />
        )}
      </div>
    </div>
  );
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: true,
      retry: 1,
    },
  },
});

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <AppInner />
      </ToastProvider>
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  );
}

export default App;
