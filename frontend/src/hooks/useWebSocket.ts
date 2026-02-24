import { useEffect, useRef, useCallback } from 'react';
import type { TaskEvent, ChatMessage } from '../types';
import { getEvents } from '../services/api';

// ===== V3 WebSocket (preserved for backward compatibility) =====

export const useWebSocket = (
  sessionId: string | null,
  onMessage: (data: Record<string, unknown>) => void
) => {
  const wsRef = useRef<WebSocket | null>(null);
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  useEffect(() => {
    if (!sessionId) return;

    const ws = new WebSocket(`ws://localhost:8000/ws/troubleshoot/${sessionId}`);

    ws.onopen = () => {
      console.log('WebSocket connected (v3)');
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        onMessageRef.current(data);
      } catch (e) {
        console.error('WebSocket JSON parse error:', e);
      }
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    ws.onclose = () => {
      console.log('WebSocket disconnected (v3)');
    };

    wsRef.current = ws;

    return () => {
      ws.close();
    };
  }, [sessionId]);

  return wsRef;
};

// ===== V4 WebSocket =====

export interface ChatStreamEndPayload {
  content: string;
  done: true;
  full_response: string;
  phase?: string;
  confidence?: number;
}

interface V4WebSocketHandlers {
  onTaskEvent?: (event: TaskEvent) => void;
  onChatResponse?: (message: ChatMessage) => void;
  onChatChunk?: (chunk: string) => void;
  onChatStreamEnd?: (payload: ChatStreamEndPayload) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
  onError?: (error: Event) => void;
  onMaxReconnectsExhausted?: () => void;
}

export const useWebSocketV4 = (
  sessionId: string | null,
  handlers: V4WebSocketHandlers
) => {
  const wsRef = useRef<WebSocket | null>(null);
  const handlersRef = useRef(handlers);
  handlersRef.current = handlers;

  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const maxReconnectAttempts = 10;
  const sessionIdRef = useRef(sessionId);
  sessionIdRef.current = sessionId;
  const receivedEventCountRef = useRef(0);

  // C4: Track whether we're replaying events to prevent duplicates
  const replayingRef = useRef(false);

  const connect = useCallback(() => {
    if (!sessionIdRef.current) return;

    // M6: Don't create duplicate connections — check both OPEN and CONNECTING states
    if (wsRef.current && (wsRef.current.readyState === WebSocket.OPEN || wsRef.current.readyState === WebSocket.CONNECTING)) return;

    const currentSessionId = sessionIdRef.current;
    const ws = new WebSocket(`ws://localhost:8000/ws/troubleshoot/${currentSessionId}`);

    ws.onopen = () => {
      console.log(`[WS] Connected to session ${currentSessionId}`);
      const wasReconnect = reconnectAttemptsRef.current > 0;
      reconnectAttemptsRef.current = 0;
      handlersRef.current.onConnect?.();
      // C4: Replay only truly missed events after reconnection
      if (wasReconnect) {
        const alreadySeen = receivedEventCountRef.current;
        replayingRef.current = true;
        getEvents(currentSessionId).then((events) => {
          // Only replay events we haven't seen — account for events received
          // via live WS between reconnect and replay response
          const currentCount = receivedEventCountRef.current;
          const missed = events.slice(alreadySeen);
          const trulyMissed = missed.slice(0, Math.max(0, missed.length - (currentCount - alreadySeen)));
          trulyMissed.forEach((ev) => handlersRef.current.onTaskEvent?.(ev));
          receivedEventCountRef.current = Math.max(currentCount, events.length);
          replayingRef.current = false;
        }).catch(() => { replayingRef.current = false; });
      }
    };

    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        const type = message.type;
        const data = message.data;

        switch (type) {
          case 'task_event':
            if (data) {
              // Ensure session_id is always present
              const taskEvent: TaskEvent = {
                ...data,
                session_id: data.session_id || currentSessionId,
              };
              receivedEventCountRef.current += 1;
              handlersRef.current.onTaskEvent?.(taskEvent);
            }
            break;
          case 'chat_response':
            if (data) {
              handlersRef.current.onChatResponse?.(data as ChatMessage);
            }
            break;
          case 'chat_chunk':
            if (data) {
              if ((data as Record<string, unknown>).done) {
                handlersRef.current.onChatStreamEnd?.(data as ChatStreamEndPayload);
              } else {
                handlersRef.current.onChatChunk?.((data as Record<string, unknown>).content as string);
              }
            }
            break;
          case 'connected':
            // Server handshake acknowledged
            console.log(`[WS] Handshake complete for ${currentSessionId}`);
            break;
          default:
            // Try to handle as a raw task event (backward compat)
            if (message.agent_name && message.event_type) {
              const rawEvent: TaskEvent = {
                ...message,
                session_id: message.session_id || currentSessionId,
              };
              handlersRef.current.onTaskEvent?.(rawEvent);
            }
        }
      } catch (e) {
        console.error('[WS] Parse error:', e);
      }
    };

    ws.onerror = (error) => {
      console.error(`[WS] Error for session ${currentSessionId}:`, error);
      handlersRef.current.onError?.(error);
    };

    ws.onclose = (event) => {
      console.log(`[WS] Disconnected from session ${currentSessionId} (code: ${event.code})`);
      handlersRef.current.onDisconnect?.();

      // Only reconnect if this is still the active session
      if (sessionIdRef.current === currentSessionId && reconnectAttemptsRef.current < maxReconnectAttempts) {
        const delay = Math.min(1000 * Math.pow(2, reconnectAttemptsRef.current), 15000);
        reconnectAttemptsRef.current += 1;
        console.log(`[WS] Reconnecting in ${delay}ms (attempt ${reconnectAttemptsRef.current}/${maxReconnectAttempts})`);
        reconnectTimeoutRef.current = setTimeout(connect, delay);
      } else if (sessionIdRef.current === currentSessionId && reconnectAttemptsRef.current >= maxReconnectAttempts) {
        console.warn(`[WS] Max reconnect attempts (${maxReconnectAttempts}) exhausted`);
        handlersRef.current.onMaxReconnectsExhausted?.();
      }
    };

    wsRef.current = ws;
  }, []);

  useEffect(() => {
    // M6: Clean up previous connection — handle both OPEN and CLOSING states
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    if (wsRef.current) {
      // Force-close even if in CLOSING state to prevent event leaks from old session
      if (wsRef.current.readyState === WebSocket.OPEN || wsRef.current.readyState === WebSocket.CONNECTING) {
        wsRef.current.close();
      }
      wsRef.current = null;
    }

    reconnectAttemptsRef.current = 0;
    receivedEventCountRef.current = 0;

    if (sessionId) {
      connect();
    }

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      wsRef.current?.close();
    };
  }, [sessionId, connect]);

  return wsRef;
};
