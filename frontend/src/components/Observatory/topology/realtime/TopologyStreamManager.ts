/**
 * TopologyStreamManager — manages a WebSocket connection to the v5
 * topology stream endpoint, dispatching parsed delta events to a
 * caller-supplied callback with automatic reconnection + exponential backoff.
 */

export interface TopologyDelta {
  event_type: string;
  entity_id: string;
  entity_type: 'node' | 'edge';
  data: Record<string, any>;
  changes: Record<string, { old: any; new: any }>;
  timestamp: string;
}

export class TopologyStreamManager {
  private ws: WebSocket | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectDelay = 3000;
  private maxReconnectDelay = 30000;
  private onDelta: (delta: TopologyDelta) => void;
  private url: string = '';

  constructor(onDelta: (delta: TopologyDelta) => void) {
    this.onDelta = onDelta;
  }

  connect(url: string): void {
    this.url = url;
    this._connect();
  }

  private _connect(): void {
    try {
      this.ws = new WebSocket(this.url);

      this.ws.onmessage = (event: MessageEvent) => {
        try {
          const delta: TopologyDelta = JSON.parse(event.data);
          this.onDelta(delta);
        } catch (e) {
          console.warn('Failed to parse topology delta:', e);
        }
      };

      this.ws.onopen = () => {
        this.reconnectDelay = 3000; // Reset on successful connect
      };

      this.ws.onclose = () => {
        this._scheduleReconnect();
      };

      this.ws.onerror = () => {
        this.ws?.close();
      };
    } catch (e) {
      this._scheduleReconnect();
    }
  }

  private _scheduleReconnect(): void {
    if (this.reconnectTimer) return;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this._connect();
      // Exponential backoff
      this.reconnectDelay = Math.min(
        this.reconnectDelay * 1.5,
        this.maxReconnectDelay,
      );
    }, this.reconnectDelay);
  }

  disconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.onclose = null; // Prevent reconnect
      this.ws.close();
      this.ws = null;
    }
  }

  get connected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}
