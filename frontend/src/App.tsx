import React, { useState, useCallback, useMemo } from 'react';
import type {
  V4Session,
  ChatMessage,
  TaskEvent,
  DiagnosticPhase,
  TokenUsage,
  CapabilityType,
  CapabilityFormData,
} from './types';
import { useWebSocketV4 } from './hooks/useWebSocket';
import { useKeyboardShortcuts } from './hooks/useKeyboardShortcuts';
import { getSessionStatus, startSessionV4 } from './services/api';
import SessionSidebar from './components/SessionSidebar';
import ActionCenter from './components/ActionCenter/ActionCenter';
import CapabilityForm from './components/ActionCenter/CapabilityForm';
import TabLayout from './components/TabLayout';
import ChatTab from './components/Chat/ChatTab';
import DashboardTab from './components/Dashboard/DashboardTab';
import ActivityLogTab from './components/ActivityLog/ActivityLogTab';
import ResultsPanel from './components/ResultsPanel';
import ProgressBar from './components/ProgressBar';
import IntegrationSettings from './components/Settings/IntegrationSettings';

type ViewState = 'home' | 'form' | 'session' | 'settings';

function App() {
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
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const activeSessionId = activeSession?.session_id ?? null;

  // Refresh session status when events indicate progress
  const refreshStatus = useCallback(async (sessionId: string) => {
    try {
      const status = await getSessionStatus(sessionId);
      setCurrentPhase(status.phase);
      setConfidence(status.confidence);
      setTokenUsage(status.token_usage);
    } catch {
      // Status refresh failed silently
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

      if (event.event_type === 'success' || event.event_type === 'error') {
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

  const handleWsConnect = useCallback(() => setWsConnected(true), []);
  const handleWsDisconnect = useCallback(() => setWsConnected(false), []);

  useWebSocketV4(activeSessionId, {
    onTaskEvent: handleTaskEvent,
    onChatResponse: handleChatResponse,
    onConnect: handleWsConnect,
    onDisconnect: handleWsDisconnect,
  });

  // Navigation
  const handleSelectCapability = useCallback((capability: CapabilityType) => {
    setSelectedCapability(capability);
    setViewState('form');
  }, []);

  const handleGoHome = useCallback(() => {
    setViewState('home');
    setSelectedCapability(null);
    setActiveSession(null);
  }, []);

  const handleSettings = useCallback(() => {
    setViewState('settings');
    setSelectedCapability(null);
    setActiveSession(null);
  }, []);

  const handleSelectSession = useCallback(
    (session: V4Session) => {
      setActiveSession(session);
      setCurrentPhase(session.status);
      setConfidence(session.confidence);
      setViewState('session');
      refreshStatus(session.session_id);
    },
    [refreshStatus]
  );

  const handleFormSubmit = useCallback(
    async (data: CapabilityFormData) => {
      try {
        // For troubleshoot_app, use the existing V4 API
        if (data.capability === 'troubleshoot_app') {
          const session = await startSessionV4({
            service_name: data.service_name,
            time_window: data.time_window,
            trace_id: data.trace_id,
            namespace: data.namespace,
            repo_url: data.repo_url,
          });
          setSessions((prev) => [session, ...prev]);
          setActiveSession(session);
          setCurrentPhase(session.status);
          setConfidence(session.confidence);
          setViewState('session');
          refreshStatus(session.session_id);
        } else {
          // For other capabilities, create a placeholder session
          const placeholderSession: V4Session = {
            session_id: `${data.capability}-${Date.now()}`,
            service_name: data.capability === 'pr_review'
              ? `PR Review`
              : data.capability === 'github_issue_fix'
              ? `Issue Fix`
              : `Cluster Diag`,
            status: 'initial',
            confidence: 0,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          };
          setSessions((prev) => [placeholderSession, ...prev]);
          setActiveSession(placeholderSession);
          setCurrentPhase('initial');
          setConfidence(0);
          setViewState('session');
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Failed to start session';
        setErrorMessage(msg);
        setTimeout(() => setErrorMessage(null), 8000);
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

  return (
    <div className="flex h-screen bg-[#0f2023] text-white">
      {/* Sidebar */}
      <SessionSidebar
        activeSessionId={activeSessionId}
        onSelectSession={handleSelectSession}
        sessions={sessions}
        onSessionsChange={setSessions}
        onNewMission={handleGoHome}
        onSettings={handleSettings}
      />

      {/* Error toast */}
      {errorMessage && (
        <div className="fixed top-4 right-4 z-50 bg-red-900/90 border border-red-500 text-red-100 px-4 py-3 rounded-lg shadow-lg max-w-md">
          <div className="flex items-center gap-2">
            <span className="text-red-400 font-bold">Error</span>
            <button onClick={() => setErrorMessage(null)} className="ml-auto text-red-300 hover:text-white">&times;</button>
          </div>
          <p className="text-sm mt-1">{errorMessage}</p>
        </div>
      )}

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0">
        {viewState === 'home' && (
          <ActionCenter
            onSelectCapability={handleSelectCapability}
            sessions={sessions}
            onSelectSession={handleSelectSession}
          />
        )}

        {viewState === 'settings' && (
          <IntegrationSettings onBack={handleGoHome} />
        )}

        {viewState === 'form' && selectedCapability && (
          <CapabilityForm
            capability={selectedCapability}
            onBack={handleGoHome}
            onSubmit={handleFormSubmit}
          />
        )}

        {viewState === 'session' && activeSession && (
          <>
            {/* Header */}
            <div className="h-12 bg-[#1e2f33]/50 border-b border-[#224349] flex items-center px-4">
              <button
                onClick={handleGoHome}
                className="text-gray-400 hover:text-white text-xs mr-3 transition-colors"
              >
                &larr; Home
              </button>
              <h1 className="text-sm font-semibold text-white">
                {activeSession.service_name}
              </h1>
              <span className="ml-3 text-xs text-gray-500 font-mono">
                {activeSession.session_id.substring(0, 8)}...
              </span>
            </div>

            {/* Main area: Chat + Results */}
            <div className="flex-1 flex overflow-hidden">
              {/* Left: Tab layout */}
              <div className="flex-1 min-w-0">
                <TabLayout
                  chatContent={
                    <ChatTab
                      sessionId={activeSession.session_id}
                      messages={currentChatMessages}
                      onNewMessage={handleNewChatMessage}
                    />
                  }
                  dashboardContent={
                    <DashboardTab sessionId={activeSession.session_id} />
                  }
                  activityContent={
                    <ActivityLogTab
                      sessionId={activeSession.session_id}
                      events={currentTaskEvents}
                    />
                  }
                />
              </div>

              {/* Right: Results Panel */}
              <div className="w-80 border-l border-[#224349] bg-[#0a1a1d]">
                <ResultsPanel sessionId={activeSession.session_id} />
              </div>
            </div>

            {/* Bottom: Progress Bar */}
            <ProgressBar
              phase={currentPhase}
              confidence={confidence}
              tokenUsage={tokenUsage}
              wsConnected={wsConnected}
            />
          </>
        )}
      </div>
    </div>
  );
}

export default App;
