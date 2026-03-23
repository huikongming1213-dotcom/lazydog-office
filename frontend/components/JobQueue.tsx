"use client";
import { useEffect, useState } from "react";

interface Job {
  id: string;
  topic: string;
  status: string;
  approval_status?: string;
  platform_list: string[];
  created_at: string;
}

const STATUS_COLOR: Record<string, string> = {
  pending: "text-pixel-dim",
  running: "text-pixel-working",
  trend_done: "text-pixel-blue",
  copy_done: "text-pixel-blue",
  image_done: "text-pixel-blue",
  pending_approval: "text-pixel-yellow animate-pixel-blink",
  approved: "text-pixel-green",
  rejected: "text-pixel-error",
  revision_requested: "text-pixel-yellow",
  completed: "text-pixel-green",
  failed: "text-pixel-error",
};

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

export default function JobQueue() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [topic, setTopic] = useState("");
  const [loading, setLoading] = useState(false);

  const fetchJobs = async () => {
    try {
      const res = await fetch(`${BACKEND}/jobs`);
      const data = await res.json();
      setJobs(data);
    } catch {
      // silently fail — SSE will update state anyway
    }
  };

  useEffect(() => {
    fetchJobs();
    const interval = setInterval(fetchJobs, 5000);
    return () => clearInterval(interval);
  }, []);

  const startJob = async () => {
    if (!topic.trim()) return;
    setLoading(true);
    try {
      await fetch(`${BACKEND}/webhooks/n8n/start-job`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          topic,
          platforms: ["ig", "linkedin", "x", "threads", "fb"],
          tone: "casual",
        }),
      });
      setTopic("");
      setTimeout(fetchJobs, 500);
    } catch (e) {
      alert("Failed to start job");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="px-border bg-pixel-panel flex flex-col h-full">
      <div className="px-titlebar">📋 JOB QUEUE</div>

      {/* New job form */}
      <div className="p-3 border-b border-pixel-border flex gap-2">
        <input
          className="px-input flex-1"
          placeholder="Enter topic..."
          value={topic}
          onChange={e => setTopic(e.target.value)}
          onKeyDown={e => e.key === "Enter" && startJob()}
        />
        <button
          className="px-btn px-btn-green whitespace-nowrap"
          onClick={startJob}
          disabled={loading}
        >
          {loading ? "..." : "▶ START"}
        </button>
      </div>

      {/* Job list */}
      <div className="flex-1 overflow-y-auto min-h-0">
        {jobs.length === 0 && (
          <div className="text-pixel-dim text-center py-8 font-mono text-sm">
            No jobs yet
          </div>
        )}
        {jobs.map(job => (
          <JobRow key={job.id} job={job} />
        ))}
      </div>
    </div>
  );
}

function JobRow({ job }: { job: Job }) {
  const statusColor = STATUS_COLOR[job.status] || "text-pixel-dim";
  const time = new Date(job.created_at).toLocaleTimeString("en-HK", {
    hour: "2-digit", minute: "2-digit", hour12: false,
  });

  return (
    <div className="border-b border-pixel-border/30 px-3 py-2 hover:bg-white/5 transition-colors">
      <div className="flex justify-between items-start gap-2">
        <div className="font-mono text-sm text-pixel-text truncate flex-1">
          {job.topic}
        </div>
        <div className={`font-pixel text-[7px] shrink-0 ${statusColor}`}>
          {job.status.toUpperCase()}
        </div>
      </div>
      <div className="flex gap-2 mt-1 items-center">
        <span className="text-pixel-dim text-xs">{time}</span>
        <span className="text-pixel-dim text-xs">#{job.id.slice(0, 8)}</span>
        <div className="flex gap-1">
          {job.platform_list.map(p => (
            <span key={p} className="px-tag">{p.toUpperCase()}</span>
          ))}
        </div>
      </div>
    </div>
  );
}
