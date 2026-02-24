import React, { createContext, useContext, useState, useCallback, useRef, useEffect, useMemo } from 'react';
import type { ChatMessage, TaskEvent } from '../types';
import { sendChatMessage } from '../services/api';

interface StreamingState {
  isStreaming: boolean;
  content: string;
  messageId: string | null;
}

interface ChatContextValue {
  // State
  messages: ChatMessage[];
  isOpen: boolean;
  isStreaming: boolean;
  streamingContent: string;
  unreadCount: number;
  isWaiting: boolean;
  isSending: boolean;

  // Actions
  sendMessage: (content: string) => Promise<void>;
  toggleDrawer: () => void;
  openDrawer: () => void;
  closeDrawer: () => void;
  markRead: () => void;
  addMessage: (message: ChatMessage) => void;

  // Streaming actions (used by WebSocket handler)
  startStream: () => void;
  appendChunk: (chunk: string) => void;
  finishStream: (fullResponse: string, metadata?: ChatMessage['metadata']) => void;
}

const ChatContext = createContext<ChatContextValue | null>(null);

export function useChatContext(): ChatContextValue {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error('useChatContext must be used within ChatProvider');
  return ctx;
}

interface ChatProviderProps {
  sessionId: string | null;
  events: TaskEvent[];
  onRegisterChatHandler?: React.MutableRefObject<((msg: ChatMessage) => void) | null>;
  children: React.ReactNode;
}

export const ChatProvider: React.FC<ChatProviderProps> = ({ sessionId, events, onRegisterChatHandler, children }) => {
  const [messagesBySession, setMessagesBySession] = useState<Record<string, ChatMessage[]>>({});
  const [isOpen, setIsOpen] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const [isSending, setIsSending] = useState(false);
  const prevMessageCountRef = useRef(0);

  // Streaming state
  const [streaming, setStreaming] = useState<StreamingState>({
    isStreaming: false,
    content: '',
    messageId: null,
  });

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

  // Reset on session change
  useEffect(() => {
    setIsOpen(false);
    setUnreadCount(0);
    prevMessageCountRef.current = 0;
    setStreaming({ isStreaming: false, content: '', messageId: null });
  }, [sessionId]);

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
  }, [sessionId, addMessage]);

  // Streaming actions
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
    setIsSending(false);
  }, [sessionId, addMessage]);

  const toggleDrawer = useCallback(() => setIsOpen(prev => !prev), []);
  const openDrawer = useCallback(() => setIsOpen(true), []);
  const closeDrawer = useCallback(() => setIsOpen(false), []);
  const markRead = useCallback(() => setUnreadCount(0), []);

  const value = useMemo<ChatContextValue>(() => ({
    messages,
    isOpen,
    isStreaming: streaming.isStreaming,
    streamingContent: streaming.content,
    unreadCount,
    isWaiting,
    isSending,
    sendMessage,
    toggleDrawer,
    openDrawer,
    closeDrawer,
    markRead,
    addMessage,
    startStream,
    appendChunk,
    finishStream,
  }), [
    messages, isOpen, streaming.isStreaming, streaming.content,
    unreadCount, isWaiting, isSending, sendMessage,
    toggleDrawer, openDrawer, closeDrawer, markRead, addMessage,
    startStream, appendChunk, finishStream,
  ]);

  return (
    <ChatContext.Provider value={value}>
      {children}
    </ChatContext.Provider>
  );
};
