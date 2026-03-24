"""
Strategist — Pre-production market analysis and angle selection.
Runs during brainstorm phase (triggered by topic discussion in TG group).

Flow:
  1. Aria quick-scans market data (Claude Haiku, zero Apify cost)
  2. Max analyses 3 copy angles from trend data
  3. Chief ranks by brand fit and recommends best angle

Each step posts to TG group as the agent's own bot.
Full Apify call happens later in trend_analyst.py when /go is triggered.
"""
import json
import logging
import os
import anthropic

from backend.services.agent_messenger import send_as

logger = logging.getLogger(__name__)


async def run_strategy_discussion(topic: str):
    """
    Full brainstorm strategy flow for a topic.
    Posts 3 messages (Aria → Max → Chief) to the TG group.
    """
    logger.info(f"[Strategist] Starting strategy discussion for: {topic}")
    client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

    try:
        # Step 1: Aria — market scan (Haiku, cheap)
        scan = await _aria_quick_scan(client, topic)
        await send_as("trend_analyst", _format_aria_message(topic, scan))

        # Step 2: Max — copy angle suggestions
        angles = await _max_angle_analysis(client, topic, scan)
        await send_as("copywriter", _format_max_message(angles))

        # Step 3: Chief — brand filter + final recommendation
        rec = await _chief_rank(client, topic, angles)
        await send_as("supervisor", _format_chief_message(rec))

    except Exception as e:
        logger.error(f"[Strategist] Strategy discussion failed for '{topic}': {e}")


# ── Agent sub-tasks ─────────────────────────────────────────────────────────────

async def _aria_quick_scan(client: anthropic.AsyncAnthropic, topic: str) -> dict:
    """
    Simulate HK market trend data via Claude Haiku.
    No Apify call — this is brainstorm mode only.
    Real Apify analysis happens during pipeline run.
    """
    msg = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=350,
        messages=[{
            "role": "user",
            "content": (
                f"You are a HK social media market analyst. "
                f"For the topic \"{topic}\", provide realistic trend data for HK social media.\n\n"
                "Return JSON only:\n"
                "{\n"
                '  "overall_score": <1-10 float>,\n'
                '  "sub_topics": [\n'
                '    {"name": "...", "score": <1-100 int>, "trend": "up/stable/down"},\n'
                '    {"name": "...", "score": <1-100 int>, "trend": "up/stable/down"},\n'
                '    {"name": "...", "score": <1-100 int>, "trend": "up/stable/down"}\n'
                "  ],\n"
                '  "competition_level": "low/medium/high",\n'
                '  "content_gap": "one sentence: what existing content is missing"\n'
                "}"
            ),
        }],
    )
    return _parse_json(msg.content[0].text)


async def _max_angle_analysis(client: anthropic.AsyncAnthropic, topic: str, scan: dict) -> list:
    """Max suggests 3 copy angles based on trend data."""
    sub_lines = "\n".join(
        f"- {s['name']} ({s['score']}分, {s['trend']})"
        for s in scan.get("sub_topics", [])
    )
    msg = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=450,
        messages=[{
            "role": "user",
            "content": (
                f"You are a social media copywriter. Topic: \"{topic}\"\n\n"
                f"Trend data:\n{sub_lines}\n"
                f"Content gap: {scan.get('content_gap', '')}\n\n"
                "Suggest 3 distinct content angles. Return JSON only:\n"
                "[\n"
                "  {\n"
                '    "angle": "short angle name",\n'
                '    "hook": "punchy opening line in Traditional Chinese",\n'
                '    "format": "e.g. before/after, tutorial, opinion, story",\n'
                '    "best_platform": "ig/linkedin/x",\n'
                '    "strength": "why this angle works (one sentence)"\n'
                "  }\n"
                "]"
            ),
        }],
    )
    return _parse_json(msg.content[0].text)


async def _chief_rank(client: anthropic.AsyncAnthropic, topic: str, angles: list) -> dict:
    """Chief ranks angles by Lazydog.ai brand fit."""
    msg = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{
            "role": "user",
            "content": (
                "You are the Content Director at Lazydog.ai — a witty, approachable AI productivity brand.\n"
                "Brand values: empowering, smart-but-lazy, never corporate or tech-heavy.\n\n"
                f"Topic: \"{topic}\"\n"
                f"Angles proposed:\n{json.dumps(angles, ensure_ascii=False, indent=2)}\n\n"
                "Pick the best angle for brand fit. Return JSON only:\n"
                "{\n"
                '  "best_angle": "<angle name>",\n'
                '  "best_hook": "<the hook for that angle>",\n'
                '  "brand_notes": "what to emphasise and what to avoid (one sentence)",\n'
                '  "ranking": ["best angle name", "2nd", "3rd"]\n'
                "}"
            ),
        }],
    )
    return _parse_json(msg.content[0].text)


# ── Message formatters ──────────────────────────────────────────────────────────

def _format_aria_message(topic: str, scan: dict) -> str:
    sub = scan.get("sub_topics", [])
    trend_arrow = {"up": "↗", "stable": "→", "down": "↘"}
    sub_lines = "\n".join(
        f"  • {s['name']} — {s['score']}分 {trend_arrow.get(s['trend'], '')}"
        for s in sub
    )
    competition = {
        "low": "🟢 競爭低，好時機",
        "medium": "🟡 競爭中等",
        "high": "🔴 競爭激烈，要差異化",
    }.get(scan.get("competition_level", ""), "")

    return (
        f"📊 *市場快掃：{topic}*\n"
        f"整體熱度：{scan.get('overall_score', '?')}/10\n\n"
        f"*Sub-topics：*\n{sub_lines}\n\n"
        f"{competition}\n"
        f"💡 內容空白：_{scan.get('content_gap', '')}_"
    )


def _format_max_message(angles: list) -> str:
    lines = ["✍️ *3個內容角度分析*\n"]
    for i, a in enumerate(angles, 1):
        lines.append(f"*{i}\\. {a.get('angle', '')}*")
        lines.append(f"  Hook：\"{a.get('hook', '')}\"")
        lines.append(f"  Format：{a.get('format', '')} | 最佳平台：{a.get('best_platform', '')}")
        lines.append(f"  ✅ {a.get('strength', '')}\n")
    return "\n".join(lines)


def _format_chief_message(rec: dict) -> str:
    ranking = rec.get("ranking", [])
    rank_str = " > ".join(ranking) if ranking else ""
    return (
        f"👔 *Chief 建議*\n\n"
        f"推薦角度：*{rec.get('best_angle', '')}*\n"
        f"Hook：\"{rec.get('best_hook', '')}\"\n\n"
        f"品牌指引：_{rec.get('brand_notes', '')}_\n"
        f"優先順序：{rank_str}\n\n"
        f"同意就打 /go 開始生產 🚀"
    )


# ── Helpers ─────────────────────────────────────────────────────────────────────

def _parse_json(raw: str) -> dict | list:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())
