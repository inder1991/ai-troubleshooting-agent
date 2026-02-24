import React, { useState, useEffect, useCallback, useRef } from 'react';
import type { V4Session, V4Findings, V4SessionStatus, ChatMessage, TaskEvent, DiagnosticPhase, TokenUsage, AttestationGateData } from '../../types';
import { getFindings, getSessionStatus, sendChatMessage } from '../../services/api';
import { useChatContext } from '../../contexts/ChatContext';
import { useCampaignContext } from '../../contexts/CampaignContext';
import Investigator from './Investigator';
import EvidenceFindings from './EvidenceFindings';
import Navigator from './Navigator';
import RemediationProgressBar from './RemediationProgressBar';
import AttestationGateUI from '../Remediation/AttestationGateUI';
import ErrorBanner from '../ui/ErrorBanner';
import ChatDrawer from '../Chat/ChatDrawer';
import LedgerTriggerTab from '../Chat/LedgerTriggerTab';
import SurgicalTelescope from './SurgicalTelescope';
import { TopologySelectionProvider } from '../../contexts/TopologySelectionContext';

interface InvestigationViewProps {
  session: V4Session;
  events: TaskEvent[];
  wsConnected: boolean;
  phase: DiagnosticPhase | null;
  confidence: number;
  tokenUsage: TokenUsage[];
  attestationGate?: AttestationGateData | null;
  onAttestationDecision?: (decision: string) => void;
}

const InvestigationView: React.FC<InvestigationViewProps> = ({
  session,
  events,
  wsConnected,
  phase,
  confidence,
  tokenUsage,
  attestationGate,
  onAttestationDecision,
}) => {
  // ── Single source of truth for findings + status ──────────────────────
  const [findings, setFindings] = useState<V4Findings | null>(null);
  const [sessionStatus, setSessionStatus] = useState<V4SessionStatus | null>(null);
  const [fetchFailCount, setFetchFailCount] = useState(0);
  const [fetchErrorDismissed, setFetchErrorDismissed] = useState(false);
  const [lastFetchTime, setLastFetchTime] = useState<number | null>(null);
  const [lastFetchAgo, setLastFetchAgo] = useState(0);
  const agoIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Chat state now managed by ChatContext
  const { addMessage: onNewMessage } = useChatContext();
  const { setCampaign } = useCampaignContext();

  // Sync campaign data from findings into CampaignContext
  useEffect(() => {
    if (findings?.campaign) {
      setCampaign(findings.campaign);
    }
  }, [findings?.campaign, setCampaign]);

  // Tick "last updated X s ago" every second
  useEffect(() => {
    agoIntervalRef.current = setInterval(() => {
      if (lastFetchTime) setLastFetchAgo(Math.floor((Date.now() - lastFetchTime) / 1000));
    }, 1000);
    return () => { if (agoIntervalRef.current) clearInterval(agoIntervalRef.current); };
  }, [lastFetchTime]);

  const fetchSharedData = useCallback(async () => {
    try {
      const [f, s] = await Promise.all([
        getFindings(session.session_id),
        getSessionStatus(session.session_id),
      ]);
      setFindings(f);
      setSessionStatus(s);
      setFetchFailCount(0);
      setFetchErrorDismissed(false);
      setLastFetchTime(Date.now());
    } catch {
      setFetchFailCount((c) => c + 1);
    }
  }, [session.session_id]);

  // Poll every 5s
  useEffect(() => {
    fetchSharedData();
    const interval = setInterval(fetchSharedData, 5000);
    return () => clearInterval(interval);
  }, [fetchSharedData]);

  // Also re-fetch on relevant WebSocket events (debounced — only on new events)
  const relevantEventCount = events.filter(
    (e) => e.event_type === 'summary' || e.event_type === 'finding' || e.event_type === 'phase_change'
  ).length;
  const prevRelevantCountRef = useRef(0);
  useEffect(() => {
    if (relevantEventCount > prevRelevantCountRef.current) {
      prevRelevantCountRef.current = relevantEventCount;
      fetchSharedData();
    }
  }, [relevantEventCount, fetchSharedData]);

  // Freshness indicator color
  const freshnessColor = lastFetchAgo <= 10 ? 'bg-green-500' : lastFetchAgo <= 30 ? 'bg-amber-500' : 'bg-red-500';

  // Attach repo handler — sends "confirm" through chat
  const handleAttachRepo = useCallback(() => {
    if (!session.session_id) return;
    const userMsg: ChatMessage = { role: 'user', content: 'confirm', timestamp: new Date().toISOString() };
    onNewMessage(userMsg);
    sendChatMessage(session.session_id, 'confirm').then((resp) => {
      if (resp?.content) onNewMessage(resp);
    }).catch(() => {});
  }, [session.session_id, onNewMessage]);

  return (
    <div className="flex flex-col h-full">
      {/* Fetch failure banner */}
      {fetchFailCount >= 3 && !fetchErrorDismissed && (
        <div className="px-4 pt-2">
          <ErrorBanner
            message={`Connection issue — data may be stale (${fetchFailCount} failed attempts)`}
            severity="warning"
            onDismiss={() => setFetchErrorDismissed(true)}
            onRetry={fetchSharedData}
          />
        </div>
      )}

      {/* Last updated indicator */}
      {lastFetchTime && (
        <div className="flex items-center gap-1.5 px-6 py-1 text-[9px] text-slate-500">
          <span className={`w-1.5 h-1.5 rounded-full ${freshnessColor}`} />
          <span>Updated {lastFetchAgo}s ago</span>
        </div>
      )}

      {/* War Room: 3-column CSS Grid layout */}
      <TopologySelectionProvider>
        <div className="grid grid-cols-12 flex-1 overflow-hidden">
          {/* Left: The Investigator (AI reasoning only — no chat) */}
          <div className="col-span-3 border-r border-slate-800 overflow-hidden">
            <Investigator
              sessionId={session.session_id}
              events={events}
              wsConnected={wsConnected}
              findings={findings}
              status={sessionStatus}
              onAttachRepo={handleAttachRepo}
            />
          </div>

          {/* Center: Evidence and Findings (NO TABS) */}
          <div className="col-span-5 overflow-hidden">
            <EvidenceFindings findings={findings} status={sessionStatus} events={events} sessionId={session.session_id} phase={phase} onRefresh={fetchSharedData} />
          </div>

          {/* Right: The Navigator */}
          <div className="col-span-4 border-l border-slate-800 overflow-hidden">
            <Navigator findings={findings} status={sessionStatus} events={events} />
          </div>
        </div>
      </TopologySelectionProvider>

      {/* Surgical Telescope overlay (rendered outside grid) */}
      <SurgicalTelescope />

      {/* Bottom: Remediation Progress Bar */}
      <RemediationProgressBar
        phase={phase}
        confidence={confidence}
        tokenUsage={tokenUsage}
        wsConnected={wsConnected}
      />

      {/* Attestation Gate Modal */}
      {attestationGate && onAttestationDecision && (
        <AttestationGateUI
          gate={attestationGate}
          evidencePins={[]}
          onDecision={(decision, _notes) => onAttestationDecision(decision)}
          onClose={() => onAttestationDecision('dismiss')}
        />
      )}

      {/* Chat Drawer + Trigger Tab (self-contained via ChatContext) */}
      <ChatDrawer />
      <LedgerTriggerTab />
    </div>
  );
};

export default InvestigationView;
