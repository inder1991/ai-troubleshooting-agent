import React, { useState, useRef, useEffect, useMemo, useCallback } from 'react';
import type { ChatMessage as ChatMessageType, TaskEvent, V4Findings, V4SessionStatus, Breadcrumb, PatientZero, ReasoningChainStep } from '../../types';
import { sendChatMessage } from '../../services/api';

interface InvestigatorProps {
  sessionId: string;
  messages: ChatMessageType[];
  events: TaskEvent[];
  onNewMessage: (message: ChatMessageType) => void;
  wsConnected: boolean;
  findings: V4Findings | null;
  status: V4SessionStatus | null;
}

// ─── Timeline Builder ─────────────────────────────────────────────────────

interface ToolCallGroup {
  kind: 'tool_group';
  agent: string;
  events: TaskEvent[];
  ts: number;
}

type TimelineItem =
  | { kind: 'chat'; msg: ChatMessageType; ts: number }
  | { kind: 'event'; event: TaskEvent; ts: number }
  | { kind: 'reasoning_chain'; chain: ReasoningChainStep[]; ts: number }
  | ToolCallGroup;

function buildTimeline(
  messages: ChatMessageType[],
  events: TaskEvent[],
  showToolCalls: boolean,
  reasoningChain?: ReasoningChainStep[],
): TimelineItem[] {
  const eventItems: TimelineItem[] = [];
  let i = 0;
  while (i < events.length) {
    const ev = events[i];
    if (ev.event_type === 'tool_call') {
      const group: TaskEvent[] = [ev];
      let j = i + 1;
      while (j < events.length && events[j].event_type === 'tool_call' && events[j].agent_name === ev.agent_name) {
        group.push(events[j]);
        j++;
      }
      if (showToolCalls) {
        eventItems.push({ kind: 'tool_group', agent: ev.agent_name, events: group, ts: new Date(ev.timestamp).getTime() });
      }
      i = j;
    } else {
      eventItems.push({ kind: 'event', event: ev, ts: new Date(ev.timestamp).getTime() });
      i++;
    }
  }

  // Insert reasoning chain at the correct chronological position (after its summary event)
  if (reasoningChain && reasoningChain.length > 0) {
    const reasoningEvent = events.find(
      (e) => e.event_type === 'summary' && e.message.toLowerCase().includes('reasoning chain'),
    );
    const ts = reasoningEvent
      ? new Date(reasoningEvent.timestamp).getTime() + 1 // just after the summary event
      : Date.now();
    eventItems.push({ kind: 'reasoning_chain', chain: reasoningChain, ts });
  }

  const chatItems: TimelineItem[] = messages.map((msg) => ({ kind: 'chat' as const, msg, ts: new Date(msg.timestamp).getTime() }));
  return [...chatItems, ...eventItems].sort((a, b) => a.ts - b.ts);
}

// Agent badge colors
const agentColor: Record<string, string> = {
  log_agent: 'bg-red-500/20 text-red-400 border-red-500/30',
  metrics_agent: 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30',
  k8s_agent: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  tracing_agent: 'bg-violet-500/20 text-violet-400 border-violet-500/30',
  code_agent: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  change_agent: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
};

const agentIcon: Record<string, string> = {
  log_agent: 'search',
  metrics_agent: 'bar_chart',
  k8s_agent: 'dns',
  tracing_agent: 'route',
  code_agent: 'code',
  change_agent: 'difference',
};

