"""
Supervisor Agent
Uses Claude Opus to review captions + image for brand consistency and quality.
After review, sends TG approval message and returns immediately (async approval flow).
"""
import logging
import os
import json
import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from backend.services.office_state import update_agent_state, AgentStatus
from backend.services.telegram_bot import send_approval_request

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

SUPERVISOR_SYSTEM = """
You are the Content Supervisor at Lazydog.ai. Your job is to review social media content
before it goes live.

Review criteria:
1. Brand consistency — does it match Lazydog.ai's witty, approachable tone?
2. Grammar and clarity — no typos, awkward phrasing, or unclear messaging
3. Platform fit — is each caption appropriate for its platform's norms?
4. Safety — no controversial, offensive, or legally risky content
5. CTA quality — is the call-to-action natural and compelling?

Be constructive but decisive. If content needs changes, be specific about what to fix.
"""


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def run_supervisor(
    job_id: str,
    captions: dict,
    image_url: str,
    brief: str,
) -> dict:
    """
    Review content with Claude Opus.
    Sends TG approval request and returns immediately with status=pending_approval.
    Returns: {"approved": bool, "feedback": str, "edited_captions": dict, "status": "pending_approval"}
    """
    await update_agent_state("supervisor", AgentStatus.WORKING, job_id=job_id,
                             message="Reviewing content...")
    logger.info(f"[Supervisor] job={job_id} reviewing captions + image")

    prompt = f"""
Please review the following social media content package:

BRIEF: {brief}

CAPTIONS:
{json.dumps(captions, indent=2, ensure_ascii=False)}

IMAGE URL: {image_url}

Provide your review as a JSON object:
{{
  "approved": true/false,
  "feedback": "Overall feedback here",
  "issues": ["issue1", "issue2"],
  "edited_captions": {{
    "ig": "edited or original if no changes",
    "linkedin": "...",
    "x": "...",
    "threads": "...",
    "fb": "..."
  }},
  "brand_score": 8.5
}}

Only return the JSON, no other text.
"""

    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

    try:
        message = await client.messages.create(
            model="claude-opus-4-6",
            max_tokens=2000,
            system=SUPERVISOR_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = message.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        review = json.loads(raw.strip())

        # Add pending_approval status — actual approval comes from TG
        review["status"] = "pending_approval"

        await update_agent_state("supervisor", AgentStatus.DONE, job_id=job_id,
                                 message=f"Review done. Brand score: {review.get('brand_score', 'N/A')}",
                                 output=review)

        # Send TG approval request with inline keyboard
        ig_caption = review["edited_captions"].get("ig", captions.get("ig", ""))
        await send_approval_request(
            job_id=job_id,
            ig_caption=ig_caption,
            captions=review["edited_captions"],
            image_url=image_url,
            feedback=review["feedback"],
            approved_by_ai=review["approved"],
        )

        return review

    except Exception as e:
        logger.error(f"[Supervisor] job={job_id} error: {e}")
        await update_agent_state("supervisor", AgentStatus.ERROR, job_id=job_id,
                                 message=str(e))
        raise
