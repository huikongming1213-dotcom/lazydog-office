"""
Lazydog.ai Virtual Office — FastAPI Backend
"""
import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, BackgroundTasks, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from sqlalchemy import select, update

load_dotenv()

from backend.database import init_db, get_db
from backend.models import Job, AgentLog, Post
from backend.services.office_state import (
    get_current_state, subscribe, unsubscribe, broadcast_activity
)
from backend.services.telegram_bot import build_application, setup_webhook, process_update
from backend.agents.trend_analyst import run_trend_analyst
from backend.agents.copywriter import run_copywriter
from backend.agents.image_gen import run_image_gen
from backend.agents.supervisor import run_supervisor
from backend.services.publisher import publish_to_all_platforms

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")


# ── Lifespan ───────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Lazydog.ai Virtual Office...")
    await init_db()

    # Build TG application (webhook mode, no polling)
    tg_app = build_application()
    await tg_app.initialize()

    # Register webhook (will be ngrok URL in dev)
    tg_webhook_url = f"{BACKEND_URL}/webhooks/telegram"
    try:
        await setup_webhook(tg_webhook_url)
    except Exception as e:
        logger.warning(f"Telegram webhook setup failed (non-fatal): {e}")

    yield

    logger.info("Shutting down...")
    await tg_app.shutdown()


