import { useState, useCallback, useRef } from 'react';
import { API_BASE_URL } from '../services/api';

export interface AssistantMessage {
  role: 'user' | 'assistant';
  content: string;
  actions?: AssistantAction[];
  timestamp: string;
}

export interface AssistantAction {
  type: 'navigate' | 'download_report' | 'start_investigation';
  page?: string;
  session_id?: string;
  capability?: string;
  service_name?: string;
}

interface UseAssistantChatOptions {
  onNavigate?: (page: string) => void;
  onStartInvestigation?: (capability: string, serviceName?: string) => void;
  onDownloadReport?: (sessionId: string) => void;
}

export function useAssistantChat(options: UseAssistantChatOptions = {}) {
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const threadIdRef = useRef('default');

  const sendMessage = useCallback(async (text: string) => {
    if (!text.trim() || isLoading) return;

    const userMsg: AssistantMessage = {
      role: 'user',
      content: text.trim(),
      timestamp: new Date().toISOString(),
    };
    setMessages(prev => [...prev, userMsg]);
    setIsLoading(true);

    try {
      const response = await fetch(`${API_BASE_URL}/api/v4/assistant/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text.trim(),
          thread_id: threadIdRef.current,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to get response');
      }

      const data = await response.json();

      const assistantMsg: AssistantMessage = {
        role: 'assistant',
        content: data.response,
        actions: data.actions,
        timestamp: new Date().toISOString(),
      };
      setMessages(prev => [...prev, assistantMsg]);

      // Execute frontend actions
      for (const action of data.actions || []) {
        if (action.type === 'navigate' && options.onNavigate) {
          options.onNavigate(action.page);
        } else if (action.type === 'start_investigation' && options.onStartInvestigation) {
          options.onStartInvestigation(action.capability, action.service_name);
        } else if (action.type === 'download_report' && options.onDownloadReport) {
          options.onDownloadReport(action.session_id);
        }
      }
    } catch {
      const errorMsg: AssistantMessage = {
        role: 'assistant',
        content: 'Sorry, something went wrong. Please try again.',
        timestamp: new Date().toISOString(),
      };
      setMessages(prev => [...prev, errorMsg]);
    } finally {
      setIsLoading(false);
    }
  }, [isLoading, options]);

  const clearThread = useCallback(async () => {
    setMessages([]);
    try {
      await fetch(`${API_BASE_URL}/api/v4/assistant/thread/${threadIdRef.current}`, {
        method: 'DELETE',
      });
    } catch { /* silent */ }
  }, []);

  return { messages, isLoading, sendMessage, clearThread };
}
