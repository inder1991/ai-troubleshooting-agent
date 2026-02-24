import React, { useRef, useState, useEffect, useMemo, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Check, HelpCircle, XCircle, GitBranch, MessageCircle, SkipForward } from 'lucide-react';
import { drawerVariants, backdropVariants } from '../../styles/chat-animations';
import { useChatContext } from '../../contexts/ChatContext';
import MarkdownBubble from './MarkdownBubble';
import ChatInputArea from './ChatInputArea';
import ActionChip from './ActionChip';
import type { ChatMessage } from '../../types';

// ─── Action Chip Derivation ─────────────────────────────────────────────

interface DerivedChip {
  label: string;
  icon: React.ComponentType<{ size: number | string }>;
  variant: 'primary' | 'warning' | 'danger';
  action: string;
}

function deriveActionChips(message: ChatMessage | undefined): DerivedChip[] {
  if (!message || message.role !== 'assistant') return [];
  const content = message.content;
  const meta = message.metadata;

  // Purpose-built chips for specific metadata types
  if (meta?.type === 'code_agent_question') {
    return [
      { label: 'Answer', icon: MessageCircle, variant: 'primary', action: '' },
      { label: 'Skip', icon: SkipForward, variant: 'warning', action: 'skip' },
    ];
  }

  if (meta?.type === 'repo_mismatch') {
    return [
      { label: 'Switch Repo', icon: GitBranch, variant: 'primary', action: 'confirm' },
      { label: 'Keep Current', icon: Check, variant: 'warning', action: 'keep' },
    ];
  }

  if (meta?.type === 'fix_proposal') {
    return [
      { label: 'Approve Fix', icon: Check, variant: 'primary', action: 'approve' },
      { label: 'Request Changes', icon: HelpCircle, variant: 'warning', action: 'request_changes' },
      { label: 'Reject', icon: XCircle, variant: 'danger', action: 'reject' },
    ];
  }

  // Generic question fallback
  if (content.trim().endsWith('?')) {
    return [
      { label: 'Yes', icon: Check, variant: 'primary', action: 'yes' },
      { label: 'No', icon: XCircle, variant: 'danger', action: 'no' },
      { label: 'More Info', icon: HelpCircle, variant: 'warning', action: 'more_info' },
    ];
  }

  return [];
}

// ─── ChatDrawer Component ────────────────────────────────────────────────

