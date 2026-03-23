"use client";
import { useState } from "react";

export type AgentStatus = "idle" | "working" | "done" | "error";

interface AgentDeskProps {
  name: string;
  role: string;
  emoji: string;
  deskEmoji: string;
  status: AgentStatus;
  jobId?: string;
  lastMessage?: string;
  lastOutput?: unknown;
}

const STATUS_LABEL: Record<AgentStatus, string> = {
  idle: "IDLE",
  working: "WORKING",
  done: "DONE",
  error: "ERROR",
};

const STATUS_COLOR: Record<AgentStatus, string> = {
  idle: "text-pixel-idle",
  working: "text-pixel-working",
  done: "text-pixel-green",
  error: "text-pixel-error",
};

export default function AgentDesk({
  name, role, emoji, deskEmoji, status, jobId, lastMessage, lastOutput,
}: AgentDeskProps) {
  const [showOutput, setShowOutput] = useState(false);

  return (
    <div className="flex flex-col items-center gap-1">
      {/* Desk card */}
      <div
        className={`agent-desk px-border w-40 ${status === "working" ? "animate-working" : ""}`}
        onClick={() => lastOutput && setShowOutput(true)}
        title={lastOutput ? "Click to view output" : undefined}
      >
        {/* Name bar */}
        <div className="px-titlebar text-[6px] justify-between">
          <span>{name.toUpperCase()}</span>
          <span className={STATUS_COLOR[status]}>{STATUS_LABEL[status]}</span>
        </div>

        {/* Character area */}
        <div className="flex flex-col items-center py-3 gap-2 bg-pixel-panel relative">
          {/* Status dot */}
          <div className={`status-dot status-${status} absolute top-2 right-2`} />

          {/* Agent sprite */}
          <div className="text-3xl agent-emoji select-none">{emoji}</div>

          {/* Role label */}
          <div className="font-pixel text-[5px] text-pixel-dim text-center leading-loose">
            {role}
          </div>
        </div>

        {/* Desk surface */}
        <div className="desk-surface flex items-center justify-center gap-1 px-2">
          <span className="text-sm">{deskEmoji}</span>
          {status === "working" && (
            <span className="text-pixel-working text-xs animate-pixel-blink">●●●</span>
          )}
        </div>

        {/* Job ID */}
        {jobId && (
          <div className="bg-black/30 px-1 py-0.5 text-[8px] font-mono text-pixel-dim truncate">
            #{jobId.slice(0, 8)}
          </div>
        )}
      </div>

      {/* Last message */}
      {lastMessage && (
        <div className="w-40 text-[11px] font-mono text-pixel-dim text-center leading-tight px-1 truncate">
          {lastMessage}
        </div>
      )}

      {/* Output modal */}
      {showOutput && lastOutput && (
        <OutputModal
          title={`${name} Output`}
          data={lastOutput}
          onClose={() => setShowOutput(false)}
        />
      )}
    </div>
  );
}

function OutputModal({ title, data, onClose }: { title: string; data: unknown; onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4"
      onClick={onClose}
    >
      <div
        className="px-border bg-pixel-panel max-w-2xl w-full max-h-[80vh] flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        <div className="px-titlebar justify-between">
          <span>{title.toUpperCase()}</span>
          <button className="px-btn text-[6px] px-2 py-1" onClick={onClose}>✕ CLOSE</button>
        </div>
        <div className="overflow-auto p-4 font-mono text-sm text-pixel-text flex-1">
          <pre className="whitespace-pre-wrap break-words text-xs text-pixel-green">
            {JSON.stringify(data, null, 2)}
          </pre>
        </div>
      </div>
    </div>
  );
}
