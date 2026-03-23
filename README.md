# 🐾 Lazydog.ai Virtual Office

Multi-agent social media management system with pixel art UI.

## Architecture

```
N8N → FastAPI Backend → Agents (Claude + Apify + OpenRouter)
                      ↓
              Telegram Bot (approval)
                      ↓
              Publisher (stub → real APIs)
                      ↑
Frontend (Next.js) ← SSE Stream
```

## Prerequisites

- Python 3.11+ with `uv`
- Node.js 18+
- ngrok (for local TG webhook testing)

## Setup

### 1. Clone & configure env

```bash
cp .env.example .env
# Fill in all API keys in .env
```

### 2. Backend

```bash
# Install dependencies with uv
uv sync

# Run backend
uv run uvicorn backend.main:app --reload --port 8000
```

### 3. Expose backend for Telegram webhook (local dev)

```bash
ngrok http 8000
# Copy the https URL, set BACKEND_URL=https://xxxx.ngrok.io in .env
# Restart backend — it will auto-register TG webhook on startup
```

### 4. Frontend

```bash
cd frontend
npm install
# Set NEXT_PUBLIC_BACKEND_URL=http://localhost:8000 in frontend/.env.local
npm run dev
```

Open http://localhost:3000

## Environment Variables

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Claude API key (Sonnet + Opus) |
| `OPENROUTER_API_KEY` | OpenRouter key for image generation |
| `APIFY_API_TOKEN` | Apify token for trend scraping |
| `TELEGRAM_BOT_TOKEN` | BotFather token |
| `TELEGRAM_GROUP_CHAT_ID` | Group chat ID for agent discussion |
| `TELEGRAM_APPROVAL_CHAT_ID` | Your personal chat ID for approvals |
| `N8N_BASE_URL` | N8N instance URL |
| `BACKEND_URL` | Public URL of this backend (ngrok in dev) |

## N8N Workflow Setup

### Endpoints provided by backend

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/webhooks/n8n/start-job` | Create new job, returns `job_id` |
| POST | `/agents/trend-analyst` | Run trend analysis |
| POST | `/agents/copywriter` | Generate captions |
| POST | `/agents/image-gen` | Generate image |
| POST | `/agents/supervisor` | Review content (returns `pending_approval`) |
| POST | `/webhooks/n8n/job-status` | Poll job status |
| GET | `/webhooks/n8n/get-result/{id}` | Get final results |

### Recommended N8N flow

```
[Trigger] → start-job → trend-analyst → copywriter → image-gen
          → supervisor (pass n8n_resume_url) → [Wait Webhook]
          ← TG approval callback resumes here
          → publisher (approved) / copywriter (revision) / end (rejected)
```

Pass `n8n_resume_url` in the supervisor request body — backend stores it and
calls it when TG approval button is pressed.

## Agent Details

### Trend Analyst
- Uses **Apify** `apify/google-trends-scraper`
- Falls back to mock data if `APIFY_API_TOKEN` not set
- Sends TG group message on completion

### Copywriter
- Uses **Claude Sonnet 4** (`claude-sonnet-4-6`)
- Generates IG, LinkedIn, X, Threads, FB captions
- Supports revision flow with `revision_notes`

### Image Gen
- Uses **OpenRouter** (FLUX 1.1 Pro by default)
- Model configurable via `IMAGE_MODEL` env var
- Falls back to placeholder if no API key

### Supervisor
- Uses **Claude Opus 4** (`claude-opus-4-6`)
- Returns immediately with `status: pending_approval`
- Sends TG inline keyboard for human approval
- **Does NOT block** the HTTP request

## Telegram Approval Flow

1. Supervisor sends preview + inline buttons to `TELEGRAM_APPROVAL_CHAT_ID`
2. User presses button → TG callback → FastAPI `/webhooks/approval-callback`
3. Backend updates job status + resumes N8N Wait Webhook
4. For ✏️ Revise: user types notes → rerouted to copywriter → supervisor again

## Publisher

All platform publishers are **stubs** in `backend/services/publisher.py`.
Each has a comment with the relevant API approach. Implement per platform.

## Docker

```bash
docker-compose up --build
```
