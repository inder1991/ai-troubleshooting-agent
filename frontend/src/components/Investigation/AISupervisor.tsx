import React, { useState, useRef, useEffect, useMemo } from 'react';
import type { ChatMessage as ChatMessageType, TaskEvent, V4Findings, PatientZero, InferredDependency, ReasoningChainStep } from '../../types';
import { sendChatMessage, getFindings } from '../../services/api';

interface AISupervisorProps {
  sessionId: string;
  messages: ChatMessageType[];
  events: TaskEvent[];
  onNewMessage: (message: ChatMessageType) => void;
  wsConnected: boolean;
}

// Severity colors for finding cards
const severityStyles: Record<string, { border: string; bg: string; text: string; icon: string }> = {
  critical: { border: 'border-red-500/40', bg: 'bg-red-500/10', text: 'text-red-400', icon: 'error' },
  high: { border: 'border-orange-500/40', bg: 'bg-orange-500/10', text: 'text-orange-400', icon: 'warning' },
  medium: { border: 'border-yellow-500/40', bg: 'bg-yellow-500/10', text: 'text-yellow-400', icon: 'info' },
  low: { border: 'border-blue-500/40', bg: 'bg-blue-500/10', text: 'text-blue-400', icon: 'help' },
};

// Group consecutive tool_call events from the same agent
interface ToolCallGroup {
  kind: 'tool_group';
  agent: string;
  events: TaskEvent[];
  ts: number;
}

type TimelineItem =
  | { kind: 'chat'; msg: ChatMessageType; ts: number }
  | { kind: 'event'; event: TaskEvent; ts: number }
  | ToolCallGroup;

function buildTimeline(messages: ChatMessageType[], events: TaskEvent[], showToolCalls: boolean): TimelineItem[] {
  // First, build event items — group consecutive tool_calls from the same agent
  const eventItems: TimelineItem[] = [];
  let i = 0;
  while (i < events.length) {
    const ev = events[i];
    if (ev.event_type === 'tool_call') {
      // Collect consecutive tool_call events from the same agent
      const group: TaskEvent[] = [ev];
      let j = i + 1;
      while (j < events.length && events[j].event_type === 'tool_call' && events[j].agent_name === ev.agent_name) {
        group.push(events[j]);
        j++;
      }
      if (showToolCalls) {
        eventItems.push({
          kind: 'tool_group',
          agent: ev.agent_name,
          events: group,
          ts: new Date(ev.timestamp).getTime(),
        });
      }
      i = j;
    } else {
      eventItems.push({ kind: 'event', event: ev, ts: new Date(ev.timestamp).getTime() });
      i++;
    }
  }

  const chatItems: TimelineItem[] = messages.map((msg) => ({
    kind: 'chat' as const,
    msg,
    ts: new Date(msg.timestamp).getTime(),
  }));

  return [...chatItems, ...eventItems].sort((a, b) => a.ts - b.ts);
}

