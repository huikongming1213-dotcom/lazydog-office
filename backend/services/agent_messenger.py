"""
Agent Messenger — each agent sends messages via their own bot token.
Falls back to TELEGRAM_BOT_TOKEN if the agent's token is not set.
"""
import logging
import os
from telegram import Bot

logger = logging.getLogger(__name__)

_AGENT_TOKEN_ENV = {
    "trend_analyst": "ARIA_BOT_TOKEN",
    "copywriter":    "MAX_BOT_TOKEN",
    "image_gen":     "ZOE_BOT_TOKEN",
    "supervisor":    "CHIEF_BOT_TOKEN",
}


async def send_as(agent: str, text: str):
    """Send a message to the group as the specified agent's own bot."""
    token_env = _AGENT_TOKEN_ENV.get(agent)
    token = (os.getenv(token_env, "") if token_env else "").strip()

    if not token:
        # Fallback: use main Commander bot
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

    group_chat_id = os.getenv("TELEGRAM_GROUP_CHAT_ID", "").strip()

    if not token or not group_chat_id:
        logger.warning(f"[AgentMessenger] Skipping message for {agent} (no token/chat_id)")
        return

    try:
        bot = Bot(token=token)
        await bot.send_message(
            chat_id=group_chat_id,
            text=text,
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"[AgentMessenger] {agent} failed to send: {e}")
