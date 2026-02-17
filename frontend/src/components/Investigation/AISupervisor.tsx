import React, { useState, useRef, useEffect } from 'react';
import type { ChatMessage as ChatMessageType, TaskEvent } from '../../types';
import { sendChatMessage } from '../../services/api';

interface AISupervisorProps {
  sessionId: string;
  messages: ChatMessageType[];
  events: TaskEvent[];
  onNewMessage: (message: ChatMessageType) => void;
  wsConnected: boolean;
}

// Map event types to display tags
const eventTypeTag: Record<string, { label: string; color: string }> = {
  started: { label: 'STARTED', color: 'text-blue-400' },
  progress: { label: 'PROGRESS', color: 'text-slate-400' },
  success: { label: 'SUCCESS', color: 'text-green-400' },
  warning: { label: 'WARNING', color: 'text-amber-400' },
  error: { label: 'ERROR', color: 'text-red-400' },
};

// Infer operation type from agent name / message content
const inferOperationTag = (event: TaskEvent): { label: string; color: string } => {
  const msg = event.message.toLowerCase();
  const agent = event.agent_name.toLowerCase();

  if (msg.includes('tool') || msg.includes('calling') || msg.includes('querying') || msg.includes('fetching')) {
    return { label: 'TOOL_CALL', color: 'text-purple-400' };
  }
  if (msg.includes('reasoning') || msg.includes('analyzing') || msg.includes('correlating') || msg.includes('hypothesis')) {
    return { label: 'REASONING', color: 'text-cyan-400' };
  }
  if (msg.includes('validated') || msg.includes('verdict') || msg.includes('critic')) {
    return { label: 'VALIDATION', color: 'text-emerald-400' };
  }
  if (agent.includes('log') || agent.includes('elk')) {
    return { label: 'LOG_SCAN', color: 'text-amber-300' };
  }
  if (agent.includes('metric') || agent.includes('prometheus')) {
    return { label: 'METRIC_CHECK', color: 'text-orange-400' };
  }
  if (agent.includes('k8s') || agent.includes('kube')) {
    return { label: 'K8S_PROBE', color: 'text-blue-300' };
  }
  if (agent.includes('trace') || agent.includes('jaeger')) {
    return { label: 'TRACE_WALK', color: 'text-teal-400' };
  }
  if (agent.includes('code') || agent.includes('git')) {
    return { label: 'CODE_SCAN', color: 'text-violet-400' };
  }
  if (agent.includes('supervisor')) {
    return { label: 'ORCHESTRATE', color: 'text-cyan-300' };
  }
  return eventTypeTag[event.event_type] || { label: 'EVENT', color: 'text-slate-400' };
};

// Check if events are from same agent (for grouping/nesting)
const isSameAgentGroup = (events: TaskEvent[], idx: number): boolean => {
  if (idx === 0) return false;
  return events[idx].agent_name === events[idx - 1].agent_name;
};

