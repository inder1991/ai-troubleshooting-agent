import { useEffect, useRef, useCallback } from 'react';
import type { TaskEvent, ChatMessage, V4WebSocketMessage } from '../types';

// ===== V3 WebSocket (preserved for backward compatibility) =====

export const useWebSocket = (
  sessionId: string | null,
  onMessage: (data: Record<string, unknown>) => void
) => {
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!sessionId) return;

    const ws = new WebSocket(`ws://localhost:8000/ws/troubleshoot/${sessionId}`);

    ws.onopen = () => {
      console.log('WebSocket connected (v3)');
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        onMessage(data);
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
  }, [sessionId, onMessage]);

  return wsRef;
};

// ===== V4 WebSocket =====

interface V4WebSocketHandlers {
  onTaskEvent?: (event: TaskEvent) => void;
  onChatResponse?: (message: ChatMessage) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
  onError?: (error: Event) => void;
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
  const maxReconnectAttempts = 5;

  const connect = useCallback(() => {
    if (!sessionId) return;

    const ws = new WebSocket(`ws://localhost:8000/ws/troubleshoot/${sessionId}`);

    ws.onopen = () => {
      reconnectAttemptsRef.current = 0;
      handlersRef.current.onConnect?.();
    };

    ws.onmessage = (event) => {
      try {
        const message: V4WebSocketMessage = JSON.parse(event.data);

        switch (message.type) {
          case 'task_event':
            handlersRef.current.onTaskEvent?.(message.data as TaskEvent);
            break;
          case 'chat_response':
            handlersRef.current.onChatResponse?.(message.data as ChatMessage);
            break;
          default:
            console.warn('Unknown WebSocket message type:', message.type);
        }
      } catch (e) {
        console.error('WebSocket parse error:', e);
      }
    };

    ws.onerror = (error) => {
      handlersRef.current.onError?.(error);
    };

    ws.onclose = () => {
      handlersRef.current.onDisconnect?.();

      if (reconnectAttemptsRef.current < maxReconnectAttempts) {
        const delay = Math.min(1000 * Math.pow(2, reconnectAttemptsRef.current), 10000);
        reconnectAttemptsRef.current += 1;
        reconnectTimeoutRef.current = setTimeout(connect, delay);
      }
    };

    wsRef.current = ws;
  }, [sessionId]);

  useEffect(() => {
    connect();

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      wsRef.current?.close();
    };
  }, [connect]);

  return wsRef;
};
