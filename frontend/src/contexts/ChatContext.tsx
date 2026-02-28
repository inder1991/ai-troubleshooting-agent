import React, { createContext, useContext, useState, useCallback, useRef, useEffect, useMemo } from 'react';
import type { ChatMessage, TaskEvent } from '../types';
import { sendChatMessage } from '../services/api';

// ─── Investigation Context (slow-moving: namespace/service/pod/cluster) ──

export interface InvestigationContextData {
  namespace: string | null;
  service: string | null;
  pod: string | null;
  cluster: string | null;
}

interface InvestigationContextValue {
  investigationContext: InvestigationContextData;
  setInvestigationContext: (ctx: InvestigationContextData) => void;
}

const InvestigationContext = createContext<InvestigationContextValue | null>(null);

export function useInvestigationContext(): InvestigationContextValue {
  const ctx = useContext(InvestigationContext);
  if (!ctx) throw new Error('useInvestigationContext must be used within ChatProvider');
  return ctx;
}

// ─── ChatUI Context (slow-moving: messages, drawer, sending) ─────────────

interface ChatUIContextValue {
  sessionId: string | null;
  messages: ChatMessage[];
  isOpen: boolean;
  unreadCount: number;
  isWaiting: boolean;
  isSending: boolean;
  sendMessage: (content: string) => Promise<void>;
  toggleDrawer: () => void;
  openDrawer: () => void;
  closeDrawer: () => void;
  markRead: () => void;
  addMessage: (message: ChatMessage) => void;
}

const ChatUIContext = createContext<ChatUIContextValue | null>(null);

export function useChatUI(): ChatUIContextValue {
  const ctx = useContext(ChatUIContext);
  if (!ctx) throw new Error('useChatUI must be used within ChatProvider');
  return ctx;
}

// ─── ChatStream Context (fast-moving: streaming tokens ~50ms) ────────────

interface ChatStreamContextValue {
  isStreaming: boolean;
  streamingContent: string;
  startStream: () => void;
  appendChunk: (chunk: string) => void;
  finishStream: (fullResponse: string, metadata?: ChatMessage['metadata']) => void;
}

const ChatStreamContext = createContext<ChatStreamContextValue | null>(null);

export function useChatStream(): ChatStreamContextValue {
  const ctx = useContext(ChatStreamContext);
  if (!ctx) throw new Error('useChatStream must be used within ChatProvider');
  return ctx;
}

// ─── Backward-compatible merged hook ─────────────────────────────────────

interface ChatContextValue extends ChatUIContextValue, ChatStreamContextValue {}

export function useChatContext(): ChatContextValue {
  const ui = useChatUI();
  const stream = useChatStream();
  return useMemo(() => ({ ...ui, ...stream }), [ui, stream]);
}

// ─── Provider Props ──────────────────────────────────────────────────────

interface ChatProviderProps {
  sessionId: string | null;
  events: TaskEvent[];
  onRegisterChatHandler?: React.MutableRefObject<((msg: ChatMessage) => void) | null>;
  onRegisterStreamStart?: React.MutableRefObject<(() => void) | null>;
  onRegisterStreamAppend?: React.MutableRefObject<((chunk: string) => void) | null>;
  onRegisterStreamFinish?: React.MutableRefObject<((full: string, meta?: ChatMessage['metadata']) => void) | null>;
  onPhaseUpdate?: (phase: string, confidence: number) => void;
  children: React.ReactNode;
}

// ─── ChatStreamProvider (inner — reads addMessage from ChatUIContext) ────

interface ChatStreamProviderProps {
  sessionId: string | null;
  onRegisterStreamStart?: React.MutableRefObject<(() => void) | null>;
  onRegisterStreamAppend?: React.MutableRefObject<((chunk: string) => void) | null>;
  onRegisterStreamFinish?: React.MutableRefObject<((full: string, meta?: ChatMessage['metadata']) => void) | null>;
  onPhaseUpdate?: (phase: string, confidence: number) => void;
  children: React.ReactNode;
}

interface StreamingState {
  isStreaming: boolean;
  content: string;
  messageId: string | null;
}

