import React from 'react';
import type { V4Session, ChatMessage, TaskEvent, DiagnosticPhase, TokenUsage } from '../../types';
import AISupervisor from './AISupervisor';
import EvidenceStack from './EvidenceStack';
import ContextScope from './ContextScope';
import RemediationProgressBar from './RemediationProgressBar';

interface InvestigationViewProps {
  session: V4Session;
  messages: ChatMessage[];
  events: TaskEvent[];
  onNewMessage: (message: ChatMessage) => void;
  wsConnected: boolean;
  phase: DiagnosticPhase | null;
  confidence: number;
  tokenUsage: TokenUsage[];
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
          <ContextScope session={session} />
        </div>
      </div>

      {/* Bottom: Remediation Progress Bar */}
      <RemediationProgressBar
        phase={phase}
        confidence={confidence}
        tokenUsage={tokenUsage}
        wsConnected={wsConnected}
      />
    </div>
  );
};

export default InvestigationView;
