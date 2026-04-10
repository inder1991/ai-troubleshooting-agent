import { useParams, useNavigate } from 'react-router-dom';
import { useState, useCallback, useRef, useEffect } from 'react';
import type {
  V4Session,
  TaskEvent,
  DiagnosticPhase,
  TokenUsage,
  ChatMessage,
  AttestationGateData,
  CapabilityType,
} from '../types';
import { useWebSocketV4 } from '../hooks/useWebSocket';
import type { ChatStreamEndPayload } from '../hooks/useWebSocket';
import { getSessionStatus, submitAttestation } from '../services/api';
import { useToast } from '../components/Toast/ToastContext';
import { ChatProvider } from '../contexts/ChatContext';
import { CampaignProvider } from '../contexts/CampaignContext';
import ForemanHUD from '../components/Foreman/ForemanHUD';
import InvestigationView from '../components/Investigation/InvestigationView';
import DatabaseWarRoom from '../components/Investigation/DatabaseWarRoom';
import ClusterWarRoom from '../components/ClusterDiagnostic/ClusterWarRoom';
import NetworkWarRoom from '../components/NetworkTroubleshooting/NetworkWarRoom';
import PostMortemDossierView from '../components/Investigation/PostMortemDossierView';
import ErrorBoundary from '../components/ui/ErrorBoundary';
import ErrorBanner from '../components/ui/ErrorBanner';

