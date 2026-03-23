"""
Office State Manager
Tracks real-time agent states and broadcasts SSE events to the frontend.
"""
import asyncio
import json
from datetime import datetime
from typing import Any
from enum import Enum


class AgentStatus(str, Enum):
    IDLE = "idle"
    WORKING = "working"
    DONE = "done"
    ERROR = "error"


AGENTS = ["trend_analyst", "copywriter", "image_gen", "supervisor"]

# In-memory state for each agent
_agent_states: dict[str, dict] = {
    agent: {
        "status": AgentStatus.IDLE,
        "job_id": None,
        "last_message": None,
        "last_output": None,
        "updated_at": datetime.utcnow().isoformat(),
    }
    for agent in AGENTS
}

# SSE subscribers: list of asyncio.Queue
_subscribers: list[asyncio.Queue] = []


def get_current_state() -> dict:
    """Return snapshot of all agent states (for GET /office/state/current)."""
    return {
        "agents": dict(_agent_states),
        "timestamp": datetime.utcnow().isoformat(),
    }


async def update_agent_state(
    agent_name: str,
    status: AgentStatus,
    job_id: str | None = None,
    message: str | None = None,
    output: Any = None,
):
    """Update an agent's state and broadcast to all SSE subscribers."""
    _agent_states[agent_name] = {
        "status": status,
        "job_id": job_id,
        "last_message": message,
        "last_output": output,
        "updated_at": datetime.utcnow().isoformat(),
    }

    event = {
        "type": "agent_update",
        "agent": agent_name,
        **_agent_states[agent_name],
    }
    await _broadcast(event)


async def broadcast_activity(message: str, job_id: str | None = None):
    """Broadcast a general activity event (e.g. TG messages) to the feed."""
    event = {
        "type": "activity",
        "message": message,
        "job_id": job_id,
        "timestamp": datetime.utcnow().isoformat(),
    }
    await _broadcast(event)


async def _broadcast(event: dict):
    dead = []
    for q in _subscribers:
        try:
            q.put_nowait(json.dumps(event))
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        _subscribers.remove(q)


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    _subscribers.append(q)
    return q


def unsubscribe(q: asyncio.Queue):
    if q in _subscribers:
        _subscribers.remove(q)
