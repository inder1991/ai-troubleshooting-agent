import React, { useState, useRef, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useAssistantChat } from '../../hooks/useAssistantChat';
import AssistantMessageEntry from './AssistantMessage';

interface AssistantDockProps {
  onNavigate?: (page: string) => void;
  onStartInvestigation?: (capability: string, serviceName?: string) => void;
  onDownloadReport?: (sessionId: string) => void;
}

const QUICK_COMMANDS = [
  { label: 'status', cmd: 'What investigations are running?' },
  { label: 'health', cmd: 'Check system health' },
  { label: 'findings', cmd: 'Show recent findings' },
  { label: 'scan db', cmd: 'Start a database scan' },
];

const AssistantDock: React.FC<AssistantDockProps> = ({
  onNavigate,
  onStartInvestigation,
  onDownloadReport,
}) => {
  const [expanded, setExpanded] = useState(false);
  const [input, setInput] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const { messages, isLoading, sendMessage, clearThread } = useAssistantChat({
    onNavigate,
    onStartInvestigation,
    onDownloadReport,
  });

  const displayedMessages = messages.length > 50 ? messages.slice(-50) : messages;

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    if (expanded) inputRef.current?.focus();
  }, [expanded]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setExpanded(prev => !prev);
      }
      if (e.key === 'Escape' && expanded) {
        setExpanded(false);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [expanded]);

  const handleSubmit = useCallback(() => {
    if (!input.trim()) return;
    sendMessage(input);
    setInput('');
  }, [input, sendMessage]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleActionClick = useCallback((action: any) => {
    if (action.type === 'navigate' && onNavigate) onNavigate(action.page);
    else if (action.type === 'start_investigation' && onStartInvestigation) onStartInvestigation(action.capability, action.service_name);
    else if (action.type === 'download_report' && onDownloadReport) onDownloadReport(action.session_id);
  }, [onNavigate, onStartInvestigation, onDownloadReport]);

  return (
    <div className="relative z-40">
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ y: '100%', opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: '100%', opacity: 0 }}
            transition={{ duration: 0.25, ease: 'easeOut' }}
            className="h-[40vh] border-t-2 border-duck-accent/40 bg-duck-panel shadow-[0_-4px_20px_rgba(0,0,0,0.5)] flex flex-col overflow-hidden"
          >
            {/* Terminal header */}
            <div className="flex items-center justify-between px-4 py-1.5 border-b border-duck-border/30 shrink-0 bg-duck-panel/40">
              <div className="flex items-center gap-3">
                {/* Traffic light dots */}
                <div className="flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-full bg-red-500/60" />
                  <span className="w-2.5 h-2.5 rounded-full bg-amber-500/60" />
                  <span className="w-2.5 h-2.5 rounded-full bg-emerald-500/60" />
                </div>
                <span className="text-[11px] font-mono text-slate-400">debugduck — assistant</span>
              </div>
              <div className="flex items-center gap-3">
                <button
                  onClick={clearThread}
                  className="text-[10px] font-mono text-slate-500 hover:text-slate-300 transition-colors"
                >
                  clear
                </button>
                <button
                  onClick={() => setExpanded(false)}
                  className="text-slate-500 hover:text-white transition-colors"
                  aria-label="Collapse terminal"
                >
                  <span className="material-symbols-outlined text-[16px]">keyboard_arrow_down</span>
                </button>
              </div>
            </div>

            {/* Terminal output */}
            <div className="flex-1 overflow-y-auto px-4 py-2 custom-scrollbar font-mono text-[12px]">
              {/* Welcome message when empty */}
              {messages.length === 0 && (
                <div className="py-4">
                  <p className="text-slate-400 mb-1">DebugDuck AI Assistant v1.0</p>
                  <p className="text-slate-500 mb-3">Type a command or ask a question. Examples:</p>
                  <div className="space-y-1 mb-4">
                    <p className="text-slate-500"><span className="text-duck-accent">❯</span> what investigations are running?</p>
                    <p className="text-slate-500"><span className="text-duck-accent">❯</span> check system health</p>
                    <p className="text-slate-500"><span className="text-duck-accent">❯</span> scan prod-orders database</p>
                    <p className="text-slate-500"><span className="text-duck-accent">❯</span> show findings for INC-A3F2</p>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {QUICK_COMMANDS.map((qc) => (
                      <button
                        key={qc.label}
                        onClick={() => sendMessage(qc.cmd)}
                        className="px-2 py-1 rounded text-[10px] font-mono text-slate-400 bg-duck-card/30 border border-duck-border/30 hover:border-duck-accent/30 hover:text-duck-accent transition-all"
                      >
                        /{qc.label}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Message log */}
              {messages.length > 50 && (
                <p className="text-[9px] text-slate-600 mb-2">--- earlier output truncated ---</p>
              )}
              {displayedMessages.map((msg, i) => (
                <AssistantMessageEntry
                  key={`${msg.role}-${msg.timestamp}-${i}`}
                  message={msg}
                  onActionClick={handleActionClick}
                />
              ))}

              {/* Processing indicator */}
              {isLoading && (
                <div className="flex items-center gap-2 py-1.5 pl-5">
                  <span className="text-duck-accent text-[11px]">⟳</span>
                  <span className="text-[11px] text-slate-400">processing</span>
                  <span className="flex items-center gap-0.5">
                    <span className="w-1 h-1 rounded-full bg-duck-accent/60 animate-pulse" />
                    <span className="w-1 h-1 rounded-full bg-duck-accent/60 animate-pulse" style={{ animationDelay: '200ms' }} />
                    <span className="w-1 h-1 rounded-full bg-duck-accent/60 animate-pulse" style={{ animationDelay: '400ms' }} />
                  </span>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Command input bar — always visible */}
      <div className="border-t-2 border-b-2 border-duck-accent/30 bg-duck-card/60 px-4 py-2.5 flex items-center gap-2 shadow-[0_-2px_10px_rgba(0,0,0,0.3)]">
        <span className="text-duck-accent font-mono text-[12px] shrink-0">❯</span>
        <input
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => setExpanded(true)}
          placeholder="ask debugduck..."
          className="flex-1 bg-transparent text-[13px] font-mono text-white placeholder:text-slate-600 outline-none"
          disabled={isLoading}
          aria-label="Command input"
        />
        {input.trim() ? (
          <button
            onClick={handleSubmit}
            disabled={isLoading}
            className="text-duck-accent hover:text-white transition-colors disabled:opacity-50 font-mono text-[11px]"
            aria-label="Execute"
          >
            run ↵
          </button>
        ) : (
          <span className="text-[10px] text-slate-600 font-mono shrink-0">⌘K</span>
        )}
      </div>
    </div>
  );
};

export default AssistantDock;
