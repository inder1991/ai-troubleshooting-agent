import React, { useState, useCallback, useMemo } from 'react';
import type {
  V4Session,
  ChatMessage,
  TaskEvent,
  DiagnosticPhase,
  TokenUsage,
  CapabilityType,
  CapabilityFormData,
  TroubleshootAppForm,
} from './types';
import { useWebSocketV4 } from './hooks/useWebSocket';
import { useKeyboardShortcuts } from './hooks/useKeyboardShortcuts';
import { getSessionStatus, startSessionV4 } from './services/api';
import { ToastProvider, useToast } from './components/Toast/ToastContext';
import SidebarNav from './components/Layout/SidebarNav';
import type { NavView } from './components/Layout/SidebarNav';
import HomePage from './components/Home/HomePage';
import CapabilityForm from './components/ActionCenter/CapabilityForm';
import InvestigationView from './components/Investigation/InvestigationView';
import SessionManagerView from './components/Sessions/SessionManagerView';
import IntegrationSettings from './components/Settings/IntegrationSettings';

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

      setTaskEvents((prev) => ({
        ...prev,
        [sid]: [...(prev[sid] || []), event],
      }));

      // Refresh status on all event types for real-time updates
      refreshStatus(sid);
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

  const handleWsConnect = useCallback(() => setWsConnected(true), []);
  const handleWsDisconnect = useCallback(() => setWsConnected(false), []);

  useWebSocketV4(activeSessionId, {
    onTaskEvent: handleTaskEvent,
    onChatResponse: handleChatResponse,
    onConnect: handleWsConnect,
    onDisconnect: handleWsDisconnect,
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

  const handleGoHome = useCallback(() => {
    setViewState('home');
    setSelectedCapability(null);
    setActiveSession(null);
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
            {/* Investigation header - matches reference war room style */}
            <header className="h-14 border-b border-primary/20 bg-background-dark/50 backdrop-blur-md flex items-center justify-between px-6 shrink-0">
              <div className="flex items-center gap-4">
                <button
                  onClick={handleGoHome}
                  className="flex items-center gap-2 group"
                >
                  <div className="w-8 h-8 bg-primary rounded flex items-center justify-center">
                    <span className="material-symbols-outlined text-white text-lg" style={{ fontFamily: 'Material Symbols Outlined' }}>bug_report</span>
                  </div>
                  <span className="font-bold tracking-tight text-lg">
                    Debug<span className="text-primary">Duck</span>
                  </span>
                </button>
                <div className="h-4 w-px bg-slate-700 mx-2" />
                <div className="flex flex-col">
                  <span className="text-[10px] uppercase tracking-widest text-slate-500 font-bold">Investigation ID</span>
                  <span className="text-xs font-mono text-primary">{activeSession.session_id.substring(0, 8).toUpperCase()}</span>
                </div>
              </div>
              <div className="flex items-center gap-6">
                {currentPhase && (
                  <div className="flex items-center gap-2 px-3 py-1 bg-red-500/10 border border-red-500/20 rounded-full">
                    <span className="w-2 h-2 bg-red-500 rounded-full animate-pulse" />
                    <span className="text-[10px] font-bold text-red-500 uppercase tracking-wider">
                      Phase: {currentPhase.replace(/_/g, ' ')}
                    </span>
                  </div>
                )}
                {/* User Avatars */}
                <div className="flex -space-x-2">
                  <div className="w-7 h-7 rounded-full border-2 border-background-dark bg-primary/20 flex items-center justify-center">
                    <span className="material-symbols-outlined text-primary text-xs" style={{ fontFamily: 'Material Symbols Outlined' }}>person</span>
                  </div>
                  <div className="w-7 h-7 rounded-full border-2 border-background-dark bg-slate-800 flex items-center justify-center text-[10px] font-bold text-slate-400">+1</div>
                </div>
                <button className="bg-primary/10 hover:bg-primary/20 text-primary p-1.5 rounded-lg transition-colors">
                  <span className="material-symbols-outlined text-xl" style={{ fontFamily: 'Material Symbols Outlined' }}>share</span>
                </button>
              </div>
            </header>

            {/* 3-column investigation layout + bottom progress bar */}
            <div className="flex-1 overflow-hidden">
              <InvestigationView
                session={activeSession}
                messages={currentChatMessages}
                events={currentTaskEvents}
                onNewMessage={handleNewChatMessage}
                wsConnected={wsConnected}
                phase={currentPhase}
                confidence={confidence}
                tokenUsage={tokenUsage}
              />
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
