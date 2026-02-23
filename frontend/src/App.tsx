import React, { useState, useCallback, useMemo, useRef } from 'react';
import type {
  V4Session,
  ChatMessage,
  TaskEvent,
  DiagnosticPhase,
  TokenUsage,
  CapabilityType,
  CapabilityFormData,
  TroubleshootAppForm,
  AttestationGateData,
} from './types';
import { useWebSocketV4 } from './hooks/useWebSocket';
import { useKeyboardShortcuts } from './hooks/useKeyboardShortcuts';
import { getSessionStatus, startSessionV4, submitAttestation } from './services/api';
import { ToastProvider, useToast } from './components/Toast/ToastContext';
import SidebarNav from './components/Layout/SidebarNav';
import type { NavView } from './components/Layout/SidebarNav';
import HomePage from './components/Home/HomePage';
import CapabilityForm from './components/ActionCenter/CapabilityForm';
import InvestigationView from './components/Investigation/InvestigationView';
import SessionManagerView from './components/Sessions/SessionManagerView';
import IntegrationSettings from './components/Settings/IntegrationSettings';
import ErrorBoundary from './components/ui/ErrorBoundary';
import ErrorBanner from './components/ui/ErrorBanner';
import ForemanHUD from './components/Foreman/ForemanHUD';


type ViewState = 'home' | 'form' | 'investigation' | 'sessions' | 'integrations' | 'settings';

function AppInner() {
  const { addToast } = useToast();
  const [viewState, setViewState] = useState<ViewState>('home');
  const [selectedCapability, setSelectedCapability] = useState<CapabilityType | null>(null);
  const [sessions, setSessions] = useState<V4Session[]>([]);
  const [activeSession, setActiveSession] = useState<V4Session | null>(null);
  const [chatMessages, setChatMessages] = useState<Record<string, ChatMessage[]>>({});
  const [taskEvents, setTaskEvents] = useState<Record<string, TaskEvent[]>>({});
  const [wsConnected, setWsConnected] = useState(false);
  const [currentPhase, setCurrentPhase] = useState<DiagnosticPhase | null>(null);
  const [confidence, setConfidence] = useState(0);
  const [tokenUsage, setTokenUsage] = useState<TokenUsage[]>([]);
  const [attestationGate, setAttestationGate] = useState<AttestationGateData | null>(null);
  const [wsMaxReconnectsHit, setWsMaxReconnectsHit] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const commandTabRef = useRef<HTMLButtonElement>(null);

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

      // Refresh full status on key events (summary, finding, phase_change, success)
      if (['summary', 'finding', 'phase_change', 'success'].includes(event.event_type)) {
        refreshStatus(sid);
      }
    },
    [activeSessionId, refreshStatus]
  );

  const handleChatResponse = useCallback(
    (message: ChatMessage) => {
      if (!activeSessionId) return;
      setChatMessages((prev) => ({
        ...prev,
        [activeSessionId]: [...(prev[activeSessionId] || []), message],
      }));
    },
    [activeSessionId]
  );

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
    onConnect: handleWsConnect,
    onDisconnect: handleWsDisconnect,
    onMaxReconnectsExhausted: handleWsMaxReconnects,
  });

  // Navigation
  const handleNavigate = useCallback((view: NavView) => {
    setViewState(view);
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
    setChatOpen(false);
    setCurrentPhase(null);
    setConfidence(0);
    setAttestationGate(null);
    setTaskEvents({});
  }, []);

  const handleSelectSession = useCallback(
    (session: V4Session) => {
      setActiveSession(session);
      setCurrentPhase(session.status);
      setConfidence(session.confidence);
      setViewState('investigation');
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
          setSessions((prev) => [session, ...prev]);
          setActiveSession(session);
          setCurrentPhase(session.status);
          setConfidence(session.confidence);
          setViewState('investigation');
          refreshStatus(session.session_id);
        } else {
          const placeholderSession: V4Session = {
            session_id: `${data.capability}-${Date.now()}`,
            service_name:
              data.capability === 'pr_review'
                ? 'PR Review'
                : data.capability === 'github_issue_fix'
                ? 'Issue Fix'
                : 'Cluster Diag',
            status: 'initial',
            confidence: 0,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          };
          setSessions((prev) => [placeholderSession, ...prev]);
          setActiveSession(placeholderSession);
          setCurrentPhase('initial');
          setConfidence(0);
          setViewState('investigation');
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Failed to start session';
        addToast('error', msg);
      }
    },
    [refreshStatus]
  );

  const handleNewChatMessage = useCallback(
    (message: ChatMessage) => {
      if (!activeSessionId) return;
      setChatMessages((prev) => ({
        ...prev,
        [activeSessionId]: [...(prev[activeSessionId] || []), message],
      }));
    },
    [activeSessionId]
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

  const currentChatMessages = activeSessionId ? chatMessages[activeSessionId] || [] : [];
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

  // Detect if agent needs user input
  const needsInput = useMemo(() => {
    const msgs = currentChatMessages.filter(m => m.role === 'assistant');
    if (!msgs.length) return false;
    const last = msgs[msgs.length - 1];
    return last.content.trim().endsWith('?') ||
      /\b(confirm|approve|proceed|rollback|input needed)\b/i.test(last.content);
  }, [currentChatMessages]);

  // Derive nav view from viewState
  const navView: NavView =
    viewState === 'sessions' ? 'sessions' : viewState === 'integrations' ? 'integrations' : viewState === 'settings' ? 'settings' : 'home';

  const showSidebar = viewState !== 'investigation';

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
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
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
          <div className="flex-1 flex items-center justify-center text-gray-500 text-sm">
            Settings — Coming Soon
          </div>
        )}

        {viewState === 'form' && selectedCapability && (
          <CapabilityForm
            capability={selectedCapability}
            onBack={handleGoHome}
            onSubmit={handleFormSubmit}
          />
        )}

        {viewState === 'investigation' && activeSession && (
          <>
            {/* Foreman HUD Header */}
            <ForemanHUD
              sessionId={activeSession.session_id}
              serviceName={activeSession.service_name}
              phase={currentPhase}
              confidence={confidence}
              events={currentTaskEvents}
              wsConnected={wsConnected}
              needsInput={needsInput}
              onGoHome={handleGoHome}
              onOpenChat={() => setChatOpen(true)}
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
                  messages={currentChatMessages}
                  events={currentTaskEvents}
                  onNewMessage={handleNewChatMessage}
                  wsConnected={wsConnected}
                  phase={currentPhase}
                  confidence={confidence}
                  tokenUsage={tokenUsage}
                  attestationGate={attestationGate}
                  onAttestationDecision={handleAttestationDecision}
                  needsInput={needsInput}
                  chatOpen={chatOpen}
                  onChatToggle={setChatOpen}
                  commandTabRef={commandTabRef}
                />
              </ErrorBoundary>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function App() {
  return (
    <ToastProvider>
      <AppInner />
    </ToastProvider>
  );
}

export default App;
