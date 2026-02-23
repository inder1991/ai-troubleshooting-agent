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

interface V4WebSocketHandlers {
  onTaskEvent?: (event: TaskEvent) => void;
  onChatResponse?: (message: ChatMessage) => void;
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

  const connect = useCallback(() => {
    if (!sessionIdRef.current) return;

    // Don't create duplicate connections
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) return;

    const currentSessionId = sessionIdRef.current;
    const ws = new WebSocket(`ws://localhost:8000/ws/troubleshoot/${currentSessionId}`);

    ws.onopen = () => {
      console.log(`[WS] Connected to session ${currentSessionId}`);
      const wasReconnect = reconnectAttemptsRef.current > 0;
      reconnectAttemptsRef.current = 0;
      handlersRef.current.onConnect?.();
      // Replay only missed events after reconnection (skip already-received ones)
      if (wasReconnect) {
        const alreadySeen = receivedEventCountRef.current;
        getEvents(currentSessionId).then((events) => {
          const missed = events.slice(alreadySeen);
          missed.forEach((ev) => handlersRef.current.onTaskEvent?.(ev));
          receivedEventCountRef.current = events.length;
        }).catch(() => {});
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
    // Clean up previous connection
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close();
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