const AISupervisor: React.FC<AISupervisorProps> = ({
  sessionId,
  messages,
  events,
  onNewMessage,
  wsConnected,
}) => {
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [showToolCalls, setShowToolCalls] = useState(false);
  const [findings, setFindings] = useState<V4Findings | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Fetch findings when summary events arrive (agent completed)
  const summaryCount = events.filter(e => e.event_type === 'summary').length;
  useEffect(() => {
    if (summaryCount > 0) {
      getFindings(sessionId).then(setFindings).catch(() => {});
    }
  }, [sessionId, summaryCount]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, events, findings]);

  useEffect(() => {
    inputRef.current?.focus();
  }, [sessionId]);

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || sending) return;

    const userMessage: ChatMessageType = {
      role: 'user',
      content: trimmed,
      timestamp: new Date().toISOString(),
    };
    onNewMessage(userMessage);
    setInput('');
    setSending(true);

    try {
      const response = await sendChatMessage(sessionId, trimmed);
      if (response && response.content) {
        onNewMessage(response);
      }
    } catch (err) {
      onNewMessage({
        role: 'assistant',
        content: `Error: ${err instanceof Error ? err.message : 'Failed to send message'}`,
        timestamp: new Date().toISOString(),
      });
    } finally {
      setSending(false);
    }
  };

  const timeline = useMemo(
    () => buildTimeline(messages, events, showToolCalls),
    [messages, events, showToolCalls]
  );

  // Count tool call events for the toggle badge
  const toolCallCount = events.filter((e) => e.event_type === 'tool_call').length;

  return (
    <div className="flex flex-col h-full bg-slate-900/20 border-r border-[#07b6d5]/10">
      {/* Header */}
      <div className="p-4 border-b border-primary/10 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-primary text-sm" style={{ fontFamily: 'Material Symbols Outlined' }}>psychology</span>
          <h2 className="text-xs font-bold uppercase tracking-widest text-slate-400">AI Supervisor</h2>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowToolCalls(!showToolCalls)}
            className={`text-[10px] px-2 py-0.5 rounded border font-mono transition-colors ${
              showToolCalls
                ? 'bg-purple-500/20 text-purple-400 border-purple-500/30'
                : 'bg-slate-800/50 text-slate-500 border-slate-700'
            }`}
          >
            {showToolCalls ? 'TOOLS ON' : 'TOOLS OFF'}
            {toolCallCount > 0 && (
              <span className="ml-1 text-[9px] opacity-60">({toolCallCount})</span>
            )}
          </button>
        </div>
      </div>

      {/* Scrollable content */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-2 custom-scrollbar">
        {timeline.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-slate-500">
            <p className="text-sm">Waiting for investigation to begin...</p>
            <p className="text-[10px] mt-1">Agent events will stream here in real-time</p>
          </div>
        ) : (
          timeline.map((item, idx) => {
            if (item.kind === 'chat') {
              return <ChatBubble key={`chat-${idx}`} message={item.msg} />;
            }
            if (item.kind === 'tool_group') {
              return <ToolCallGroupCard key={`tg-${idx}`} group={item} />;
            }
            return <EventCard key={`ev-${idx}`} event={item.event} />;
          })
        )}

        {sending && (
          <div className="flex justify-start">
            <div className="bg-[#07b6d5]/5 border border-[#07b6d5]/10 rounded-xl px-3 py-2">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 bg-[#07b6d5] rounded-full animate-pulse" />
                <span className="text-xs text-slate-400">Thinking...</span>
              </div>
            </div>
          </div>
        )}

        {/* AI Analysis Section — appears after log_agent completes */}
        {findings?.patient_zero && <PatientZeroCard patientZero={findings.patient_zero} />}
        {(findings?.reasoning_chain?.length ?? 0) > 0 && <ReasoningChainCard chain={findings!.reasoning_chain} />}
        {(findings?.inferred_dependencies?.length ?? 0) > 0 && <InferredDependenciesCard deps={findings!.inferred_dependencies} targetService={findings?.target_service} />}
      </div>

      {/* Chat Input */}
      <div className="p-4 border-t border-primary/10 bg-slate-900/40">
        <form onSubmit={handleSend} className="relative">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSend(e);
              }
            }}
            placeholder="Ask supervisor for data analysis..."
            disabled={sending}
            className="w-full bg-slate-800/50 border border-slate-700 rounded-lg py-2 px-3 text-xs focus:ring-1 focus:ring-primary focus:border-primary outline-none resize-none h-20 placeholder:text-slate-600 disabled:opacity-50 text-white custom-scrollbar"
          />
          <button
            type="submit"
            disabled={sending || !input.trim()}
            className="absolute bottom-2 right-2 p-1.5 bg-primary rounded-md text-white disabled:opacity-30 disabled:cursor-not-allowed hover:bg-primary/80 transition-colors"
          >
            <span className="material-symbols-outlined text-sm" style={{ fontFamily: 'Material Symbols Outlined' }}>send</span>
          </button>
        </form>
      </div>
    </div>
  );
};

// ─── Event Card (type-specific rendering) ─────────────────────────────────