const AISupervisor: React.FC<AISupervisorProps> = ({
  sessionId,
  messages,
  events,
  onNewMessage,
  wsConnected,
}) => {
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [showLogs, setShowLogs] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, events]);

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

  // Build an interleaved timeline of chat messages + events
  type TimelineItem =
    | { kind: 'chat'; msg: ChatMessageType; ts: number }
    | { kind: 'event'; event: TaskEvent; ts: number };

  const timeline: TimelineItem[] = [
    ...messages.map((msg) => ({
      kind: 'chat' as const,
      msg,
      ts: new Date(msg.timestamp).getTime(),
    })),
    ...(showLogs
      ? events.map((event) => ({
          kind: 'event' as const,
          event,
          ts: new Date(event.timestamp).getTime(),
        }))
      : []),
  ].sort((a, b) => a.ts - b.ts);

  return (
    <div className="flex flex-col h-full bg-slate-900/20 border-r border-[#07b6d5]/10">
      {/* Header - matches reference */}
      <div className="p-4 border-b border-primary/10 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-primary text-sm" style={{ fontFamily: 'Material Symbols Outlined' }}>psychology</span>
          <h2 className="text-xs font-bold uppercase tracking-widest text-slate-400">AI Supervisor</h2>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowLogs(!showLogs)}
            className={`text-[10px] px-2 py-0.5 rounded border font-mono transition-colors ${
              showLogs
                ? 'bg-primary/20 text-primary border-primary/30'
                : 'bg-slate-800/50 text-slate-500 border-slate-700'
            }`}
          >
            {showLogs ? 'LOGS ON' : 'LOGS OFF'}
          </button>
          <span className="text-[10px] px-2 py-0.5 bg-primary/20 text-primary rounded border border-primary/30 font-mono">V4.2-STABLE</span>
        </div>
      </div>

      {/* Scrollable content: interleaved chat + log feed */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3 custom-scrollbar">
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

            const event = item.event;
            const opTag = inferOperationTag(event);
            const isNested = isSameAgentGroup(
              events,
              events.indexOf(event)
            );

            return (
              <LogEntry
                key={`event-${idx}`}
                event={event}
                opTag={opTag}
                isNested={isNested}
              />
            );
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
      </div>

      {/* Chat Input - matches reference */}
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

// Chat message bubble (matches reference style)
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

// Monospace log entry with operation tags and vertical connectors
const LogEntry: React.FC<{
  event: TaskEvent;
  opTag: { label: string; color: string };
  isNested: boolean;
}> = ({ event, opTag, isNested }) => {
  const levelColor =
    event.event_type === 'error'
      ? 'text-red-400'
      : event.event_type === 'warning'
      ? 'text-amber-400'
      : event.event_type === 'success'
      ? 'text-green-400'
      : event.event_type === 'started'
      ? 'text-blue-400'
      : 'text-slate-500';

  const levelIcon =
    event.event_type === 'success'
      ? 'check_circle'
      : event.event_type === 'error'
      ? 'error'
      : event.event_type === 'warning'
      ? 'warning'
      : event.event_type === 'started'
      ? 'play_circle'
      : 'search';

  const isActive = event.event_type === 'progress' || event.event_type === 'started';

  return (
    <div className={`${isNested ? 'ml-6 border-l-2 border-slate-800 pl-3' : ''}`}>
      <div className={`font-mono text-[11px] flex items-start gap-2 ${isActive ? 'animate-pulse' : ''}`}>
        {/* Status icon */}
        <span
          className={`material-symbols-outlined text-[14px] mt-0.5 shrink-0 ${levelColor}`}
          style={{ fontFamily: 'Material Symbols Outlined' }}
        >
          {levelIcon}
        </span>

        {/* Timestamp */}
        <span className="text-slate-600 shrink-0 w-[70px]">
          {new Date(event.timestamp).toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
          })}
        </span>

        {/* Operation type tag */}
        <span className={`font-bold shrink-0 ${opTag.color}`}>
          [{opTag.label}]
        </span>

        {/* Agent name */}
        <span className="text-[#07b6d5] shrink-0">
          {event.agent_name}
        </span>

        {/* Message */}
        <span className="text-slate-400 truncate">
          {event.message}
        </span>
      </div>

      {/* Nested detail expansion for events with details */}
      {event.details && Object.keys(event.details).length > 0 && (
        <details className="ml-6 mt-1 group">
          <summary className="list-none cursor-pointer flex items-center gap-1 text-[10px] text-slate-600 hover:text-slate-400 transition-colors">
            <span
              className="material-symbols-outlined text-[12px] group-open:rotate-90 transition-transform"
              style={{ fontFamily: 'Material Symbols Outlined' }}
            >
              chevron_right
            </span>
            View Details
          </summary>
          <div className="mt-1 ml-4 border-l border-slate-800 pl-2 space-y-0.5">
            {Object.entries(event.details).map(([key, value]) => (
              <div key={key} className="font-mono text-[10px]">
                <span className="text-slate-500">{key}: </span>
                <span className="text-slate-400">{typeof value === 'string' ? value : JSON.stringify(value)}</span>
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
};

export default AISupervisor;
