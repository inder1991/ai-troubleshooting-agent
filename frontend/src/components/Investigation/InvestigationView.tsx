import React from 'react';
import type { V4Session, ChatMessage, TaskEvent, DiagnosticPhase, TokenUsage, AttestationGateData } from '../../types';
import AISupervisor from './AISupervisor';
import EvidenceStack from './EvidenceStack';
import ContextScope from './ContextScope';
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
  return (
    <div className="flex flex-col h-full">
      {/* 3-column layout */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: AI Supervisor with log feed */}
        <div className="w-[380px] flex-shrink-0">
          <AISupervisor
            sessionId={session.session_id}
            messages={messages}
            events={events}
            onNewMessage={onNewMessage}
            wsConnected={wsConnected}
          />
        </div>

        {/* Center: Evidence Stack */}
        <div className="flex-1 min-w-0">
          <EvidenceStack sessionId={session.session_id} events={events} />
        </div>

        {/* Right: Context Scope */}
        <div className="w-[320px] flex-shrink-0">
          <ContextScope session={session} events={events} />
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
