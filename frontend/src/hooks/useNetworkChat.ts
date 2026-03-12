import { useState, useCallback, useRef, useEffect } from 'react';
import { API_BASE_URL } from '../services/api';

export interface NetworkChatMessage {
  message_id?: string;
  role: 'user' | 'assistant' | 'tool';
  content: string;
  timestamp: string;
  tool_name?: string;
  tool_calls?: { name: string; blocked?: boolean; reason?: string }[];
}

interface UseNetworkChatOptions {
  view: string;
  userId?: string;
}

export function useNetworkChat({ view, userId = 'default' }: UseNetworkChatOptions) {
  const [messages, setMessages] = useState<NetworkChatMessage[]>([]);
  const [isSending, setIsSending] = useState(false);
  const [threadId, setThreadId] = useState<string | null>(() => {
    try {
      return localStorage.getItem(`network-chat-thread-${view}`);
    } catch {
      return null;
    }
  });
  const [activeToolCalls, setActiveToolCalls] = useState<string[]>([]);
  const abortRef = useRef<AbortController | null>(null);

  // Load existing messages when thread exists
  useEffect(() => {
    if (!threadId) return;
    const load = async () => {
      try {
        const resp = await fetch(
          `${API_BASE_URL}/api/v4/network/chat/threads/${threadId}/messages?limit=50`
        );
        if (resp.ok) {
          const data = await resp.json();
          setMessages(
            data.map((m: Record<string, unknown>) => ({
              message_id: m.message_id,
              role: m.role as 'user' | 'assistant' | 'tool',
              content: m.content as string,
              timestamp: m.timestamp as string,
              tool_name: m.tool_name as string | undefined,
            }))
          );
        }
      } catch {
        // silent -- start fresh
      }
    };
    load();
  }, [threadId]);

  const sendMessage = useCallback(
    async (content: string, visibleData: Record<string, unknown> = {}) => {
      if (!content.trim() || isSending) return;

      const userMsg: NetworkChatMessage = {
        role: 'user',
        content: content.trim(),
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, userMsg]);
      setIsSending(true);

      try {
        abortRef.current = new AbortController();
        const resp = await fetch(`${API_BASE_URL}/api/v4/network/chat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message: content.trim(),
            view,
            visible_data_summary: visibleData,
            thread_id: threadId,
            user_id: userId,
          }),
          signal: abortRef.current.signal,
        });

        if (!resp.ok) {
          throw new Error(await resp.text().catch(() => 'Request failed'));
        }

        const data = await resp.json();

        // Persist thread ID
        if (data.thread_id && data.thread_id !== threadId) {
          setThreadId(data.thread_id);
          try {
            localStorage.setItem(`network-chat-thread-${view}`, data.thread_id);
          } catch {
            /* noop */
          }
        }

        // Track tool calls
        if (data.tool_calls?.length) {
          setActiveToolCalls(
            data.tool_calls.map((tc: { name: string }) => tc.name)
          );
        }

        const assistantMsg: NetworkChatMessage = {
          role: 'assistant',
          content: data.response,
          timestamp: new Date().toISOString(),
          tool_calls: data.tool_calls,
        };
        setMessages((prev) => [...prev, assistantMsg]);
        setActiveToolCalls([]);
      } catch (err) {
        if ((err as Error).name === 'AbortError') return;
        const errorMsg: NetworkChatMessage = {
          role: 'assistant',
          content: `Error: ${err instanceof Error ? err.message : 'Failed to send message'}`,
          timestamp: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, errorMsg]);
      } finally {
        setIsSending(false);
      }
    },
    [view, threadId, userId, isSending]
  );

  const clearThread = useCallback(() => {
    setMessages([]);
    setThreadId(null);
    try {
      localStorage.removeItem(`network-chat-thread-${view}`);
    } catch {
      /* noop */
    }
  }, [view]);

  return {
    messages,
    isSending,
    threadId,
    activeToolCalls,
    sendMessage,
    clearThread,
  };
}