const EventCard: React.FC<{ event: TaskEvent }> = ({ event }) => {
  switch (event.event_type) {
    case 'phase_change':
      return <PhaseChangeCard event={event} />;
    case 'finding':
      return <FindingCard event={event} />;
    case 'summary':
      return <SummaryCard event={event} />;
    case 'started':
      return <StartedCard event={event} />;
    case 'warning':
      return <AlertCard event={event} variant="warning" />;
    case 'error':
      return <AlertCard event={event} variant="error" />;
    case 'success':
      return <SuccessCard event={event} />;
    case 'attestation_required':
      return <AttestationRequiredCard event={event} />;
    default:
      return <GenericLogEntry event={event} />;
  }
};

// ─── Phase Change Divider ─────────────────────────────────────────────────

const PhaseChangeCard: React.FC<{ event: TaskEvent }> = ({ event }) => {
  const phaseName = event.details?.phase
    ? String(event.details.phase).replace(/_/g, ' ').toUpperCase()
    : event.message.toUpperCase();

  return (
    <div className="flex items-center gap-3 py-2">
      <div className="flex-1 h-px bg-gradient-to-r from-transparent via-[#07b6d5]/40 to-transparent" />
      <span className="text-[10px] font-bold tracking-[0.2em] text-[#07b6d5]">
        {phaseName}
      </span>
      <div className="flex-1 h-px bg-gradient-to-r from-transparent via-[#07b6d5]/40 to-transparent" />
    </div>
  );
};

// ─── Finding Discovery Card ───────────────────────────────────────────────