const ChatStreamProvider: React.FC<ChatStreamProviderProps> = ({
  sessionId,
  onRegisterStreamStart,
  onRegisterStreamAppend,
  onRegisterStreamFinish,
  onPhaseUpdate,
  children,
}) => {
  const { addMessage } = useChatUI();

  const [streaming, setStreaming] = useState<StreamingState>({
    isStreaming: false,
    content: '',
    messageId: null,
  });

  // Reset on session change
  useEffect(() => {
    setStreaming({ isStreaming: false, content: '', messageId: null });
  }, [sessionId]);

  const startStream = useCallback(() => {
    setStreaming({
      isStreaming: true,
      content: '',
      messageId: crypto.randomUUID(),
    });
  }, []);

  const appendChunk = useCallback((chunk: string) => {
    setStreaming(prev => ({
      ...prev,
      isStreaming: true,
      content: prev.content + chunk,
    }));
  }, []);

  const finishStream = useCallback((fullResponse: string, metadata?: ChatMessage['metadata']) => {
    if (!sessionId) return;
    const msg: ChatMessage = {
      role: 'assistant',
      content: fullResponse,
      timestamp: new Date().toISOString(),
      metadata,
    };
    addMessage(msg);
    setStreaming({ isStreaming: false, content: '', messageId: null });
  }, [sessionId, addMessage]);

  // Register streaming handlers for parent (WebSocket bridge)
  const streamStartedRef = useRef(false);
  useEffect(() => {
    if (onRegisterStreamStart) {
      onRegisterStreamStart.current = () => {
        if (!streamStartedRef.current) {
          streamStartedRef.current = true;
          startStream();
        }
      };
    }
    if (onRegisterStreamAppend) {
      onRegisterStreamAppend.current = appendChunk;
    }
    if (onRegisterStreamFinish) {
      onRegisterStreamFinish.current = (full, meta) => {
        streamStartedRef.current = false;
        finishStream(full, meta);
        if (onPhaseUpdate && meta?.newPhase) {
          onPhaseUpdate(meta.newPhase, meta.newConfidence ?? 0);
        }
      };
    }
    return () => {
      if (onRegisterStreamStart) onRegisterStreamStart.current = null;
      if (onRegisterStreamAppend) onRegisterStreamAppend.current = null;
      if (onRegisterStreamFinish) onRegisterStreamFinish.current = null;
    };
  }, [startStream, appendChunk, finishStream, onRegisterStreamStart, onRegisterStreamAppend, onRegisterStreamFinish, onPhaseUpdate]);

  const value = useMemo<ChatStreamContextValue>(() => ({
    isStreaming: streaming.isStreaming,
    streamingContent: streaming.content,
    startStream,
    appendChunk,
    finishStream,
  }), [streaming.isStreaming, streaming.content, startStream, appendChunk, finishStream]);

  return (
    <ChatStreamContext.Provider value={value}>
      {children}
    </ChatStreamContext.Provider>
  );
};

// ─── ChatUIProvider (outer — slow-moving state) ──────────────────────────

