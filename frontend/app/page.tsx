"use client";
import PixelOffice from "@/components/PixelOffice";
import TelegramFeed from "@/components/TelegramFeed";
import JobQueue from "@/components/JobQueue";

export default function Home() {
  return (
    <main className="min-h-screen bg-pixel-bg p-4 flex flex-col gap-4">
      {/* Header */}
      <header className="px-border bg-pixel-panel py-3 px-4 flex items-center justify-between">
        <div>
          <h1 className="font-pixel text-pixel-accent text-sm tracking-widest">
            🐾 LAZYDOG.AI
          </h1>
          <p className="font-mono text-pixel-dim text-xs mt-1">
            VIRTUAL OFFICE v0.1 — MULTI-AGENT SOCIAL MEDIA SYSTEM
          </p>
        </div>
        <div className="font-pixel text-[7px] text-pixel-dim text-right">
          <div>AGENTS: 4 ONLINE</div>
          <div className="text-pixel-green mt-1">● SYSTEM NOMINAL</div>
        </div>
      </header>

      {/* Main grid */}
      <div className="flex gap-4 flex-1 min-h-0" style={{ minHeight: "calc(100vh - 140px)" }}>
        {/* Left column: Office + Job Queue */}
        <div className="flex flex-col gap-4 flex-1 min-w-0">
          {/* Pixel Office */}
          <PixelOffice />

          {/* Job Queue */}
          <div className="flex-1" style={{ minHeight: "240px" }}>
            <JobQueue />
          </div>
        </div>

        {/* Right column: Activity Feed */}
        <div className="w-80 shrink-0" style={{ minHeight: "600px" }}>
          <TelegramFeed />
        </div>
      </div>

      {/* Footer */}
      <footer className="font-pixel text-[6px] text-pixel-dim text-center py-2">
        LAZYDOG.AI VIRTUAL OFFICE — POWERED BY CLAUDE + N8N
      </footer>
    </main>
  );
}