app = FastAPI(title="Lazydog.ai Virtual Office", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Pydantic Schemas ───────────────────────────────────────────────────────────

class StartJobRequest(BaseModel):
    topic: str
    platforms: list[str] = ["ig", "linkedin", "x", "threads", "fb"]
    tone: str = "casual"
    n8n_resume_url: str | None = None


class TrendAnalystRequest(BaseModel):
    job_id: str
    topic: str
    platforms: list[str]


class CopywriterRequest(BaseModel):
    job_id: str
    brief: str
    platforms: list[str]
    tone: str = "casual"
    revision_notes: str | None = None


class ImageGenRequest(BaseModel):
    job_id: str
    brief: str
    style: str = "modern minimal"


class SupervisorRequest(BaseModel):
    job_id: str
    captions: dict
    image_url: str
    brief: str
    n8n_resume_url: str | None = None  # N8N Wait Webhook URL


class ApprovalCallbackRequest(BaseModel):
    job_id: str
    action: str   # approved | rejected | revision_requested | regenerate
    notes: str | None = None


# ── Helper: log agent action ────────────────────────────────────────────────────

async def _log(job_id: str, agent: str, action: str, message: str, level: str = "info"):
    async with get_db() as db:
        db.add(AgentLog(
            job_id=job_id,
            agent_name=agent,
            action=action,
            message=message,
            level=level,
        ))


async def _update_job_status(job_id: str, **kwargs):
    async with get_db() as db:
        await db.execute(
            update(Job).where(Job.id == job_id).values(**kwargs)
        )


# ── Office State ───────────────────────────────────────────────────────────────

@app.get("/office/state/current")
async def get_office_state():
    """Return current agent states snapshot (frontend initial load)."""
    return get_current_state()


@app.get("/office/stream")
async def office_sse_stream(request: Request):
    """SSE stream for real-time office state updates."""
    q = subscribe()

    async def event_generator():
        # Send current state immediately on connect
        import json
        yield {"data": json.dumps({"type": "init", **get_current_state()})}
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(q.get(), timeout=25.0)
                    yield {"data": data}
                except asyncio.TimeoutError:
                    # Heartbeat to keep connection alive
                    yield {"data": '{"type":"ping"}'}
        finally:
            unsubscribe(q)

    return EventSourceResponse(event_generator())


# ── N8N Webhooks ───────────────────────────────────────────────────────────────

@app.post("/webhooks/n8n/start-job")
async def n8n_start_job(req: StartJobRequest, background_tasks: BackgroundTasks):
    """N8N triggers a new content job. Returns job_id immediately."""
    job_id = str(uuid.uuid4())
    async with get_db() as db:
        db.add(Job(
            id=job_id,
            topic=req.topic,
            platform_list=req.platforms,
            tone=req.tone,
            status="pending",
            n8n_resume_url=req.n8n_resume_url,
        ))
    await broadcast_activity(f"🆕 New job started: {req.topic}", job_id=job_id)
    logger.info(f"[N8N] New job created: {job_id}")
    return {"job_id": job_id, "status": "pending"}


@app.post("/webhooks/n8n/job-status")
async def n8n_job_status(body: dict):
    """N8N polls job status."""
    job_id = body.get("job_id")
    if not job_id:
        raise HTTPException(400, "job_id required")
    async with get_db() as db:
        result = await db.execute(select(Job).where(Job.id == job_id))
        job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Job not found")
    return {"job_id": job_id, "status": job.status, "approval_status": job.approval_status}


@app.get("/webhooks/n8n/get-result/{job_id}")
async def n8n_get_result(job_id: str):
    """N8N fetches final result of a completed job."""
    async with get_db() as db:
        result = await db.execute(select(Job).where(Job.id == job_id))
        job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Job not found")
    return {
        "job_id": job_id,
        "status": job.status,
        "trend_result": job.trend_result,
        "copy_result": job.copy_result,
        "image_result": job.image_result,
        "supervisor_result": job.supervisor_result,
    }


# ── Agent Endpoints ────────────────────────────────────────────────────────────

@app.post("/agents/trend-analyst")
async def agent_trend_analyst(req: TrendAnalystRequest):
    try:
        result = await run_trend_analyst(req.job_id, req.topic, req.platforms)
        await _update_job_status(req.job_id, trend_result=result, status="trend_done")
        await _log(req.job_id, "trend_analyst", "complete", result["brief"])
        return result
    except Exception as e:
        await _log(req.job_id, "trend_analyst", "error", str(e), level="error")
        raise HTTPException(500, str(e))


@app.post("/agents/copywriter")
async def agent_copywriter(req: CopywriterRequest):
    try:
        result = await run_copywriter(
            req.job_id, req.brief, req.platforms, req.tone, req.revision_notes
        )
        await _update_job_status(req.job_id, copy_result=result, status="copy_done")
        await _log(req.job_id, "copywriter", "complete", "Captions generated")
        return result
    except Exception as e:
        await _log(req.job_id, "copywriter", "error", str(e), level="error")
        raise HTTPException(500, str(e))


@app.post("/agents/image-gen")
async def agent_image_gen(req: ImageGenRequest):
    try:
        result = await run_image_gen(req.job_id, req.brief, req.style)
        await _update_job_status(req.job_id, image_result=result, status="image_done")
        await _log(req.job_id, "image_gen", "complete", result["image_url"])
        return result
    except Exception as e:
        await _log(req.job_id, "image_gen", "error", str(e), level="error")
        raise HTTPException(500, str(e))


@app.post("/agents/supervisor")
async def agent_supervisor(req: SupervisorRequest):
    """
    Run supervisor review, send TG approval request, return IMMEDIATELY.
    Returns status=pending_approval — N8N should use a Wait node after this.
    """
    # Store n8n_resume_url if provided
    if req.n8n_resume_url:
        await _update_job_status(req.job_id, n8n_resume_url=req.n8n_resume_url)

    try:
        result = await run_supervisor(req.job_id, req.captions, req.image_url, req.brief)
        await _update_job_status(
            req.job_id,
            supervisor_result=result,
            status="pending_approval",
            approval_status="pending_approval",
        )
        await _log(req.job_id, "supervisor", "pending_approval",
                   f"Brand score: {result.get('brand_score', 'N/A')}")
        # Return immediately — TG approval is async
        return {"status": "pending_approval", "job_id": req.job_id, "review": result}
    except Exception as e:
        await _log(req.job_id, "supervisor", "error", str(e), level="error")
        raise HTTPException(500, str(e))


# ── Approval Callback (from TG Bot → Backend → N8N) ───────────────────────────

@app.post("/webhooks/approval-callback")
async def approval_callback(req: ApprovalCallbackRequest, background_tasks: BackgroundTasks):
    """
    Called by TG Bot service when user presses an inline button.
    Updates job status and resumes N8N Wait Webhook.
    """
    logger.info(f"[Approval] job={req.job_id} action={req.action}")

    # Fetch job
    async with get_db() as db:
        result = await db.execute(select(Job).where(Job.id == req.job_id))
        job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Job not found")

    status_map = {
        "approved": "approved",
        "rejected": "rejected",
        "revision_requested": "revision_requested",
        "regenerate": "regenerate",
    }
    new_status = status_map.get(req.action, req.action)

    await _update_job_status(
        req.job_id,
        approval_status=new_status,
        status=new_status,
        revision_notes=req.notes,
    )
    await broadcast_activity(
        f"🔔 Job {req.job_id[:8]}... → {new_status}", job_id=req.job_id
    )

    # Resume N8N Wait Webhook
    if job.n8n_resume_url:
        background_tasks.add_task(
            _resume_n8n,
            job.n8n_resume_url,
            {"job_id": req.job_id, "action": req.action, "notes": req.notes},
        )

    # If revision requested, trigger copywriter in background
    if req.action == "revision_requested" and req.notes:
        background_tasks.add_task(_handle_revision, job, req.notes)

    return {"status": "ok", "job_id": req.job_id, "action": req.action}


async def _resume_n8n(resume_url: str, payload: dict):
    """POST to N8N Wait Webhook to resume the paused workflow."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(resume_url, json=payload)
            logger.info(f"[N8N] Resumed wait webhook: {resume_url}")
    except Exception as e:
        logger.error(f"[N8N] Failed to resume webhook: {e}")


async def _handle_revision(job: Job, notes: str):
    """Re-run copywriter with revision notes, then re-run supervisor."""
    logger.info(f"[Revision] job={job.id} rerouting to copywriter")
    try:
        copy_result = await run_copywriter(
            job_id=job.id,
            brief=job.trend_result.get("brief", job.topic) if job.trend_result else job.topic,
            platforms=job.platform_list,
            tone=job.tone,
            revision_notes=notes,
        )
        await _update_job_status(job.id, copy_result=copy_result, status="copy_done")

        # Re-run supervisor
        image_url = job.image_result.get("image_url", "") if job.image_result else ""
        brief = job.trend_result.get("brief", job.topic) if job.trend_result else job.topic
        await run_supervisor(job.id, copy_result["captions"], image_url, brief)

    except Exception as e:
        logger.error(f"[Revision] job={job.id} error: {e}")
        await _update_job_status(job.id, status="failed")


# ── Telegram Webhook ───────────────────────────────────────────────────────────

@app.post("/webhooks/telegram")
async def telegram_webhook(request: Request):
    """Receive Telegram updates via webhook (no polling)."""
    update_data = await request.json()
    await process_update(update_data)
    return JSONResponse({"ok": True})


# ── Job Management ─────────────────────────────────────────────────────────────

@app.get("/jobs")
async def list_jobs(limit: int = 20):
    async with get_db() as db:
        result = await db.execute(
            select(Job).order_by(Job.created_at.desc()).limit(limit)
        )
        jobs = result.scalars().all()
    return [
        {
            "id": j.id,
            "topic": j.topic,
            "status": j.status,
            "approval_status": j.approval_status,
            "platform_list": j.platform_list,
            "created_at": j.created_at.isoformat() if j.created_at else None,
        }
        for j in jobs
    ]


@app.get("/jobs/{job_id}")
async def get_job(job_id: str):
    async with get_db() as db:
        result = await db.execute(select(Job).where(Job.id == job_id))
        job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@app.get("/jobs/{job_id}/logs")
async def get_job_logs(job_id: str):
    async with get_db() as db:
        result = await db.execute(
            select(AgentLog)
            .where(AgentLog.job_id == job_id)
            .order_by(AgentLog.timestamp.asc())
        )
        logs = result.scalars().all()
    return logs


@app.post("/pipeline/run")
async def pipeline_run(req: StartJobRequest, background_tasks: BackgroundTasks):
    """
    Start the full agent pipeline without N8N.
    Called by the TG bot /go command.
    Returns job_id immediately; pipeline runs in background.
    """
    job_id = str(uuid.uuid4())
    async with get_db() as db:
        db.add(Job(
            id=job_id,
            topic=req.topic,
            platform_list=req.platforms,
            tone=req.tone,
            status="pending",
        ))
    await broadcast_activity(f"🚀 Pipeline started: {req.topic}", job_id=job_id)
    logger.info(f"[Pipeline] New run: job={job_id} topic={req.topic}")
    background_tasks.add_task(_run_full_pipeline, job_id, req.topic, req.platforms, req.tone)
    return {"job_id": job_id, "status": "running"}


async def _run_full_pipeline(job_id: str, topic: str, platforms: list, tone: str):
    """Run all agents sequentially: Trend → Copy → Image → Supervisor."""
    try:
        # 1. Trend analysis
        trend = await run_trend_analyst(job_id, topic, platforms)
        await _update_job_status(job_id, trend_result=trend, status="trend_done")
        await _log(job_id, "trend_analyst", "complete", trend["brief"])

        # 2. Copywriting
        copy = await run_copywriter(job_id, trend["brief"], platforms, tone)
        await _update_job_status(job_id, copy_result=copy, status="copy_done")
        await _log(job_id, "copywriter", "complete", "Captions generated")

        # 3. Image generation
        image = await run_image_gen(job_id, trend["brief"])
        await _update_job_status(job_id, image_result=image, status="image_done")
        await _log(job_id, "image_gen", "complete", image.get("image_url", ""))

        # 4. Supervisor review → sends TG approval message
        await run_supervisor(job_id, copy["captions"], image.get("image_url", ""), trend["brief"])
        await _update_job_status(
            job_id, status="pending_approval", approval_status="pending_approval"
        )

    except Exception as e:
        logger.error(f"[Pipeline] job={job_id} failed: {e}")
        await _update_job_status(job_id, status="failed")
        await _log(job_id, "pipeline", "error", str(e), level="error")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "lazydog-office"}