export const ChatProvider: React.FC<ChatProviderProps> = ({
  sessionId,
  events,
  onRegisterChatHandler,
  onRegisterStreamStart,
  onRegisterStreamAppend,
  onRegisterStreamFinish,
  onPhaseUpdate,
  children,
}) => {
  const [messagesBySession, setMessagesBySession] = useState<Record<string, ChatMessage[]>>({});
  const [isOpen, setIsOpen] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const [isSending, setIsSending] = useState(false);
  const prevMessageCountRef = useRef(0);

  // Investigation context — set by InvestigationView with real namespace/service/pod
  const [investigationCtx, setInvestigationCtx] = useState<InvestigationContextData>({
    namespace: null,
    service: null,
    pod: null,
    cluster: null,
  });

  const investigationValue = useMemo<InvestigationContextValue>(() => ({
    investigationContext: investigationCtx,
    setInvestigationContext: setInvestigationCtx,
  }), [investigationCtx]);

  const messages = useMemo(
    () => (sessionId ? messagesBySession[sessionId] || [] : []),
    [sessionId, messagesBySession]
  );

  // Detect if Foreman needs input
  const isWaiting = useMemo(() => {
    const assistantMsgs = messages.filter(m => m.role === 'assistant');
    if (!assistantMsgs.length) return false;
    const last = assistantMsgs[assistantMsgs.length - 1];
    return last.content.trim().endsWith('?') ||
      /\b(confirm|approve|proceed|rollback|input needed)\b/i.test(last.content);
  }, [messages]);

  // Unread tracking
  useEffect(() => {
    const count = messages.length;
    if (isOpen) {
      setUnreadCount(0);
    } else if (count > prevMessageCountRef.current) {
      const newMsgs = messages.slice(prevMessageCountRef.current);
      const assistantCount = newMsgs.filter(m => m.role === 'assistant').length;
      setUnreadCount(c => c + assistantCount);
    }
    prevMessageCountRef.current = count;
  }, [messages, isOpen]);

  // Reset on session change — clear stale messages view state
  useEffect(() => {
    setIsOpen(false);
    setUnreadCount(0);
    prevMessageCountRef.current = 0;
    // Reset message count ref to current session's message count
    // to prevent flash of old session's messages
    if (sessionId) {
      prevMessageCountRef.current = (messagesBySession[sessionId] || []).length;
    }
  }, [sessionId]); // eslint-disable-line react-hooks/exhaustive-deps

  const addMessage = useCallback((message: ChatMessage) => {
    if (!sessionId) return;
    setMessagesBySession(prev => ({
      ...prev,
      [sessionId]: [...(prev[sessionId] || []), message],
    }));
  }, [sessionId]);

  // Register addMessage handler for parent (WebSocket bridge)
  useEffect(() => {
    if (onRegisterChatHandler) {
      onRegisterChatHandler.current = addMessage;
    }
    return () => {
      if (onRegisterChatHandler) {
        onRegisterChatHandler.current = null;
      }
    };
  }, [addMessage, onRegisterChatHandler]);

  const sendMessage = useCallback(async (content: string) => {
    if (!sessionId || !content.trim()) return;

    const userMsg: ChatMessage = {
      role: 'user',
      content: content.trim(),
      timestamp: new Date().toISOString(),
    };
    addMessage(userMsg);
    setIsSending(true);

    try {
      const response = await sendChatMessage(sessionId, content.trim());
      addMessage(response);
      if (onPhaseUpdate && response.metadata?.newPhase) {
        onPhaseUpdate(response.metadata.newPhase, response.metadata.newConfidence ?? 0);
      }
    } catch (err) {
      const errorMsg: ChatMessage = {
        role: 'assistant',
        content: `Error: ${err instanceof Error ? err.message : 'Failed to send message'}`,
        timestamp: new Date().toISOString(),
        metadata: { type: 'error' },
      };
      addMessage(errorMsg);
    } finally {
      setIsSending(false);
    }
  }, [sessionId, addMessage, onPhaseUpdate]);

  const toggleDrawer = useCallback(() => setIsOpen(prev => !prev), []);
  const openDrawer = useCallback(() => setIsOpen(true), []);
  const closeDrawer = useCallback(() => setIsOpen(false), []);
  const markRead = useCallback(() => setUnreadCount(0), []);

  const uiValue = useMemo<ChatUIContextValue>(() => ({
    sessionId,
    messages,
    isOpen,
    unreadCount,
    isWaiting,
    isSending,
    sendMessage,
    toggleDrawer,
    openDrawer,
    closeDrawer,
    markRead,
    addMessage,
  }), [
    sessionId, messages, isOpen, unreadCount, isWaiting, isSending,
    sendMessage, toggleDrawer, openDrawer, closeDrawer, markRead, addMessage,
  ]);

  return (
    <ChatUIContext.Provider value={uiValue}>
      <InvestigationContext.Provider value={investigationValue}>
        <ChatStreamProvider
          sessionId={sessionId}
          onRegisterStreamStart={onRegisterStreamStart}
          onRegisterStreamAppend={onRegisterStreamAppend}
          onRegisterStreamFinish={onRegisterStreamFinish}
          onPhaseUpdate={onPhaseUpdate}
        >
          {children}
        </ChatStreamProvider>
      </InvestigationContext.Provider>
    </ChatUIContext.Provider>
  );
};
