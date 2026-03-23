"""
Copywriter Agent
Uses Claude Sonnet to generate platform-specific social media captions.
"""
import logging
import os
import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from backend.services.office_state import update_agent_state, AgentStatus
from backend.services.telegram_bot import send_group_message

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

BRAND_VOICE = """
You are the copywriter for Lazydog.ai — a playful, smart AI productivity brand.

Brand Voice Guidelines:
- Tone: Witty, approachable, slightly lazy but brilliant (like a genius who works smart, not hard)
- Avoid corporate jargon. Write like a smart friend, not a press release.
- Use relatable humour where appropriate
- Always end with a subtle CTA or thought-provoking question
- Emojis: use sparingly and purposefully (1-3 per post max)
- Never use: "game-changer", "revolutionary", "disruptive", "synergy"

Platform character limits and styles:
- IG: 2200 chars max, punchy opener, line breaks for readability, 5-10 hashtags at end
- LinkedIn: 3000 chars max, professional but human, story-driven, no hashtags in body
- X (Twitter): 280 chars HARD limit, punchy, standalone thought
- Threads: 500 chars, conversational, no hashtags needed
- Facebook: 1000 chars, community-focused, question to spark comments
"""


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def run_copywriter(
    job_id: str,
    brief: str,
    platforms: list[str],
    tone: str = "casual",
    revision_notes: str | None = None,
) -> dict:
    """
    Generate captions for each platform using Claude Sonnet.
    Returns: {"captions": {"ig": str, ...}, "hashtags": list}
    """
    await update_agent_state("copywriter", AgentStatus.WORKING, job_id=job_id,
                             message="Writing captions...")
    logger.info(f"[Copywriter] job={job_id} platforms={platforms} tone={tone}")

    revision_block = ""
    if revision_notes:
        revision_block = f"\n\n⚠️ REVISION REQUEST from Supervisor:\n{revision_notes}\nPlease address these points specifically."

    prompt = f"""
Brief: {brief}
Tone: {tone}
Target Platforms: {', '.join(platforms)}
{revision_block}

Generate captions for EACH of the following platforms: ig, linkedin, x, threads, fb.

Return a JSON object with this exact structure:
{{
  "captions": {{
    "ig": "...",
    "linkedin": "...",
    "x": "...",
    "threads": "...",
    "fb": "..."
  }},
  "hashtags": ["tag1", "tag2", "tag3", "tag4", "tag5"]
}}

Only return the JSON, no other text.
"""

    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

    try:
        message = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            system=BRAND_VOICE,
            messages=[{"role": "user", "content": prompt}],
        )

        import json
        raw = message.content[0].text.strip()
        # Strip markdown code blocks if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw.strip())

        await update_agent_state("copywriter", AgentStatus.DONE, job_id=job_id,
                                 message="Captions ready, awaiting supervisor review",
                                 output=result)

        tg_msg = (
            f"✍️ *文案完成，等主管審核*\n"
            f"🆔 Job: `{job_id}`\n"
            f"📱 Platforms: {', '.join(platforms)}\n"
            f"🎯 Tone: {tone}\n"
            f"📝 IG Preview: {result['captions'].get('ig', '')[:100]}..."
        )
        await send_group_message(tg_msg)
        return result

    except Exception as e:
        logger.error(f"[Copywriter] job={job_id} error: {e}")
        await update_agent_state("copywriter", AgentStatus.ERROR, job_id=job_id,
                                 message=str(e))
        raise
