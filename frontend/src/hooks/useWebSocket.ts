import { useEffect, useRef } from 'react';

export const useWebSocket = (sessionId: string | null, onMessage: (data: any) => void) => {
  const wsRef = useRef<WebSocket | null>(null);
  
  useEffect(() => {
    if (!sessionId) return;
    
    const ws = new WebSocket(`ws://localhost:8000/ws/troubleshoot/${sessionId}`);
    
    ws.onopen = () => {
      console.log('✅ WebSocket connected');
    };
    
    ws.onmessage = (event) => {
      console.log('📨 RAW data:', event.data);  // ← ADD THIS FIRST
      console.log('📨 Data type:', typeof event.data);  // ← ADD THIS
      console.log('📨 Data length:', event.data.length);
      try {
        const data = JSON.parse(event.data);
        console.log('✅ Parsed successfully:', data);
        onMessage(data);
      } catch (e) {
          console.error('❌ JSON parse error:', e);
          console.error('   Raw data was:', event.data);
      }
    };
    
    ws.onerror = (error) => {
      console.error('❌ WebSocket error:', error);
    };
    
    ws.onclose = () => {
      console.log('🔌 WebSocket disconnected');
    };
    
    wsRef.current = ws;
    
    return () => {
      ws.close();
    };
  }, [sessionId, onMessage]);
  
  return wsRef;
};