const Investigator: React.FC<InvestigatorProps> = ({
  sessionId,
  messages,
  events,
  onNewMessage,
  wsConnected,
  findings,
  status,
}) => {
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [showToolCalls, setShowToolCalls] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const userScrolledUpRef = useRef(false);

  // Only auto-scroll when user is near the bottom (not reading earlier content)
  const handleScroll = useCallback(() => {
    if (!scrollRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
    userScrolledUpRef.current = scrollHeight - scrollTop - clientHeight > 120;
  }, []);

  useEffect(() => {
    if (scrollRef.current && !userScrolledUpRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, events]);

  useEffect(() => { inputRef.current?.focus(); }, [sessionId]);

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || sending) return;

    const userMessage: ChatMessageType = { role: 'user', content: trimmed, timestamp: new Date().toISOString() };
    onNewMessage(userMessage);
    setInput('');
    setSending(true);

    try {
      const response = await sendChatMessage(sessionId, trimmed);
      if (response?.content) onNewMessage(response);
    } catch (err) {
      onNewMessage({ role: 'assistant', content: `Error: ${err instanceof Error ? err.message : 'Failed to send message'}`, timestamp: new Date().toISOString() });
    } finally {
      setSending(false);
    }
  };

  const timeline = useMemo(
    () => buildTimeline(messages, events, showToolCalls, findings?.reasoning_chain),
    [messages, events, showToolCalls, findings?.reasoning_chain],
  );
  const toolCallCount = events.filter((e) => e.event_type === 'tool_call').length;

  // Group breadcrumbs by agent for evidence trail rendering
  const breadcrumbsByAgent = useMemo(() => {
    const map: Record<string, Breadcrumb[]> = {};
    for (const b of status?.breadcrumbs || []) {
      if (!map[b.agent_name]) map[b.agent_name] = [];
      map[b.agent_name].push(b);
    }
    return map;
  }, [status?.breadcrumbs]);

  // Derive active agents
  const activeAgents = useMemo(() => {
    const started = new Set<string>();
    const completed = new Set<string>();
    events.forEach((e) => {
      if (e.event_type === 'started') started.add(e.agent_name);
      if (e.event_type === 'summary' || e.event_type === 'success') completed.add(e.agent_name);
    });
    return Array.from(started).map((a) => ({ name: a, active: !completed.has(a) }));
  }, [events]);

  // Repo mismatch detection
  const repoMismatch = useMemo(() => {
    if (!findings?.patient_zero?.service || !findings?.target_service) return false;
    return findings.patient_zero.service.toLowerCase() !== findings.target_service.toLowerCase();
  }, [findings?.patient_zero?.service, findings?.target_service]);

  const handleAttachRepo = useCallback(() => {
    if (!sessionId) return;
    const userMsg: ChatMessageType = { role: 'user', content: 'confirm', timestamp: new Date().toISOString() };
    onNewMessage(userMsg);
    sendChatMessage(sessionId, 'confirm').then((resp) => {
      if (resp?.content) onNewMessage(resp);
    }).catch(() => {});
  }, [sessionId, onNewMessage]);

  // Time-to-impact
  const firstErrorTime = findings?.patient_zero?.first_error_time;
  const [elapsedSec, setElapsedSec] = useState(0);
  useEffect(() => {
    if (!firstErrorTime) return;
    const start = new Date(firstErrorTime).getTime();
    const tick = () => setElapsedSec(Math.floor((Date.now() - start) / 1000));
    tick();
    const iv = setInterval(tick, 1000);
    return () => clearInterval(iv);
  }, [firstErrorTime]);

  const formatElapsed = (sec: number) => {
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  };

  return (
    <div className="flex flex-col h-full bg-slate-900/20">
      {/* Patient Zero Banner (sticky) */}
      {findings?.patient_zero && (
        <div className="sticky top-0 z-10 bg-gradient-to-r from-red-950/80 to-red-900/40 border-b border-red-500/30 px-4 py-3 animate-pulse-red">
          <div className="flex items-center gap-2 mb-1">
            <span className="w-2.5 h-2.5 rounded-full bg-red-500 animate-pulse" />
            <span className="text-[10px] font-bold uppercase tracking-wider text-red-400">Patient Zero</span>
            {firstErrorTime && (
              <span className="ml-auto text-lg font-mono font-bold text-red-400">{formatElapsed(elapsedSec)}</span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <span className="text-sm font-mono text-red-200 font-bold">{findings.patient_zero.service}</span>
            {repoMismatch && (
              <span className="inline-flex items-center gap-1 text-[9px] font-bold uppercase px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-400 border border-amber-500/30">
                <span className="material-symbols-outlined" style={{ fontFamily: 'Material Symbols Outlined', fontSize: '12px' }}>warning</span>
                Repo Mismatch
              </span>
            )}
          </div>
          <p className="text-[10px] text-red-300/70 mt-0.5">{findings.patient_zero.evidence}</p>
          {repoMismatch && (
            <div className="mt-1.5 flex items-center gap-2">
              <p className="text-[10px] text-amber-300/80">
                Root cause in <strong>{findings.patient_zero.service}</strong>, repo provided for <strong>{findings.target_service}</strong>
              </p>
              <button
                onClick={handleAttachRepo}
                className="text-[9px] font-bold uppercase px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30 hover:bg-amber-500/30 transition-colors flex items-center gap-1"
              >
                <span className="material-symbols-outlined" style={{ fontFamily: 'Material Symbols Outlined', fontSize: '11px' }}>link</span>
                Attach Repo
              </button>
            </div>
          )}
        </div>
      )}

      {/* Agent Pulse Indicator */}
      {activeAgents.length > 0 && (
        <div className="px-4 py-2 border-b border-slate-800/50 flex items-center gap-2 flex-wrap">
          {activeAgents.map((a) => (
            <span
              key={a.name}
              className={`text-[9px] px-2 py-0.5 rounded-full border font-bold uppercase ${
                a.active
                  ? (agentColor[a.name] || 'bg-slate-500/20 text-slate-400 border-slate-500/30') + ' animate-pulse'
                  : 'bg-slate-800/50 text-slate-500 border-slate-700'
              }`}
            >
              {a.name.replace(/_/g, ' ')}
            </span>
          ))}
        </div>
      )}

      {/* Header */}
      <div className="p-4 border-b border-slate-800/50 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-primary text-sm" style={{ fontFamily: 'Material Symbols Outlined' }}>psychology</span>
          <h2 className="text-xs font-bold uppercase tracking-widest text-slate-400">Investigator</h2>
        </div>
        <button
          onClick={() => setShowToolCalls(!showToolCalls)}
          className={`text-[10px] px-2 py-0.5 rounded border font-mono transition-colors ${
            showToolCalls ? 'bg-purple-500/20 text-purple-400 border-purple-500/30' : 'bg-slate-800/50 text-slate-500 border-slate-700'
          }`}
        >
          {showToolCalls ? 'TOOLS ON' : 'TOOLS OFF'}
          {toolCallCount > 0 && <span className="ml-1 text-[9px] opacity-60">({toolCallCount})</span>}
        </button>
      </div>

      {/* Investigative Timeline */}
      <div ref={scrollRef} onScroll={handleScroll} className="flex-1 overflow-y-auto px-4 py-3 custom-scrollbar">
        {timeline.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-slate-500">
            <p className="text-sm">Waiting for investigation to begin...</p>
            <p className="text-[10px] mt-1">Agent events will stream here in real-time</p>
          </div>
        ) : (
          <div className="relative pl-6">
            {/* Vertical connecting line */}
            <div className="absolute left-3 top-2 bottom-2 w-px bg-slate-700" />

            <div className="space-y-2">
              {timeline.map((item, idx) => {
                if (item.kind === 'chat') {
                  return <ChatBubble key={`chat-${idx}`} message={item.msg} />;
                }
                if (item.kind === 'tool_group') {
                  return <ToolCallGroupNode key={`tg-${idx}`} group={item} />;
                }
                if (item.kind === 'reasoning_chain') {
                  return <ReasoningChainSection key={`rc-${idx}`} chain={item.chain} />;
                }
                return <EventNode key={`ev-${idx}`} event={item.event} breadcrumbs={item.event.event_type === 'summary' ? breadcrumbsByAgent[item.event.agent_name] : undefined} />;
              })}
            </div>
          </div>
        )}

        {sending && (
          <div className="flex justify-start ml-6 mt-2">
            <div className="bg-[#07b6d5]/5 border border-[#07b6d5]/10 rounded-xl px-3 py-2">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 bg-[#07b6d5] rounded-full animate-pulse" />
                <span className="text-xs text-slate-400">Thinking...</span>
              </div>
            </div>
          </div>
        )}

      </div>

      {/* Chat Input (bottom, sticky) */}
      <div className="p-3 border-t border-slate-800/50 bg-slate-900/40 flex-shrink-0">
        <form onSubmit={handleSend} className="relative">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(e); } }}
            placeholder="Ask the investigator..."
            disabled={sending}
            className="w-full bg-slate-800/50 border border-slate-700 rounded-lg py-2 px-3 text-xs focus:ring-1 focus:ring-primary focus:border-primary outline-none resize-none h-16 placeholder:text-slate-600 disabled:opacity-50 text-white custom-scrollbar"
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

// ─── Event Node (vertical timeline style) ─────────────────────────────────

const EventNode: React.FC<{ event: TaskEvent; breadcrumbs?: Breadcrumb[] }> = ({ event, breadcrumbs }) => {
  const icon = agentIcon[event.agent_name] || 'circle';
  const colorClass = agentColor[event.agent_name] || 'bg-slate-500/20 text-slate-400 border-slate-500/30';

  if (event.event_type === 'phase_change') {
    const phaseName = event.details?.phase
      ? String(event.details.phase).replace(/_/g, ' ').toUpperCase()
      : event.message.toUpperCase();
    return (
      <div className="relative flex items-center gap-3 py-1">
        <div className="absolute left-[-18px] w-2.5 h-2.5 rounded-full bg-[#07b6d5] border-2 border-slate-900" />
        <div className="flex-1 flex items-center gap-3">
          <div className="flex-1 h-px bg-gradient-to-r from-transparent via-[#07b6d5]/40 to-transparent" />
          <span className="text-[10px] font-bold tracking-[0.2em] text-[#07b6d5]">{phaseName}</span>
          <div className="flex-1 h-px bg-gradient-to-r from-transparent via-[#07b6d5]/40 to-transparent" />
        </div>
      </div>
    );
  }

  if (event.event_type === 'finding') {
    const severity = String(event.details?.severity || 'medium');
    const sevColor = severity === 'critical' || severity === 'high' ? 'text-red-400' : severity === 'medium' ? 'text-amber-400' : 'text-blue-400';
    return (
      <div className="relative">
        <div className={`absolute left-[-18px] w-2.5 h-2.5 rounded-full ${severity === 'critical' || severity === 'high' ? 'bg-red-500' : 'bg-amber-500'} border-2 border-slate-900`} />
        <div className="bg-slate-800/30 border border-slate-700/50 rounded-lg px-3 py-2">
          <div className="flex items-center gap-2 text-[10px]">
            <span className="material-symbols-outlined text-sm" style={{ fontFamily: 'Material Symbols Outlined', color: severity === 'critical' || severity === 'high' ? '#f87171' : '#fbbf24' }}>lightbulb</span>
            <span className={`font-bold uppercase ${sevColor}`}>{severity}</span>
            <span className="text-slate-500">{event.agent_name.replace(/_/g, ' ')}</span>
          </div>
          <p className="text-xs text-slate-300 mt-1">{event.message.split(' — ')[0]}</p>
        </div>
      </div>
    );
  }

  if (event.event_type === 'summary') {
    const confidence = Number(event.details?.confidence || 0);
    return (
      <div className="relative">
        <div className="absolute left-[-18px] w-2.5 h-2.5 rounded-full bg-green-500 border-2 border-slate-900" />
        <div className="bg-[#07b6d5]/5 border border-[#07b6d5]/20 rounded-lg px-3 py-2">
          <div className="flex items-center gap-2 text-[10px]">
            <span className="material-symbols-outlined text-[#07b6d5] text-sm" style={{ fontFamily: 'Material Symbols Outlined' }}>check_circle</span>
            <span className="font-bold uppercase text-[#07b6d5]">{event.agent_name.replace(/_/g, ' ')}</span>
            <span className={`ml-auto font-mono font-bold ${confidence >= 70 ? 'text-green-400' : confidence >= 40 ? 'text-amber-400' : 'text-red-400'}`}>{confidence}%</span>
          </div>
          {/* Evidence Trail: breadcrumbs for this agent */}
          {breadcrumbs && breadcrumbs.length > 0 && (
            <EvidenceTrail breadcrumbs={breadcrumbs} agentName={event.agent_name} />
          )}
        </div>
      </div>
    );
  }

  if (event.event_type === 'started') {
    return (
      <div className="relative flex items-center gap-2 py-0.5">
        <div className="absolute left-[-18px] w-2.5 h-2.5 rounded-full bg-blue-400 border-2 border-slate-900" />
        <span className="material-symbols-outlined text-blue-400 text-xs" style={{ fontFamily: 'Material Symbols Outlined' }}>{icon}</span>
        <span className="text-[10px] text-blue-400 font-bold">{event.agent_name.replace(/_/g, ' ')}</span>
        <span className="text-[10px] text-slate-500">{event.message}</span>
        <span className="text-[9px] text-slate-600 ml-auto">{new Date(event.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>
      </div>
    );
  }

  if (event.event_type === 'error' || event.event_type === 'warning') {
    const isError = event.event_type === 'error';
    return (
      <div className="relative">
        <div className={`absolute left-[-18px] w-2.5 h-2.5 rounded-full ${isError ? 'bg-red-500' : 'bg-amber-500'} border-2 border-slate-900`} />
        <div className={`border rounded-lg px-3 py-2 ${isError ? 'border-red-500/30 bg-red-500/10' : 'border-amber-500/30 bg-amber-500/10'}`}>
          <div className="flex items-center gap-2 text-[10px]">
            <span className={`font-bold uppercase ${isError ? 'text-red-400' : 'text-amber-400'}`}>{event.agent_name.replace(/_/g, ' ')}</span>
          </div>
          <p className="text-xs text-slate-300 mt-1">{event.message}</p>
        </div>
      </div>
    );
  }

  // Generic
  return (
    <div className="relative flex items-start gap-2 py-0.5">
      <div className="absolute left-[-18px] w-2.5 h-2.5 rounded-full bg-slate-600 border-2 border-slate-900" />
      <span className="text-[10px] text-slate-600 shrink-0">
        {new Date(event.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
      </span>
      <span className="text-[10px] text-[#07b6d5]">{event.agent_name}</span>
      <span className="text-[10px] text-slate-400 truncate">{event.message}</span>
    </div>
  );
};

// ─── Tool Call Group Node ─────────────────────────────────────────────────

const ToolCallGroupNode: React.FC<{ group: ToolCallGroup }> = ({ group }) => {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="relative">
      <div className="absolute left-[-18px] w-2.5 h-2.5 rounded-full bg-purple-500 border-2 border-slate-900" />
      <button onClick={() => setExpanded(!expanded)} className="w-full text-left flex items-center gap-2 text-[10px] hover:bg-slate-800/30 rounded px-2 py-1 transition-colors" aria-expanded={expanded}>
        <span className={`material-symbols-outlined text-xs text-purple-400 transition-transform ${expanded ? 'rotate-90' : ''}`} style={{ fontFamily: 'Material Symbols Outlined' }}>chevron_right</span>
        <span className="font-bold text-purple-400 uppercase">{group.agent.replace(/_/g, ' ')}</span>
        <span className="text-slate-500">{group.events.length} tool calls</span>
      </button>
      {expanded && (
        <div className="pl-4 mt-1 space-y-0.5 text-[10px] text-slate-400 font-mono">
          {group.events.map((ev, i) => (
            <div key={i} className="flex gap-2">
              <span className="text-slate-600 shrink-0">{new Date(ev.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>
              <span className="truncate">{ev.message}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// ─── Chat Bubble ──────────────────────────────────────────────────────────

const ChatBubble: React.FC<{ message: ChatMessageType }> = ({ message }) => {
  if (message.role === 'user') {
    return (
      <div className="relative flex justify-end">
        <div className="absolute left-[-18px] w-2.5 h-2.5 rounded-full bg-slate-500 border-2 border-slate-900" />
        <div className="max-w-[85%] bg-slate-800/60 border border-slate-700 rounded-xl px-3 py-2">
          <p className="text-xs text-slate-200 whitespace-pre-wrap">{message.content}</p>
          <p className="text-[9px] text-slate-600 mt-1 text-right">{new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</p>
        </div>
      </div>
    );
  }
  return (
    <div className="relative">
      <div className="absolute left-[-18px] w-2.5 h-2.5 rounded-full bg-[#07b6d5] border-2 border-slate-900" />
      <div className="bg-[#07b6d5]/5 border border-[#07b6d5]/10 rounded-xl p-3">
        <p className="text-xs text-slate-300 whitespace-pre-wrap leading-relaxed">{message.content}</p>
        <p className="text-[9px] text-slate-600 mt-1">{new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</p>
      </div>
    </div>
  );
};

// ─── Reasoning Chain Section ──────────────────────────────────────────────

const ReasoningChainSection: React.FC<{ chain: ReasoningChainStep[] }> = ({ chain }) => {
  if (!chain.length) return null;
  return (
    <div className="mt-4 ml-6 bg-[#07b6d5]/5 border border-[#07b6d5]/15 rounded-lg overflow-hidden">
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

// ─── Evidence Trail (breadcrumbs under agent summary) ─────────────────────

const sourceTypeIcon: Record<string, string> = {
  log: 'description',
  metric: 'bar_chart',
  k8s_event: 'dns',
  trace_span: 'route',
  code: 'code',
  config: 'settings',
};

const EvidenceTrail: React.FC<{ breadcrumbs: Breadcrumb[]; agentName: string }> = ({ breadcrumbs, agentName }) => {
  const [expanded, setExpanded] = useState(false);
  const colorClass = agentColor[agentName] || 'bg-slate-500/20 text-slate-400 border-slate-500/30';

  return (
    <div className="mt-2 pt-2 border-t border-slate-800/50">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1.5 text-[9px] text-slate-500 hover:text-slate-300 transition-colors"
      >
        <span className="material-symbols-outlined text-xs" style={{ fontFamily: 'Material Symbols Outlined' }}>
          attach_file
        </span>
        <span className="font-bold uppercase tracking-wider">Evidence</span>
        <span className="font-mono">({breadcrumbs.length})</span>
        <span className={`material-symbols-outlined text-xs transition-transform ${expanded ? 'rotate-90' : ''}`} style={{ fontFamily: 'Material Symbols Outlined' }}>
          chevron_right
        </span>
      </button>
      {expanded && (
        <div className="flex flex-wrap gap-1.5 mt-1.5">
          {breadcrumbs.map((crumb, i) => {
            const icon = sourceTypeIcon[crumb.action] || sourceTypeIcon.log;
            // Extract short label from action (e.g., "get_pod_status" → "pod_status")
            const shortAction = crumb.action.replace(/^(get_|test_|search_|query_|list_|analyze_)/, '');
            return (
              <span
                key={i}
                className={`inline-flex items-center gap-1 text-[10px] font-mono px-1.5 py-0.5 rounded border cursor-default ${colorClass}`}
                title={crumb.detail}
              >
                <span className="material-symbols-outlined" style={{ fontFamily: 'Material Symbols Outlined', fontSize: '10px' }}>{icon}</span>
                {shortAction}
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default Investigator;
