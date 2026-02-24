import { useState, useCallback } from 'react';

interface StreamingState {
  isStreaming: boolean;
  content: string;
  messageId: string | null;
}

export function useStreamingMessage() {
  const [state, setState] = useState<StreamingState>({
    isStreaming: false,
    content: '',
    messageId: null,
  });

  const startStream = useCallback(() => {
    setState({
      isStreaming: true,
      content: '',
      messageId: crypto.randomUUID(),
    });
  }, []);

  const appendChunk = useCallback((chunk: string) => {
    setState(prev => ({
      ...prev,
      isStreaming: true,
      content: prev.content + chunk,
    }));
  }, []);

  const finishStream = useCallback((fullResponse: string) => {
    setState({ isStreaming: false, content: '', messageId: null });
    return fullResponse;
  }, []);

  const resetStream = useCallback(() => {
    setState({ isStreaming: false, content: '', messageId: null });
  }, []);

  return {
    ...state,
    startStream,
    appendChunk,
    finishStream,
    resetStream,
  };
}
