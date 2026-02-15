import React, { useState, useRef, useEffect } from 'react';
import type { ChatMessage as ChatMessageType } from '../../types';
import { sendChatMessage } from '../../services/api';
import ChatMessage from './ChatMessage';

interface ChatTabProps {
  sessionId: string;
  messages: ChatMessageType[];
  onNewMessage: (message: ChatMessageType) => void;
}

const ChatTab: React.FC<ChatTabProps> = ({ sessionId, messages, onNewMessage }) => {
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  useEffect(() => {
    inputRef.current?.focus();
  }, [sessionId]);

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || sending) return;

    const userMessage: ChatMessageType = {
      role: 'user',
      content: trimmed,
      timestamp: new Date().toISOString(),
    };
    onNewMessage(userMessage);
    setInput('');
    setSending(true);

    try {
      const response = await sendChatMessage(sessionId, trimmed);
      // If the HTTP response contains a direct reply, add it.
      // WebSocket chat_response messages are handled by the parent.
      if (response && response.content) {
        onNewMessage(response);
      }
    } catch (err) {
      const errorMessage: ChatMessageType = {
        role: 'assistant',
        content: `Error: ${err instanceof Error ? err.message : 'Failed to send message'}`,
        timestamp: new Date().toISOString(),
      };
      onNewMessage(errorMessage);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-2">
        {messages.length === 0 ? (
          <div className="flex items-center justify-center h-full text-gray-500">
            <div className="text-center">
              <p className="text-lg mb-2">Chat with the AI SRE</p>
              <p className="text-sm">Ask questions about the diagnosis or request further investigation.</p>
            </div>
          </div>
        ) : (
          messages.map((msg, idx) => (
            <ChatMessage key={`${msg.timestamp}-${idx}`} message={msg} />
          ))
        )}
        {sending && (
          <div className="flex justify-start mb-4">
            <div className="bg-gray-800 border border-gray-700 rounded-lg px-4 py-3">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse" />
                <span className="text-sm text-gray-400">Thinking...</span>
              </div>
            </div>
          </div>
        )}
      </div>

      <form
        onSubmit={handleSend}
        className="border-t border-gray-700 p-4 flex gap-3 bg-gray-900"
      >
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about the diagnosis..."
          disabled={sending}
          className="flex-1 px-4 py-2 bg-gray-800 border border-gray-600 rounded-lg text-white text-sm focus:border-blue-500 focus:outline-none disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={sending || !input.trim()}
          className="px-6 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded-lg text-sm font-medium transition-colors"
        >
          Send
        </button>
      </form>
    </div>
  );
};

export default ChatTab;
