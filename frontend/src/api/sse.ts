/**
 * Typed Server-Sent Events (SSE) Client.
 *
 * Implements ADR-1 (W3C text/event-stream `/api/events/stream`) with automatic
 * reconnection, exponential backoff, and strongly typed event subscriptions.
 */

export interface SSEEventMap {
  "mobile.batch_received": { session_id: string; chunk_index: number; role: string; book_index: number; file_size: number };
  "mobile.committed": { session_id: string; assets_created: number };
  "asset.updated": { asset_id: string; status: string; version: number };
  "ai.progress": { article: string; progress: number; message: string };
  "ozon.status_changed": { article: string; status: string; moderation_errors?: Record<string, string> };
  "sync.progress": { store_id: string; processed: number; total: number };
  "store.switched": { active_store: string };
  "tab.opened": { tab_id: string; article: string; title: string };
  [key: string]: unknown;
}

export type SSEHandler<T = unknown> = (data: T) => void;

export class SSEClient {
  private eventSource: EventSource | null = null;
  private listeners: Map<string, Set<SSEHandler<any>>> = new Map();
  private reconnectTimeout: number | null = null;
  private backoffMs: number = 1000;
  private isExplicitlyClosed: boolean = false;
  private url: string;

  constructor(url: string = "/api/events/stream") {
    this.url = url;
  }

  public connect(): void {
    if (this.eventSource) {
      return;
    }
    this.isExplicitlyClosed = false;

    try {
      this.eventSource = new EventSource(this.url);

      this.eventSource.onopen = () => {
        this.backoffMs = 1000;
      };

      this.eventSource.onmessage = (e: MessageEvent) => {
        try {
          const parsed = JSON.parse(e.data);
          const type = parsed.event || parsed.type || "message";
          const payload = parsed.data !== undefined ? parsed.data : parsed;
          this.emit(type, payload);
        } catch {
          // Keepalive comment or raw string message
        }
      };

      this.eventSource.onerror = () => {
        this.close();
        if (!this.isExplicitlyClosed) {
          this.scheduleReconnect();
        }
      };
    } catch {
      this.scheduleReconnect();
    }
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimeout !== null) {
      return;
    }
    this.reconnectTimeout = window.setTimeout(() => {
      this.reconnectTimeout = null;
      this.backoffMs = Math.min(this.backoffMs * 1.5, 30000);
      this.connect();
    }, this.backoffMs);
  }

  public on<K extends keyof SSEEventMap>(event: K, handler: SSEHandler<SSEEventMap[K]>): () => void;
  public on(event: string, handler: SSEHandler<any>): () => void {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set());
    }
    this.listeners.get(event)!.add(handler);

    // Return unbind callback
    return () => this.off(event, handler);
  }

  public off(event: string, handler: SSEHandler<any>): void {
    const handlers = this.listeners.get(event);
    if (handlers) {
      handlers.delete(handler);
      if (handlers.size === 0) {
        this.listeners.delete(event);
      }
    }
  }

  private emit(event: string, data: unknown): void {
    const handlers = this.listeners.get(event);
    if (handlers) {
      handlers.forEach((h) => {
        try {
          h(data);
        } catch (err) {
          console.error(`Error in SSE listener for '${event}':`, err);
        }
      });
    }
  }

  public close(): void {
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
    if (this.reconnectTimeout !== null) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }
  }

  public disconnect(): void {
    this.isExplicitlyClosed = true;
    this.close();
  }
}

export const sseClient = new SSEClient();

