import React, { useState, useCallback } from 'react';
import type {
  V4Session,
  ChatMessage,
  TaskEvent,
  DiagnosticPhase,
  TokenUsage,
} from './types';
import { useWebSocketV4 } from './hooks/useWebSocket';
import { getSessionStatus } from './services/api';
import SessionSidebar from './components/SessionSidebar';
import TabLayout from './components/TabLayout';
import StatusBar from './components/StatusBar';
import ChatTab from './components/Chat/ChatTab';
import DashboardTab from './components/Dashboard/DashboardTab';
import ActivityLogTab from './components/ActivityLog/ActivityLogTab';

function App() {
  const [sessions, setSessions] = useState<V4Session[]>([]);
  const [activeSession, setActiveSession] = useState<V4Session | null>(null);
  const [chatMessages, setChatMessages] = useState<Record<string, ChatMessage[]>>({});
  const [taskEvents, setTaskEvents] = useState<Record<string, TaskEvent[]>>({});
  const [wsConnected, setWsConnected] = useState(false);
  const [currentPhase, setCurrentPhase] = useState<DiagnosticPhase | null>(null);
  const [confidence, setConfidence] = useState(0);
  const [tokenUsage, setTokenUsage] = useState<TokenUsage[]>([]);

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

      // Refresh status on meaningful events
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

  const handleWsConnect = useCallback(() => {
    setWsConnected(true);
  }, []);

  const handleWsDisconnect = useCallback(() => {
    setWsConnected(false);
  }, []);

  // Connect WebSocket for active session
  useWebSocketV4(activeSessionId, {
    onTaskEvent: handleTaskEvent,
    onChatResponse: handleChatResponse,
    onConnect: handleWsConnect,
    onDisconnect: handleWsDisconnect,
  });

  const handleSelectSession = useCallback(
    (session: V4Session) => {
      setActiveSession(session);
      setCurrentPhase(session.status);
      setConfidence(session.confidence);
      // Fetch full status for the selected session
      refreshStatus(session.session_id);
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

  const currentChatMessages = activeSessionId
    ? chatMessages[activeSessionId] || []
    : [];
  const currentTaskEvents = activeSessionId
    ? taskEvents[activeSessionId] || []
    : [];

  return (
    <div className="flex h-screen bg-gray-950 text-white">
      {/* Sidebar */}
      <SessionSidebar
        activeSessionId={activeSessionId}
        onSelectSession={handleSelectSession}
        sessions={sessions}
        onSessionsChange={setSessions}
      />

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0">
        {activeSession ? (
          <>
            {/* Header */}
            <div className="h-12 bg-gray-900 border-b border-gray-700 flex items-center px-4">
              <h1 className="text-sm font-semibold text-white">
                {activeSession.service_name}
              </h1>
              <span className="ml-3 text-xs text-gray-500 font-mono">
                {activeSession.session_id.substring(0, 8)}...
              </span>
            </div>

            {/* Tab layout */}
            <div className="flex-1 overflow-hidden">
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

            {/* Status bar */}
            <StatusBar
              phase={currentPhase}
              confidence={confidence}
              tokenUsage={tokenUsage}
              wsConnected={wsConnected}
            />
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center text-gray-500">
            <div className="text-center">
              <h2 className="text-2xl font-semibold text-gray-400 mb-2">
                AI SRE Troubleshooting System
              </h2>
              <p className="text-sm">
                Select an existing session or start a new one from the sidebar.
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