export default function InvestigationRoute() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const { addToast } = useToast();

  const [session, setSession] = useState<V4Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [taskEvents, setTaskEvents] = useState<TaskEvent[]>([]);
  const [wsConnected, setWsConnected] = useState(false);
  const [currentPhase, setCurrentPhase] = useState<DiagnosticPhase | null>(null);
  const [confidence, setConfidence] = useState(0);
  const [tokenUsage, setTokenUsage] = useState<TokenUsage[]>([]);
  const [attestationGate, setAttestationGate] = useState<AttestationGateData | null>(null);
  const [wsMaxReconnectsHit, setWsMaxReconnectsHit] = useState(false);

  // Fetch session on mount
  useEffect(() => {
    if (!sessionId) return;
    setLoading(true);
    getSessionStatus(sessionId)
      .then((status) => {
        // Backend returns capability in status response (not in TS type yet)
        const capability = (status as unknown as Record<string, unknown>).capability as CapabilityType | undefined;
        setSession({
          session_id: sessionId,
          service_name: status.service_name || 'Investigation',
          status: status.phase,
          confidence: status.confidence,
          created_at: status.created_at,
          updated_at: status.updated_at,
          incident_id: status.incident_id || '',
          capability: capability || 'troubleshoot_app',
        });
        setCurrentPhase(status.phase);
        setConfidence(status.confidence);
        setTokenUsage(status.token_usage);
        setLoading(false);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : 'Session not found');
        setLoading(false);
      });
  }, [sessionId]);

  const refreshStatus = useCallback(async () => {
    if (!sessionId) return;
    try {
      const status = await getSessionStatus(sessionId);
      setCurrentPhase(status.phase);
      setConfidence(status.confidence);
      setTokenUsage(status.token_usage);
    } catch {
      /* silent */
    }
  }, [sessionId]);

  // WebSocket event handler
  const handleTaskEvent = useCallback(
    (event: TaskEvent) => {
      setTaskEvents((prev) => {
        const updated = [...prev, event];
        return updated.length > 500 ? updated.slice(-500) : updated;
      });

      if (event.event_type === 'phase_change' && event.details?.phase) {
        setCurrentPhase(event.details.phase as DiagnosticPhase);
      }
      if (event.event_type === 'summary' && event.details?.confidence != null) {
        setConfidence(event.details.confidence as number);
      }
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
      if (
        ['summary', 'finding', 'phase_change', 'success', 'waiting_for_input'].includes(
          event.event_type,
        )
      ) {
        refreshStatus();
      }
    },
    [refreshStatus],
  );

  // Chat bridging refs
  const chatResponseRef = useRef<((msg: ChatMessage) => void) | null>(null);
  const handleChatResponse = useCallback((message: ChatMessage) => {
    chatResponseRef.current?.(message);
  }, []);

  const streamStartRef = useRef<(() => void) | null>(null);
  const streamAppendRef = useRef<((chunk: string) => void) | null>(null);
  const streamFinishRef = useRef<
    ((full: string, meta?: ChatMessage['metadata']) => void) | null
  >(null);

  const handleChatChunk = useCallback((chunk: string) => {
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
    if (payload.phase) {
      setCurrentPhase(payload.phase as DiagnosticPhase);
      setConfidence(payload.confidence ?? 0);
    }
  }, []);

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

  useWebSocketV4(sessionId ?? null, {
    onTaskEvent: handleTaskEvent,
    onChatResponse: handleChatResponse,
    onChatChunk: handleChatChunk,
    onChatStreamEnd: handleChatStreamEnd,
    onConnect: handleWsConnect,
    onDisconnect: handleWsDisconnect,
    onMaxReconnectsExhausted: handleWsMaxReconnects,
  });

  const handleGoHome = useCallback(() => navigate('/'), [navigate]);
  const handleNavigateToDossier = useCallback(
    () => navigate(`/investigations/${sessionId}/dossier`),
    [navigate, sessionId],
  );

  const handleAttestationDecision = useCallback(
    (decision: string) => {
      if (sessionId && attestationGate) {
        submitAttestation(sessionId, attestationGate.gate_type, decision, 'user').catch((err) => {
          addToast('error', err instanceof Error ? err.message : 'Failed to submit attestation');
        });
      }
      setAttestationGate(null);
    },
    [sessionId, attestationGate, addToast],
  );

  // Loading state
  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <span className="material-symbols-outlined text-4xl text-slate-500 animate-spin">
          progress_activity
        </span>
      </div>
    );
  }

  // Error / not found state
  if (error || !session) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-4 text-slate-300">
        <span className="material-symbols-outlined text-5xl text-slate-500">error_outline</span>
        <h2 className="text-lg font-display font-bold">Investigation not found</h2>
        <p className="text-sm text-slate-400">
          {error || 'This session does not exist or has expired.'}
        </p>
        <button
          onClick={() => navigate('/investigations')}
          className="px-4 py-2 rounded-lg bg-duck-accent/20 text-duck-accent text-sm font-medium hover:bg-duck-accent/30 transition-colors"
        >
          View all sessions
        </button>
      </div>
    );
  }

  // Render the correct war room based on capability
  if (session.capability === 'cluster_diagnostics') {
    return (
      <ChatProvider
        sessionId={sessionId ?? null}
        events={taskEvents}
        onRegisterChatHandler={chatResponseRef}
        onRegisterStreamStart={streamStartRef}
        onRegisterStreamAppend={streamAppendRef}
        onRegisterStreamFinish={streamFinishRef}
        onPhaseUpdate={handleChatPhaseUpdate}
      >
        <ClusterWarRoom
          session={session}
          events={taskEvents}
          wsConnected={wsConnected}
          phase={currentPhase}
          confidence={confidence}
          onGoHome={handleGoHome}
        />
      </ChatProvider>
    );
  }

  if (session.capability === 'network_troubleshooting') {
    return <NetworkWarRoom session={session} onGoHome={handleGoHome} />;
  }

  // Default: app diagnostics, database diagnostics, PR review, issue fix
  return (
    <ChatProvider
      sessionId={sessionId ?? null}
      events={taskEvents}
      onRegisterChatHandler={chatResponseRef}
      onRegisterStreamStart={streamStartRef}
      onRegisterStreamAppend={streamAppendRef}
      onRegisterStreamFinish={streamFinishRef}
      onPhaseUpdate={handleChatPhaseUpdate}
    >
      <CampaignProvider sessionId={sessionId ?? null}>
        <ForemanHUD
          sessionId={session.session_id}
          serviceName={session.service_name}
          phase={currentPhase}
          confidence={confidence}
          events={taskEvents}
          wsConnected={wsConnected}
          needsInput={false}
          onGoHome={handleGoHome}
          onOpenChat={() => {}}
        />
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
        <div className="flex-1 overflow-hidden">
          <ErrorBoundary>
            {session.capability === 'database_diagnostics' ? (
              <DatabaseWarRoom
                session={session}
                events={taskEvents}
                wsConnected={wsConnected}
                phase={currentPhase}
                confidence={confidence}
              />
            ) : (
              <InvestigationView
                session={session}
                events={taskEvents}
                wsConnected={wsConnected}
                phase={currentPhase}
                confidence={confidence}
                tokenUsage={tokenUsage}
                attestationGate={attestationGate}
                onAttestationDecision={handleAttestationDecision}
                onNavigateToDossier={handleNavigateToDossier}
              />
            )}
          </ErrorBoundary>
        </div>
      </CampaignProvider>
    </ChatProvider>
  );
}

export function DossierRoute() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();

  if (!sessionId) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-4 text-slate-300">
        <span className="material-symbols-outlined text-5xl text-slate-500">error_outline</span>
        <h2 className="text-lg font-display font-bold">Dossier not found</h2>
        <button
          onClick={() => navigate('/investigations')}
          className="px-4 py-2 rounded-lg bg-duck-accent/20 text-duck-accent text-sm font-medium hover:bg-duck-accent/30 transition-colors"
        >
          View all sessions
        </button>
      </div>
    );
  }

  return (
    <PostMortemDossierView
      sessionId={sessionId}
      onBack={() => navigate(`/investigations/${sessionId}`)}
    />
  );
}
