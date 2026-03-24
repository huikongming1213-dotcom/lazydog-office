"""
Commander — Conversational router for TG group brainstorming.
Routes user messages to the right agent persona using Claude.
Maintains per-chat conversation history.
"""
import logging
import os
import anthropic

logger = logging.getLogger(__name__)

COMMANDER_SYSTEM = """
You are the AI coordinator for Lazydog.ai's virtual office.
You manage a team of AI agents who help create viral social media content.

Your team (each has a distinct personality):
- 📊 *Aria* (趨勢分析師): Data-obsessed, loves citing numbers, slightly nerdy but genuinely excited about trends
- ✍️ *Max* (文案師): Creative, witty, Gen-Z energy, loves wordplay and cultural references
- 🎨 *Zoe* (視覺總監): Aesthetic visionary, thinks in colours and vibes, uses words like "mood" and "vibe"
- 👔 *Boss* (主管): Direct, warm but decisive, sees the big picture, keeps the team focused

Rules:
1. Respond IN CHARACTER as the most relevant 1-2 agents for the user's message
2. Keep each agent's reply to 2-3 sentences — conversational, not essay-length
3. Brainstorm genuinely: give real ideas, angles, hooks, not generic advice
4. Always reply in the SAME LANGUAGE the user uses (Cantonese/Traditional Chinese/English)
5. Format each agent reply as: [emoji] *Name*: message (Telegram Markdown)
6. When the user has a clear topic and seems ready, one agent should naturally say: "準備好就打 /go 開始整！"

Do NOT respond with all 4 agents every time. Pick only the most relevant ones.
"""

# Per-chat conversation history: {chat_id: [{"role": ..., "content": ...}]}
_history: dict[str, list] = {}
MAX_HISTORY = 20


async def commander_chat(chat_id: str, user_message: str, username: str = "User") -> str:
    """
    Process a group message and return agent team response.
    Maintains conversation history per Telegram chat.
    """
    if chat_id not in _history:
        _history[chat_id] = []

    history = _history[chat_id]
    history.append({"role": "user", "content": f"{username}: {user_message}"})

    # Trim to max history
    if len(history) > MAX_HISTORY:
        _history[chat_id] = history[-MAX_HISTORY:]
        history = _history[chat_id]

    client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

    try:
        msg = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=600,
            system=COMMANDER_SYSTEM,
            messages=history,
        )
        response = msg.content[0].text.strip()
        history.append({"role": "assistant", "content": response})
        return response

    except Exception as e:
        logger.error(f"[Commander] chat error: {e}")
        return "⚠️ 系統繁忙，請稍後再試。"


async def extract_topic(chat_id: str) -> str | None:
    """
    Extract the main content topic from conversation history.
    Uses Haiku for speed. Returns short topic string or None.
    """
    history = _history.get(chat_id, [])
    if not history:
        return None

    context_text = "\n".join(m["content"] for m in history[-10:])
    client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

    try:
        msg = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=50,
            messages=[{
                "role": "user",
                "content": (
                    "From this conversation, extract the main content/post topic in 5 words or less. "
                    "Reply with ONLY the topic phrase, nothing else:\n\n" + context_text
                ),
            }],
        )
        topic = msg.content[0].text.strip()
        return topic if topic else None

    except Exception as e:
        logger.error(f"[Commander] extract_topic error: {e}")
        return None


def clear_history(chat_id: str):
    """Clear conversation history after pipeline starts."""
    _history.pop(chat_id, None)
