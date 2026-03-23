"use client";
import { useEffect, useRef, useState } from "react";

interface FeedItem {
  id: string;
  type: "activity" | "agent" | "approval" | "error" | "ping";
  message?: string;
  agent?: string;
  job_id?: string;
  timestamp: string;
}

const MAX_FEED = 50;
const RECONNECT_DELAYS = [1000, 2000, 4000, 8000, 15000]; // exponential backoff

export default function TelegramFeed() {
  const [items, setItems] = useState<FeedItem[]>([]);
  const [connected, setConnected] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const reconnectAttempt = useRef(0);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    connect();
    return () => esRef.current?.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function connect() {
    const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";
    const es = new EventSource(`${backendUrl}/office/stream`);
    esRef.current = es;

    es.onopen = () => {
      setConnected(true);
      reconnectAttempt.current = 0;
    };

    es.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.type === "ping") return;

        const item: FeedItem = {
          id: `${Date.now()}-${Math.random()}`,
          type: data.type === "agent_update" ? "agent"
               : data.type === "activity"    ? "activity"
               : "activity",
          message: data.message || formatAgentUpdate(data),
          agent: data.agent,
          job_id: data.job_id,
          timestamp: data.updated_at || data.timestamp || new Date().toISOString(),
        };

        setItems(prev => [...prev.slice(-MAX_FEED + 1), item]);
      } catch {
        // ignore parse errors
      }
    };

    es.onerror = () => {
      setConnected(false);
      es.close();
      const delay = RECONNECT_DELAYS[Math.min(reconnectAttempt.current, RECONNECT_DELAYS.length - 1)];
      reconnectAttempt.current++;
      setTimeout(connect, delay);
    };
  }

  // Auto-scroll to bottom
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [items]);

  return (
    <div className="px-border bg-pixel-panel flex flex-col h-full">
      <div className="px-titlebar justify-between">
        <span>📺 ACTIVITY FEED</span>
        <span className={`text-[8px] ${connected ? "text-pixel-green" : "text-pixel-error"}`}>
          {connected ? "● LIVE" : "○ RECONNECTING..."}
        </span>
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-0.5 min-h-0">
        {items.length === 0 && (
          <div className="text-pixel-dim text-center py-8 font-mono text-sm">
            Waiting for activity...
          </div>
        )}
        {items.map(item => (
          <FeedRow key={item.id} item={item} />
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}

function FeedRow({ item }: { item: FeedItem }) {
  const time = new Date(item.timestamp).toLocaleTimeString("en-HK", {
    hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  });

  return (
    <div className={`feed-item ${item.type} flex gap-2 items-start`}>
      <span className="text-pixel-dim text-xs shrink-0 pt-0.5">{time}</span>
      <span className="break-words">{item.message}</span>
    </div>
  );
}

function formatAgentUpdate(data: Record<string, unknown>): string {
  const agent = String(data.agent || "").replace("_", " ").toUpperCase();
  const status = String(data.status || "").toUpperCase();
  const msg = data.last_message ? ` — ${data.last_message}` : "";
  return `[${agent}] ${status}${msg}`;
}
