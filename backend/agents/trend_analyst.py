"""
Trend Analyst Agent
Uses Apify to scrape trending topics, then summarises into a brief.
"""
import logging
import os
from tenacity import retry, stop_after_attempt, wait_exponential

from apify_client import ApifyClientAsync
from backend.services.office_state import update_agent_state, AgentStatus
from backend.services.telegram_bot import send_group_message

logger = logging.getLogger(__name__)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def run_trend_analyst(job_id: str, topic: str, platforms: list[str]) -> dict:
    """
    Scrape trending content for a topic via Apify.
    Returns: {"trends": list, "viral_score": float, "brief": str}
    """
    await update_agent_state("trend_analyst", AgentStatus.WORKING, job_id=job_id,
                             message=f"Analysing trends for: {topic}")
    logger.info(f"[TrendAnalyst] job={job_id} topic={topic} platforms={platforms}")

    try:
        trends, viral_score = await _fetch_from_apify(topic, platforms)
        brief = _build_brief(topic, trends, viral_score)

        result = {
            "trends": trends,
            "viral_score": viral_score,
            "brief": brief,
        }

        await update_agent_state("trend_analyst", AgentStatus.DONE, job_id=job_id,
                                 message="Trend analysis complete", output=result)

        tg_msg = (
            f"📊 *趨勢分析完成*\n"
            f"🆔 Job: `{job_id}`\n"
            f"🔍 Topic: {topic}\n"
            f"🔥 Viral Score: {viral_score:.1f}/10\n"
            f"📝 {brief[:200]}..."
        )
        await send_group_message(tg_msg)
        return result

    except Exception as e:
        logger.error(f"[TrendAnalyst] job={job_id} error: {e}")
        await update_agent_state("trend_analyst", AgentStatus.ERROR, job_id=job_id,
                                 message=str(e))
        raise


async def _fetch_from_apify(topic: str, platforms: list[str]) -> tuple[list, float]:
    """
    Call Apify Google Trends scraper.
    Actor: apify/google-trends-scraper
    Falls back to mock data if APIFY_API_TOKEN is not set.
    """
    # Read token inside function to pick up latest env var, strip hidden whitespace
    apify_token = (os.getenv("APIFY_API_TOKEN") or "").strip()

    if not apify_token:
        logger.warning("[TrendAnalyst] No APIFY_API_TOKEN — using mock data")
        return _mock_trends(topic), 7.5

    client = ApifyClientAsync(apify_token)

    run_input = {
        "searchTerms": [topic],
        "geo": "HK",
        "timeRange": "now 7-d",
        "category": "0",
    }

    try:
        run = await client.actor("apify/google-trends-scraper").call(run_input=run_input)
    except Exception as e:
        status_code = getattr(e, "status_code", "N/A")
        message = getattr(e, "message", str(e))
        logger.error(
            f"[TrendAnalyst] Apify API error — status_code={status_code} message={message}"
        )
        raise

    items = []
    async for item in await client.dataset(run["defaultDatasetId"]).iterate_items():
        items.append(item)

    if not items:
        return _mock_trends(topic), 5.0

    # Parse Apify results into trend list
    trends = []
    for item in items[:10]:
        trends.append({
            "keyword": item.get("keyword", topic),
            "value": item.get("value", 50),
            "related": item.get("relatedQueries", [])[:3],
        })

    # Viral score: average of trend values normalised to 10
    avg_value = sum(t["value"] for t in trends) / len(trends) if trends else 50
    viral_score = round(min(avg_value / 10, 10.0), 1)

    return trends, viral_score


def _mock_trends(topic: str) -> list:
    return [
        {"keyword": topic, "value": 85, "related": ["viral", "trending", "news"]},
        {"keyword": f"{topic} tutorial", "value": 72, "related": ["howto", "guide"]},
        {"keyword": f"{topic} 2025", "value": 68, "related": ["latest", "update"]},
    ]


def _build_brief(topic: str, trends: list, viral_score: float) -> str:
    top_keywords = [t["keyword"] for t in trends[:3]]
    return (
        f"Topic '{topic}' has a viral score of {viral_score}/10. "
        f"Top trending angles: {', '.join(top_keywords)}. "
        f"Recommend creating content that highlights recency and practical value."
    )
