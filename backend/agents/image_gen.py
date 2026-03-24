"""
Image Gen Agent
Uses OpenRouter (router.ai) to generate images via FLUX or similar models.
"""
import logging
import os
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from backend.services.office_state import update_agent_state, AgentStatus
from backend.services.agent_messenger import send_as

logger = logging.getLogger(__name__)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_IMAGE_URL = "https://openrouter.ai/api/v1/images/generations"
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "black-forest-labs/flux-1.1-pro")


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=15))
async def run_image_gen(job_id: str, brief: str, style: str = "modern minimal") -> dict:
    """
    Generate an image via OpenRouter (FLUX model).
    Returns: {"image_url": str, "prompt_used": str}
    """
    await update_agent_state("image_gen", AgentStatus.WORKING, job_id=job_id,
                             message="Generating image...")
    logger.info(f"[ImageGen] job={job_id} style={style}")

    prompt = _build_image_prompt(brief, style)

    try:
        if not OPENROUTER_API_KEY:
            logger.warning("[ImageGen] No OPENROUTER_API_KEY — returning placeholder")
            result = _mock_result(prompt)
        else:
            result = await _call_openrouter(prompt)

        await update_agent_state("image_gen", AgentStatus.DONE, job_id=job_id,
                                 message="Image generated", output=result)

        tg_msg = (
            f"🎨 *Zoe：圖片搞掂*\n"
            f"🆔 `{job_id[:8]}`\n"
            f"🖼 Model：{IMAGE_MODEL.split('/')[-1]}\n\n"
            f"*視覺決策：*\n_{prompt[:150]}..._\n\n"
            f"@Chief 請 review！"
        )
        await send_as("image_gen", tg_msg)
        return result

    except Exception as e:
        logger.error(f"[ImageGen] job={job_id} error: {e}")
        await update_agent_state("image_gen", AgentStatus.ERROR, job_id=job_id,
                                 message=str(e))
        raise


async def _call_openrouter(prompt: str) -> dict:
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://lazydog.ai",
        "X-Title": "Lazydog.ai Virtual Office",
    }
    payload = {
        "model": IMAGE_MODEL,
        "prompt": prompt,
        "n": 1,
        "size": "1024x1024",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(OPENROUTER_IMAGE_URL, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

    image_url = data["data"][0].get("url") or data["data"][0].get("b64_json", "")
    return {"image_url": image_url, "prompt_used": prompt}


def _build_image_prompt(brief: str, style: str) -> str:
    return (
        f"Social media marketing image for Lazydog.ai. "
        f"Style: {style}. "
        f"Context: {brief[:300]}. "
        f"Clean composition, vibrant colours, suitable for Instagram. "
        f"No text overlays. Professional quality."
    )


def _mock_result(prompt: str) -> dict:
    return {
        "image_url": "https://placehold.co/1024x1024/667eea/ffffff?text=Lazydog.ai",
        "prompt_used": prompt,
    }
