import React, { useState, useEffect, useCallback } from 'react';
import type { V4Session, V4Findings, V4SessionStatus, ChatMessage, TaskEvent, DiagnosticPhase, TokenUsage, AttestationGateData } from '../../types';
import { getFindings, getSessionStatus } from '../../services/api';
import Investigator from './Investigator';
import EvidenceFindings from './EvidenceFindings';
import Navigator from './Navigator';
import RemediationProgressBar from './RemediationProgressBar';
import AttestationGateUI from '../Remediation/AttestationGateUI';

interface InvestigationViewProps {
  session: V4Session;
  messages: ChatMessage[];
  events: TaskEvent[];
  onNewMessage: (message: ChatMessage) => void;
  wsConnected: boolean;
  phase: DiagnosticPhase | null;
  confidence: number;
  tokenUsage: TokenUsage[];
  attestationGate?: AttestationGateData | null;
  onAttestationDecision?: (decision: string) => void;
}

const InvestigationView: React.FC<InvestigationViewProps> = ({
  session,
  messages,
  events,
  onNewMessage,
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

  const fetchSharedData = useCallback(async () => {
    try {
      const [f, s] = await Promise.all([
        getFindings(session.session_id),
        getSessionStatus(session.session_id),
      ]);
      setFindings(f);
      setSessionStatus(s);
    } catch {
      // silent — keep previous state
    }
  }, [session.session_id]);

  // Poll every 5s
  useEffect(() => {
    fetchSharedData();
    const interval = setInterval(fetchSharedData, 5000);
    return () => clearInterval(interval);
  }, [fetchSharedData]);

  // Also re-fetch immediately on relevant WebSocket events
  const relevantEventCount = events.filter(
    (e) => e.event_type === 'summary' || e.event_type === 'finding' || e.event_type === 'phase_change'
  ).length;
  useEffect(() => {
    if (relevantEventCount > 0) fetchSharedData();
  }, [relevantEventCount, fetchSharedData]);

  return (
    <div className="flex flex-col h-full">
      {/* War Room: 3-column CSS Grid layout */}
      <div className="grid grid-cols-12 flex-1 overflow-hidden">
        {/* Left: The Investigator */}
        <div className="col-span-3 border-r border-slate-800 overflow-hidden">
          <Investigator
            sessionId={session.session_id}
            messages={messages}
            events={events}
            onNewMessage={onNewMessage}
            wsConnected={wsConnected}
            findings={findings}
            status={sessionStatus}
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
    </div>
  );
};

export default InvestigationView;