const ChatDrawer: React.FC = () => {
  const {
    messages,
    isOpen,
    isStreaming,
    streamingContent,
    isWaiting,
    isSending,
    sendMessage,
    closeDrawer,
  } = useChatContext();

  const scrollRef = useRef<HTMLDivElement>(null);
  const [userScrolled, setUserScrolled] = useState(false);

  // Track if user manually scrolled up
  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const isAtBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    setUserScrolled(!isAtBottom);
  }, []);

  // CRITICAL: Aggressive auto-scroll — triggers on BOTH messages.length AND streamingContent
  useEffect(() => {
    if (!userScrolled && scrollRef.current) {
      scrollRef.current.scrollTo({
        top: scrollRef.current.scrollHeight,
        behavior: 'smooth',
      });
    }
  }, [messages.length, streamingContent, userScrolled]);

  // Focus input when drawer opens
  useEffect(() => {
    if (isOpen) {
      setUserScrolled(false);
    }
  }, [isOpen]);

  // Action chips from last assistant message
  const lastAssistantMsg = useMemo(() => {
    const assistantMsgs = messages.filter(m => m.role === 'assistant');
    return assistantMsgs[assistantMsgs.length - 1];
  }, [messages]);

  const actionChips = useMemo(() => deriveActionChips(lastAssistantMsg), [lastAssistantMsg]);

  const handleQuickAction = useCallback((action: string) => {
    if (!action) return; // Empty action = focus input (e.g. "Answer" chip)
    sendMessage(action);
  }, [sendMessage]);

  return (
    <AnimatePresence mode="wait">
      {isOpen && (
        <>
          {/* Backdrop — z-[55] */}
          <motion.div
            key="drawer-backdrop"
            variants={backdropVariants}
            initial="hidden"
            animate="visible"
            exit="exit"
            className="fixed inset-0 top-16 z-[55] bg-black/10 backdrop-blur-[2px] pointer-events-none"
          />

          {/* Drawer — z-[60], responsive width */}
          <motion.div
            key="chat-drawer"
            variants={drawerVariants}
            initial="hidden"
            animate="visible"
            exit="exit"
            className={`fixed top-16 right-0 bottom-0 z-[60] w-full sm:w-[420px] max-w-[100vw] flex flex-col bg-slate-900/95 backdrop-blur-xl border-l-2 ${
              isWaiting ? 'border-amber-500/40' : 'border-cyan-500/20'
            }`}
          >
            {/* Header */}
            <div className="shrink-0 flex items-center gap-2 px-4 py-3 border-b border-slate-800/50">
              <span
                className="material-symbols-outlined text-cyan-400"
                style={{ fontFamily: 'Material Symbols Outlined', fontSize: '18px' }}
              >
                auto_stories
              </span>
              <span className="text-sm font-mono text-slate-300 flex-1">Mission_Log.v7</span>
              <span className="w-1.5 h-1.5 rounded-full bg-cyan-500 animate-pulse" />
              <button
                onClick={closeDrawer}
                className="p-1 rounded hover:bg-slate-800 text-slate-500 hover:text-slate-300 transition-colors"
                title="Close"
              >
                <span
                  className="material-symbols-outlined"
                  style={{ fontFamily: 'Material Symbols Outlined', fontSize: '18px' }}
                >
                  close
                </span>
              </button>
            </div>

            {/* Waiting Banner */}
            {isWaiting && (
              <div className="shrink-0 flex items-center gap-2 px-4 py-2 bg-amber-500/10 border-b border-amber-500/20">
                <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
                <span className="text-[11px] text-amber-400 font-mono">Foreman awaiting operator input</span>
              </div>
            )}

            {/* Messages Area */}
            <div
              ref={scrollRef}
              onScroll={handleScroll}
              className="flex-1 overflow-y-auto px-3 py-3 custom-scrollbar"
            >
              {messages.length === 0 && !isStreaming ? (
                <div className="flex flex-col items-center justify-center h-full text-slate-600 gap-3">
                  <span
                    className="material-symbols-outlined"
                    style={{ fontFamily: 'Material Symbols Outlined', fontSize: '40px' }}
                  >
                    auto_stories
                  </span>
                  <span className="text-sm font-mono">Mission log empty</span>
                  <span className="text-[11px] text-slate-700">Ask the crew anything to begin</span>
                </div>
              ) : (
                <>
                  {messages.map((msg, i) => (
                    <MarkdownBubble key={`msg-${i}`} message={msg} />
                  ))}

                  {/* Streaming bubble */}
                  {isStreaming && streamingContent && (
                    <MarkdownBubble
                      message={{
                        role: 'assistant',
                        content: streamingContent,
                        timestamp: new Date().toISOString(),
                      }}
                      isStreaming
                      streamingContent={streamingContent}
                    />
                  )}

                  {/* Sending indicator (non-streaming fallback) */}
                  {isSending && !isStreaming && (
                    <div className="flex items-center gap-2 px-3 py-2 text-[11px] text-cyan-500/60">
                      <span className="w-1.5 h-1.5 rounded-full bg-cyan-500 animate-pulse" />
                      <span className="font-mono">Processing...</span>
                    </div>
                  )}
                </>
              )}
            </div>

            {/* Action Chips Ribbon */}
            {actionChips.length > 0 && !isSending && (
              <div className="shrink-0 flex flex-wrap gap-2 px-3 py-2 border-t border-slate-800/50">
                {actionChips.map((chip) => (
                  <ActionChip
                    key={chip.action}
                    label={chip.label}
                    icon={chip.icon}
                    variant={chip.variant}
                    onClick={() => handleQuickAction(chip.action)}
                  />
                ))}
              </div>
            )}

            {/* Input Area */}
            <ChatInputArea
              onSend={sendMessage}
              disabled={isSending}
              onEscDrawer={closeDrawer}
            />
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
};

export default ChatDrawer;
