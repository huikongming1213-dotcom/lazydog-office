"use client";
import { useEffect, useState } from "react";
import AgentDesk, { AgentStatus } from "./AgentDesk";

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

interface AgentState {
  status: AgentStatus;
  job_id?: string;
  last_message?: string;
  last_output?: Record<string, unknown>;
  updated_at?: string;
}

interface OfficeState {
  agents: Record<string, AgentState>;
}

const AGENT_META = {
  trend_analyst: {
    name: "Aria",
    role: "趨勢分析師",
    emoji: "🐨",
    deskEmoji: "📊",
  },
  copywriter: {
    name: "Max",
    role: "文案師",
    emoji: "🐨",
    deskEmoji: "✍️",
  },
  image_gen: {
    name: "Zoe",
    role: "視覺總監",
    emoji: "🐨",
    deskEmoji: "🎨",
  },
  supervisor: {
    name: "Chief",
    role: "主管",
    emoji: "🐻",
    deskEmoji: "👔",
  },
};

const DEFAULT_STATE: OfficeState = {
  agents: Object.fromEntries(
    Object.keys(AGENT_META).map(k => [k, { status: "idle" }])
  ),
};

export default function PixelOffice() {
  const [state, setState] = useState<OfficeState>(DEFAULT_STATE);

  // Step 1: Fetch current state snapshot on mount
  useEffect(() => {
    fetch(`${BACKEND}/office/state/current`)
      .then(r => r.json())
      .then(data => setState({ agents: data.agents }))
      .catch(() => {}); // graceful — SSE will fill in
  }, []);

  // Step 2: Subscribe to SSE for live updates
  useEffect(() => {
    const reconnectDelays = [1000, 2000, 4000, 8000, 15000];
    let attempt = 0;
    let es: EventSource;

    function connect() {
      es = new EventSource(`${BACKEND}/office/stream`);

      es.onopen = () => { attempt = 0; };

      es.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);

          if (data.type === "init") {
            // Full state snapshot on (re)connect
            setState({ agents: data.agents });
            return;
          }

          if (data.type === "agent_update") {
            setState(prev => ({
              agents: {
                ...prev.agents,
                [data.agent]: {
                  status: data.status,
                  job_id: data.job_id,
                  last_message: data.last_message,
                  last_output: data.last_output,
                  updated_at: data.updated_at,
                },
              },
            }));
          }
        } catch {
          // ignore
        }
      };

      es.onerror = () => {
        es.close();
        const delay = reconnectDelays[Math.min(attempt, reconnectDelays.length - 1)];
        attempt++;
        setTimeout(connect, delay);
      };
    }

    connect();
    return () => es?.close();
  }, []);

  const getAgent = (key: string) => ({
    ...(AGENT_META[key as keyof typeof AGENT_META] || { name: key, role: key, emoji: "🤖", deskEmoji: "💻" }),
    ...(state.agents[key] || { status: "idle" as AgentStatus }),
  });

  return (
    <div className="px-border bg-pixel-panel">
      {/* Office title bar */}
      <div className="px-titlebar text-[8px] justify-center">
        🖥 LAZYDOG.AI VIRTUAL OFFICE
      </div>

      {/* Floor plan */}
      <div className="p-6 bg-[#0d1117] relative">
        {/* Floor grid */}
        <div
          className="absolute inset-0 opacity-10"
          style={{
            backgroundImage: "linear-gradient(#334 1px, transparent 1px), linear-gradient(90deg, #334 1px, transparent 1px)",
            backgroundSize: "32px 32px",
          }}
        />

        {/* Agent row 1: Analyst, Writer, Artist */}
        <div className="flex gap-8 justify-center mb-8 relative z-10">
          {["trend_analyst", "copywriter", "image_gen"].map(key => {
            const a = getAgent(key);
            return (
              <AgentDesk
                key={key}
                name={a.name}
                role={a.role}
                emoji={a.emoji}
                deskEmoji={a.deskEmoji}
                status={a.status as AgentStatus}
                jobId={a.job_id}
                lastMessage={a.last_message}
                lastOutput={a.last_output}
              />
            );
          })}
        </div>

        {/* Divider */}
        <div className="border-t-2 border-dashed border-pixel-border/40 mx-4 mb-8 relative z-10">
          <span className="absolute top-[-10px] left-1/2 -translate-x-1/2 bg-[#0d1117] px-2 text-pixel-dim text-xs">
            ── MANAGEMENT FLOOR ──
          </span>
        </div>

        {/* Agent row 2: Supervisor */}
        <div className="flex justify-center relative z-10">
          {(() => {
            const a = getAgent("supervisor");
            return (
              <AgentDesk
                name={a.name}
                role={a.role}
                emoji={a.emoji}
                deskEmoji={a.deskEmoji}
                status={a.status as AgentStatus}
                jobId={a.job_id}
                lastMessage={a.last_message}
                lastOutput={a.last_output}
              />
            );
          })()}
        </div>
      </div>
    </div>
  );
}