const FindingCard: React.FC<{ event: TaskEvent }> = ({ event }) => {
  const severity = String(event.details?.severity || 'medium');
  const confidence = Number(event.details?.confidence || 0);
  const category = String(event.details?.category || '');
  const style = severityStyles[severity] || severityStyles.medium;
  const defaultExpanded = severity === 'critical' || severity === 'high';
  const [expanded, setExpanded] = useState(defaultExpanded);

  return (
    <div className={`border rounded-lg overflow-hidden ${style.border} ${style.bg}`}>
      {/* L1: Always visible — severity + title */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full px-3 py-2.5 text-left flex items-center gap-2"
        aria-expanded={expanded}
      >
        <span
          className={`material-symbols-outlined text-xs text-slate-400 transition-transform ${expanded ? 'rotate-90' : ''}`}
          style={{ fontFamily: 'Material Symbols Outlined' }}
        >
          chevron_right
        </span>
        <span
          className={`material-symbols-outlined text-sm ${style.text}`}
          style={{ fontFamily: 'Material Symbols Outlined' }}
        >
          {style.icon}
        </span>
        <span className={`text-[10px] font-bold uppercase tracking-wider ${style.text}`}>
          {severity}
        </span>
        <span className="text-xs text-slate-200 truncate flex-1">{event.message.split(' — ')[0]}</span>
        {confidence > 0 && (
          <span className="text-[10px] text-slate-400 shrink-0">{confidence}%</span>
        )}
      </button>
      {/* L2: Expandable details */}
      {expanded && (
        <div className="px-3 pb-3 border-t border-black/10 pt-2">
          <p className="text-sm text-slate-200 leading-snug">{event.message}</p>
          {category && (
            <span className="text-[10px] font-mono text-slate-400 mt-1 inline-block">{category}</span>
          )}
          {confidence > 0 && (
            <div className="flex items-center gap-2 mt-2">
              <div className="flex-1 h-1 bg-black/20 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full ${style.text.replace('text-', 'bg-')}`}
                  style={{ width: `${confidence}%` }}
                />
              </div>
              <span className="text-[10px] text-slate-400">{confidence}%</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// ─── Agent Summary Banner ─────────────────────────────────────────────────

const SummaryCard: React.FC<{ event: TaskEvent }> = ({ event }) => {
  const confidence = Number(event.details?.confidence || 0);
  const findingsCount = Number(event.details?.findings_count || 0);
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="bg-[#07b6d5]/5 border border-[#07b6d5]/20 rounded-lg overflow-hidden">
      {/* L1: Agent name + confidence badge */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full px-3 py-2.5 text-left flex items-center gap-2"
        aria-expanded={expanded}
      >
        <span
          className={`material-symbols-outlined text-xs text-slate-400 transition-transform ${expanded ? 'rotate-90' : ''}`}
          style={{ fontFamily: 'Material Symbols Outlined' }}
        >
          chevron_right
        </span>
        <span
          className="material-symbols-outlined text-[#07b6d5] text-sm"
          style={{ fontFamily: 'Material Symbols Outlined' }}
        >
          check_circle
        </span>
        <span className="text-[10px] font-bold uppercase tracking-wider text-[#07b6d5]">
          {event.agent_name.replace(/_/g, ' ')}
        </span>
        <div className="ml-auto flex items-center gap-2">
          {findingsCount > 0 && (
            <span className="text-[10px] px-1.5 py-0.5 bg-[#07b6d5]/20 text-[#07b6d5] rounded">
              {findingsCount} findings
            </span>
          )}
          <span className={`text-[10px] font-mono font-bold ${
            confidence >= 70 ? 'text-green-400' : confidence >= 40 ? 'text-amber-400' : 'text-red-400'
          }`}>
            {confidence}%
          </span>
        </div>
      </button>
      {/* L2: Full message on expand */}
      {expanded && (
        <div className="px-3 pb-3 border-t border-[#07b6d5]/10 pt-2">
          <p className="text-xs text-slate-300 leading-relaxed">{event.message}</p>
        </div>
      )}
    </div>
  );
};

// ─── Started Card ─────────────────────────────────────────────────────────

const StartedCard: React.FC<{ event: TaskEvent }> = ({ event }) => (
  <div className="flex items-center gap-2 py-1">
    <div className="w-6 h-6 rounded-md bg-blue-500/20 flex items-center justify-center">
      <span
        className="material-symbols-outlined text-blue-400 text-xs"
        style={{ fontFamily: 'Material Symbols Outlined' }}
      >
        play_circle
      </span>
    </div>
    <span className="text-xs text-blue-400">{event.agent_name}</span>
    <span className="text-xs text-slate-400">{event.message}</span>
    <span className="text-[10px] text-slate-600 ml-auto">
      {new Date(event.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
    </span>
  </div>
);

// ─── Warning / Error Alert Card ───────────────────────────────────────────

const AlertCard: React.FC<{ event: TaskEvent; variant: 'warning' | 'error' }> = ({ event, variant }) => {
  const isError = variant === 'error';
  return (
    <div className={`border rounded-lg px-3 py-2 ${
      isError ? 'border-red-500/30 bg-red-500/10' : 'border-amber-500/30 bg-amber-500/10'
    }`}>
      <div className="flex items-center gap-2">
        <span
          className={`material-symbols-outlined text-sm ${isError ? 'text-red-400' : 'text-amber-400'}`}
          style={{ fontFamily: 'Material Symbols Outlined' }}
        >
          {isError ? 'error' : 'warning'}
        </span>
        <span className={`text-[10px] font-bold uppercase ${isError ? 'text-red-400' : 'text-amber-400'}`}>
          {event.agent_name}
        </span>
        <span className="text-[10px] text-slate-600 ml-auto">
          {new Date(event.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
        </span>
      </div>
      <p className="text-xs text-slate-300 mt-1">{event.message}</p>
    </div>
  );
};

// ─── Success Card ─────────────────────────────────────────────────────────

const SuccessCard: React.FC<{ event: TaskEvent }> = ({ event }) => (
  <div className="flex items-center gap-2 py-1">
    <span
      className="material-symbols-outlined text-green-400 text-sm"
      style={{ fontFamily: 'Material Symbols Outlined' }}
    >
      check_circle
    </span>
    <span className="text-xs text-green-400">{event.agent_name}</span>
    <span className="text-xs text-slate-400">{event.message}</span>
  </div>
);

// ─── Collapsible Tool Call Group ──────────────────────────────────────────

const ToolCallGroupCard: React.FC<{ group: ToolCallGroup }> = ({ group }) => {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border border-slate-800/50 rounded-lg overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
        className="w-full flex items-center gap-2 px-3 py-1.5 text-left hover:bg-slate-800/30 transition-colors"
      >
        <span
          className={`material-symbols-outlined text-xs text-purple-400 transition-transform ${expanded ? 'rotate-90' : ''}`}
          style={{ fontFamily: 'Material Symbols Outlined' }}
        >
          chevron_right
        </span>
        <span className="text-[10px] font-bold text-purple-400 uppercase">
          {group.agent.replace(/_/g, ' ')}
        </span>
        <span className="text-[10px] text-slate-500">
          — {group.events.length} tool call{group.events.length !== 1 ? 's' : ''}
        </span>
      </button>
      {expanded && (
        <div className="px-3 py-2 border-t border-slate-800/30 space-y-1 bg-slate-900/20">
          {group.events.map((ev, i) => (
            <div key={i} className="flex items-start gap-2 font-mono text-[11px]">
              <span className="text-slate-600 shrink-0 w-[60px]">
                {new Date(ev.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
              </span>
              <span className="text-slate-400">{ev.message}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// ─── Attestation Required Card ───────────────────────────────────────────

const AttestationRequiredCard: React.FC<{ event: TaskEvent }> = ({ event }) => {
  const [expanded, setExpanded] = useState(true);
  const findingsCount = Number(event.details?.findings_count || 0);
  const confidence = Number(event.details?.confidence || 0);
  const proposedAction = String(event.details?.proposed_action || 'Proceed to remediation');

  return (
    <div className="border-2 border-amber-500/40 bg-amber-500/10 rounded-lg overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full px-3 py-2.5 text-left flex items-center gap-2"
        aria-expanded={expanded}
      >
        <span
          className={`material-symbols-outlined text-xs text-amber-400 transition-transform ${expanded ? 'rotate-90' : ''}`}
          style={{ fontFamily: 'Material Symbols Outlined' }}
        >
          chevron_right
        </span>
        <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
        <span className="text-[10px] font-bold uppercase tracking-wider text-amber-400">
          Action Required
        </span>
        <span className="text-xs text-amber-300 ml-1">Human Review Needed</span>
      </button>
      {expanded && (
        <div className="px-3 pb-3 border-t border-amber-500/20 pt-2 space-y-2">
          <p className="text-sm text-slate-200">{event.message}</p>
          <div className="flex items-center gap-4 text-[10px] text-slate-400">
            <span>{findingsCount} findings</span>
            <span>Confidence: {confidence}%</span>
          </div>
          <div className="text-[10px] text-slate-500">
            Proposed: {proposedAction}
          </div>
        </div>
      )}
    </div>
  );
};

// ─── Generic Log Entry (fallback for progress, etc.) ──────────────────────

const GenericLogEntry: React.FC<{ event: TaskEvent }> = ({ event }) => (
  <div className="font-mono text-[11px] flex items-start gap-2 py-0.5">
    <span
      className="material-symbols-outlined text-[14px] mt-0.5 text-slate-500"
      style={{ fontFamily: 'Material Symbols Outlined' }}
    >
      search
    </span>
    <span className="text-slate-600 shrink-0 w-[60px]">
      {new Date(event.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
    </span>
    <span className="text-[#07b6d5] shrink-0">{event.agent_name}</span>
    <span className="text-slate-400 truncate">{event.message}</span>
  </div>
);

// ─── Chat Bubble ──────────────────────────────────────────────────────────

const ChatBubble: React.FC<{ message: ChatMessageType }> = ({ message }) => {
  if (message.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] bg-slate-800/60 border border-slate-700 rounded-xl px-3 py-2">
          <p className="text-sm text-slate-200 whitespace-pre-wrap">{message.content}</p>
          <p className="text-[10px] text-slate-600 mt-1 text-right">
            {new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex items-start gap-3">
        <div className="w-8 h-8 rounded-lg bg-[#07b6d5]/20 flex items-center justify-center shrink-0">
          <span className="material-symbols-outlined text-primary text-sm" style={{ fontFamily: 'Material Symbols Outlined' }}>smart_toy</span>
        </div>
        <div className="flex-1">
          <div className="bg-[#07b6d5]/5 border border-[#07b6d5]/10 rounded-xl p-3 text-sm leading-relaxed text-slate-300">
            <p className="whitespace-pre-wrap">{message.content}</p>
          </div>
          <p className="text-[10px] text-slate-600 mt-1">
            {new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
          </p>
        </div>
      </div>
    </div>
  );
};

// ─── Patient Zero Card ────────────────────────────────────────────────────

const PatientZeroCard: React.FC<{ patientZero: PatientZero }> = ({ patientZero }) => (
  <div className="border-2 border-red-500/30 bg-red-500/5 rounded-lg p-3">
    <div className="flex items-center gap-2 mb-2">
      <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
      <span className="text-[10px] font-bold uppercase tracking-wider text-red-400">Patient Zero</span>
    </div>
    <div className="text-xs font-mono text-red-300 font-bold mb-1">{patientZero.service}</div>
    <p className="text-[10px] text-slate-400">{patientZero.evidence}</p>
    {patientZero.first_error_time && (
      <div className="text-[10px] text-slate-500 mt-1">
        First error: {new Date(patientZero.first_error_time).toLocaleString()}
      </div>
    )}
  </div>
);

// ─── Reasoning Chain Card ─────────────────────────────────────────────────

const ReasoningChainCard: React.FC<{ chain: ReasoningChainStep[] }> = ({ chain }) => {
  if (!chain.length) return null;
  return (
    <div className="bg-[#07b6d5]/5 border border-[#07b6d5]/15 rounded-lg overflow-hidden">
      <div className="px-3 py-2 border-b border-[#07b6d5]/10 flex items-center gap-2">
        <span className="material-symbols-outlined text-[#07b6d5] text-sm" style={{ fontFamily: 'Material Symbols Outlined' }}>psychology</span>
        <span className="text-[10px] font-bold uppercase tracking-wider text-[#07b6d5]">AI Reasoning Chain</span>
      </div>
      <div className="p-3 space-y-2">
        {chain.map((step, i) => (
          <div key={i} className="flex gap-2">
            <div className="w-5 h-5 rounded-full bg-[#07b6d5]/20 flex items-center justify-center shrink-0 mt-0.5">
              <span className="text-[9px] font-bold text-[#07b6d5]">{step.step}</span>
            </div>
            <div>
              <p className="text-[11px] text-slate-300">{step.observation}</p>
              <p className="text-[10px] text-slate-400 italic mt-0.5">{'\u2192'} {step.inference}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

// ─── Inferred Dependencies Card ───────────────────────────────────────────

const InferredDependenciesCard: React.FC<{ deps: InferredDependency[]; targetService?: string }> = ({ deps, targetService }) => {
  if (!deps.length) return null;
  const normalizedTarget = targetService?.toLowerCase() ?? '';
  const isTarget = (name: string) => normalizedTarget !== '' && name.toLowerCase() === normalizedTarget;
  return (
    <div className="bg-slate-900/40 border border-slate-800 rounded-lg overflow-hidden">
      <div className="px-3 py-2 border-b border-slate-800 flex items-center gap-2 bg-slate-900/60">
        <span className="material-symbols-outlined text-violet-400 text-sm" style={{ fontFamily: 'Material Symbols Outlined' }}>hub</span>
        <span className="text-[10px] font-bold uppercase tracking-wider">Inferred Dependencies</span>
      </div>
      <div className="p-3 space-y-1.5">
        {deps.map((dep, i) => (
          <div key={i} className="flex items-center gap-2 text-[11px]">
            <span className={`font-mono ${isTarget(dep.source) ? 'text-[#07b6d5] font-bold' : 'text-[#07b6d5]'}`}>
              {dep.source}
            </span>
            {isTarget(dep.source) && (
              <span className="text-[8px] px-1 py-0.5 rounded bg-[#07b6d5]/20 text-[#07b6d5] border border-[#07b6d5]/30 font-bold">TARGET</span>
            )}
            <span className="text-slate-600">{'\u2192'}</span>
            <span className="font-mono text-slate-300">{dep.target || dep.targets?.join(', ')}</span>
            {dep.evidence && (
              <span className="text-[9px] text-slate-500 ml-auto truncate max-w-[200px]">{dep.evidence}</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

export default AISupervisor;
