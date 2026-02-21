import React from 'react';
import type { V4Session, ChatMessage, TaskEvent, DiagnosticPhase, TokenUsage, AttestationGateData } from '../../types';
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
          />
        </div>

        {/* Center: Evidence and Findings (NO TABS) */}
        <div className="col-span-5 overflow-hidden">
          <EvidenceFindings sessionId={session.session_id} events={events} />
        </div>

        {/* Right: The Navigator */}
        <div className="col-span-4 border-l border-slate-800 overflow-hidden">
          <Navigator sessionId={session.session_id} events={events} />
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
