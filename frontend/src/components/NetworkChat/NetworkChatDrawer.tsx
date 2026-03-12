import React, { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import ReactMarkdown from 'react-markdown';
import NetworkChatFAB from './NetworkChatFAB';
import { useNetworkChat } from '../../hooks/useNetworkChat';
import type { NetworkChatMessage } from '../../hooks/useNetworkChat';

const SUGGESTED_PROMPTS: Record<string, string[]> = {
  observatory: ['Any anomalies right now?', 'Explain the top alert', 'What changed in the last hour?'],
  'network-topology': ['Review this design', 'Any redundancy gaps?', 'What breaks if this node fails?'],
  ipam: ['Which subnets are running low?', 'Any IP conflicts?', 'Forecast growth for this region'],
  'device-monitoring': ['Why is this device unhealthy?', 'Show interface errors', 'Compare to last week'],
  'network-adapters': ['Evaluate this rule', 'Show security group rules', 'Any misconfigurations?'],
  matrix: ['Any blocked paths?', 'Check reachability to 10.0.0.0/24', 'Show routing state'],
  'mib-browser': ['Explain this OID', 'Show device metrics', 'What does this counter mean?'],
  'cloud-resources': ['Show VPC routes', 'Any security group issues?', 'Check peering status'],
  'security-resources': ['Audit security groups', 'Show NACL rules', 'Any compliance issues?'],
};

interface NetworkChatDrawerProps {
  view: string;
  visibleData?: Record<string, unknown>;
  onStartInvestigation?: () => void;
}

const NetworkChatDrawer: React.FC<NetworkChatDrawerProps> = ({
  view,
  visibleData = {},
  onStartInvestigation,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const { messages, isSending, activeToolCalls, sendMessage, clearThread } = useNetworkChat({
    view,
  });

  const prompts = SUGGESTED_PROMPTS[view] || ['Ask me anything about this view'];

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length]);

  // Focus input when drawer opens
  useEffect(() => {
    if (isOpen) inputRef.current?.focus();
  }, [isOpen]);

  const handleSend = () => {
    if (!input.trim()) return;
    sendMessage(input, visibleData);
    setInput('');
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handlePromptClick = (prompt: string) => {
    sendMessage(prompt, visibleData);
  };

  return (
    <>
      {/* FAB */}
      {!isOpen && (
        <NetworkChatFAB
          onClick={() => setIsOpen(true)}
          hasUnread={false}
        />
      )}

      {/* Drawer */}
      <AnimatePresence>
        {isOpen && (
          <>
            {/* Backdrop */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 bg-black/30 z-[55]"
              onClick={() => setIsOpen(false)}
            />

            {/* Panel */}
            <motion.div
              initial={{ x: 420 }}
              animate={{ x: 0 }}
              exit={{ x: 420 }}
              transition={{ type: 'spring', stiffness: 400, damping: 40 }}
              className="fixed right-0 top-0 bottom-0 w-full sm:w-[420px] z-[70] bg-slate-900/95 backdrop-blur-xl border-l border-white/5 flex flex-col shadow-2xl"
            >
              {/* Header */}
              <div className="flex items-center justify-between px-4 py-3 border-b border-white/5 flex-shrink-0">
                <div className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-duck-accent text-[20px]">chat</span>
                  <h2 className="text-sm font-bold text-slate-200">Network Assistant</h2>
                </div>
                <div className="flex items-center gap-1">
                  <button
                    onClick={clearThread}
                    title="New thread"
                    className="p-1.5 rounded text-slate-500 hover:text-slate-300 hover:bg-white/5 transition-colors"
                  >
                    <span className="material-symbols-outlined text-[18px]">restart_alt</span>
                  </button>
                  <button
                    onClick={() => setIsOpen(false)}
                    title="Close"
                    className="p-1.5 rounded text-slate-500 hover:text-slate-300 hover:bg-white/5 transition-colors"
                  >
                    <span className="material-symbols-outlined text-[18px]">close</span>
                  </button>
                </div>
              </div>

              {/* Messages */}
              <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3 custom-scrollbar">
                {messages.length === 0 && (
                  <div className="text-center py-8">
                    <span className="material-symbols-outlined text-[40px] text-slate-600 mb-3 block">chat</span>
                    <p className="text-xs text-slate-500 mb-4">
                      Ask me about what you see in this view.
                    </p>
                    <div className="flex flex-col gap-2">
                      {prompts.map((p) => (
                        <button
                          key={p}
                          onClick={() => handlePromptClick(p)}
                          className="text-left text-xs text-slate-400 hover:text-cyan-400 bg-white/[0.03] hover:bg-white/[0.06] px-3 py-2 rounded-lg border border-white/5 transition-colors"
                        >
                          {p}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {messages
                  .filter((m) => m.role !== 'tool')
                  .map((msg, i) => (
                    <MessageBubble key={i} message={msg} />
                  ))}

                {/* Tool call indicators */}
                {activeToolCalls.length > 0 && (
                  <div className="flex items-center gap-2 text-xs text-slate-500 px-2">
                    <span className="animate-spin material-symbols-outlined text-[14px]">progress_activity</span>
                    <span>Using: {activeToolCalls.join(', ')}</span>
                  </div>
                )}

                {/* Sending indicator */}
                {isSending && activeToolCalls.length === 0 && (
                  <div className="flex items-center gap-2 text-xs text-slate-500 px-2">
                    <span className="animate-pulse">Thinking...</span>
                  </div>
                )}

                <div ref={messagesEndRef} />
              </div>

              {/* Input */}
              <div className="px-4 py-3 border-t border-white/5 flex-shrink-0">
                <div className="flex gap-2">
                  <textarea
                    ref={inputRef}
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="Ask about this view..."
                    rows={1}
                    className="flex-1 bg-white/[0.04] border border-white/10 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-600 resize-none focus:outline-none focus:border-cyan-400/40 transition-colors"
                  />
                  <button
                    onClick={handleSend}
                    disabled={!input.trim() || isSending}
                    className="px-3 py-2 rounded-lg bg-duck-accent text-duck-bg text-xs font-semibold disabled:opacity-30 hover:brightness-110 transition-all"
                  >
                    <span className="material-symbols-outlined text-[18px]">send</span>
                  </button>
                </div>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </>
  );
};

// ── Message Bubble ──

const MessageBubble: React.FC<{ message: NetworkChatMessage }> = ({ message }) => {
  const isUser = message.role === 'user';
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[85%] px-3 py-2 rounded-lg text-xs leading-relaxed ${
          isUser
            ? 'bg-cyan-400/10 text-slate-200 rounded-br-none'
            : 'bg-white/[0.04] text-slate-300 rounded-bl-none'
        }`}
      >
        {isUser ? (
          <p>{message.content}</p>
        ) : (
          <div className="prose prose-invert prose-xs max-w-none">
            <ReactMarkdown>{message.content}</ReactMarkdown>
          </div>
        )}
        {message.tool_calls && message.tool_calls.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {message.tool_calls.map((tc, i) => (
              <span
                key={i}
                className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] ${
                  tc.blocked ? 'bg-red-500/10 text-red-400' : 'bg-cyan-400/10 text-cyan-400'
                }`}
              >
                <span className="material-symbols-outlined text-[11px]">build</span>
                {tc.name}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default NetworkChatDrawer;
