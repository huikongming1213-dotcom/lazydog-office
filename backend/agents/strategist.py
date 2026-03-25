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
from backend.agents.trend_analyst import _fetch_from_apify, _mock_trends

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
    Real Apify Google Trends data — same source as the production pipeline.
    Falls back to mock data if APIFY_API_TOKEN not set.
    """
    trends, viral_score = await _fetch_from_apify(topic, [])

    avg_score = round(viral_score, 1)
    competition = "high" if avg_score >= 7 else "medium" if avg_score >= 4 else "low"

    sub_topics = [
        {
            "name": t["keyword"],
            "score": t["value"],
            "trend": "up" if t["value"] >= 70 else "stable" if t["value"] >= 40 else "down",
        }
        for t in trends[:3]
    ]

    # Use related queries from first trend item as content gap signal
    rising_kws = trends[0].get("related", []) if trends else []
    content_gap = rising_kws[0] if rising_kws else "no dominant angle yet"

    source = "Apify" if os.getenv("APIFY_API_TOKEN", "").strip() else "mock"

    return {
        "overall_score": avg_score,
        "sub_topics": sub_topics,
        "competition_level": competition,
        "content_gap": content_gap,
        "source": source,
    }


async def _max_angle_analysis(client: anthropic.AsyncAnthropic, topic: str, scan: dict) -> list:
    """Max suggests 3 copy angles based on trend data."""
    sub_lines = "\n".join(
        f"- {s['name']} ({s['score']}分, {s['trend']})"
        for s in scan.get("sub_topics", [])
    )
    msg = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=700,
        messages=[{
            "role": "user",
            "content": (
                f"Social media copywriter. Topic: \"{topic}\"\n"
                f"Trends: {sub_lines}\n"
                f"Gap: {scan.get('content_gap', '')}\n\n"
                "Return ONLY valid JSON array, no extra text:\n"
                '[{"angle":"name","hook":"Traditional Chinese hook under 20 chars",'
                '"format":"before/after or tutorial or story","best_platform":"ig",'
                '"strength":"reason under 10 words"}]'
                "\nProvide exactly 3 objects."
            ),
        }],
    )
    return _parse_json(msg.content[0].text)


async def _chief_rank(client: anthropic.AsyncAnthropic, topic: str, angles: list) -> dict:
    """Chief ranks angles by Lazydog.ai brand fit."""
    angle_names = [a.get("angle", "") for a in angles]
    angles_brief = "\n".join(
        f'{i+1}. {a.get("angle","")} — {a.get("hook","")}'
        for i, a in enumerate(angles)
    )
    msg = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        messages=[{
            "role": "user",
            "content": (
                "Lazydog.ai Content Director. Brand: witty, empowering, never corporate.\n"
                f"Topic: \"{topic}\"\nAngles:\n{angles_brief}\n\n"
                "Return ONLY valid JSON, no extra text:\n"
                '{"best_angle":"angle name","best_hook":"hook under 20 chars",'
                '"brand_notes":"emphasise X avoid Y under 15 words",'
                f'"ranking":{json.dumps(angle_names)}' + "}"
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

    source = scan.get("source", "Google Trends")
    source_label = "📡 數據來源：Apify Google Trends HK" if source == "Apify" else "⚠️ 冇 Apify token，以下係 mock 數據"

    return (
        f"📊 *市場快掃：{topic}*\n"
        f"{source_label}\n\n"
        f"整體熱度：{scan.get('overall_score', '?')}/10\n\n"
        f"*相關搜尋趨勢：*\n{sub_lines}\n\n"
        f"{competition}\n"
        f"💡 上升趨勢：_{scan.get('content_gap', '')}_"
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
    # Strip markdown code fences
    if "```" in raw:
        parts = raw.split("```")
        # parts[1] is inside the fences
        raw = parts[1] if len(parts) > 1 else raw
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()
    # Find the first { or [ and last } or ] to extract just the JSON
    start = min(
        (raw.find(c) for c in ["{", "["] if raw.find(c) != -1),
        default=0,
    )
    end = max(raw.rfind("}"), raw.rfind("]")) + 1
    if end > start:
        raw = raw[start:end]
    return json.loads(raw)
