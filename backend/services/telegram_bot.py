"""
Telegram Bot Service — Webhook Mode
- Group discussion: agent activity messages → TELEGRAM_GROUP_CHAT_ID
- Approval flow: supervisor sends preview → TELEGRAM_APPROVAL_CHAT_ID
- Inline buttons: ✅ Approve / ✏️ Revise / ❌ Reject / 🔄 Regenerate
- On button press: resume N8N Wait Webhook
"""
import logging
import os
import httpx
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters, ContextTypes
import asyncio
from backend.agents.commander import commander_chat, extract_topic, clear_history, detect_topic_proposal
from backend.agents.strategist import run_strategy_discussion

logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
GROUP_CHAT_ID = os.getenv("TELEGRAM_GROUP_CHAT_ID", "")
APPROVAL_CHAT_ID = os.getenv("TELEGRAM_APPROVAL_CHAT_ID", "")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

# Will be initialised in build_application()
_application: Application | None = None
_bot: Bot | None = None


def build_application() -> Application:
    """Build the telegram Application (no polling — webhook mode)."""
    global _application, _bot
    _application = Application.builder().token(BOT_TOKEN).build()
    _bot = _application.bot

    # Register handlers
    _application.add_handler(CallbackQueryHandler(_handle_approval_callback))
    _application.add_handler(CommandHandler("go", _handle_go_command))
    _application.add_handler(CommandHandler("status", _handle_status_command))
    _application.add_handler(CommandHandler("clear", _handle_clear_command))
    _application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_text_message)
    )
    return _application


async def setup_webhook(webhook_url: str):
    """Register webhook URL with Telegram."""
    if not BOT_TOKEN:
        logger.warning("[TGBot] No BOT_TOKEN — skipping webhook setup")
        return
    bot = Bot(token=BOT_TOKEN)
    await bot.set_webhook(url=webhook_url)
    logger.info(f"[TGBot] Webhook set to {webhook_url}")


async def process_update(update_data: dict):
    """Process an incoming Telegram update (called from FastAPI webhook endpoint)."""
    if _application is None:
        logger.error("[TGBot] Application not initialised")
        return
    update = Update.de_json(update_data, _application.bot)
    await _application.process_update(update)


# ── Outgoing messages ──────────────────────────────────────────────────────────

async def send_group_message(text: str):
    """Send a message to the agent discussion group."""
    if not BOT_TOKEN or not GROUP_CHAT_ID:
        logger.warning(f"[TGBot] Group message skipped (no config): {text[:80]}")
        return
    try:
        bot = Bot(token=BOT_TOKEN)
        await bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=text,
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"[TGBot] Failed to send group message: {e}")


async def send_approval_request(
    job_id: str,
    ig_caption: str,
    captions: dict,
    image_url: str,
    feedback: str,
    approved_by_ai: bool,
):
    """Send approval preview with inline keyboard to APPROVAL_CHAT_ID."""
    if not BOT_TOKEN or not APPROVAL_CHAT_ID:
        logger.warning(f"[TGBot] Approval message skipped (no config): job={job_id}")
        return

    ai_verdict = "✅ AI Recommends Approval" if approved_by_ai else "⚠️ AI Flagged Issues"
    hashtags_str = ""

    text = (
        f"🐾 *Lazydog.ai新帖待審核*\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📋 任務：`{job_id}`\n"
        f"🤖 {ai_verdict}\n"
        f"💬 AI Feedback: _{feedback[:200]}_\n\n"
        f"📝 *IG Caption:*\n{ig_caption[:400]}\n\n"
        f"🔗 [圖片預覽]({image_url})"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ 批准發佈", callback_data=f"approve:{job_id}"),
            InlineKeyboardButton("✏️ 修改", callback_data=f"revise:{job_id}"),
        ],
        [
            InlineKeyboardButton("❌ 拒絕", callback_data=f"reject:{job_id}"),
            InlineKeyboardButton("🔄 重新生成", callback_data=f"regenerate:{job_id}"),
        ],
    ])

    try:
        bot = Bot(token=BOT_TOKEN)
        await bot.send_message(
            chat_id=APPROVAL_CHAT_ID,
            text=text,
            parse_mode="Markdown",
            reply_markup=keyboard,
            disable_web_page_preview=False,
        )
        # Also notify the group
        await send_group_message(
            f"👔 *主管審核完成*\n"
            f"🆔 Job: `{job_id}`\n"
            f"{ai_verdict}\n"
            f"⏳ 等待人工審核..."
        )
    except Exception as e:
        logger.error(f"[TGBot] Failed to send approval request: {e}")


# ── Callback handlers ──────────────────────────────────────────────────────────

async def _handle_approval_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline button presses from the approval message."""
    query = update.callback_query
    await query.answer()

    data = query.data  # e.g. "approve:abc-123"
    action, job_id = data.split(":", 1)

    if action == "approve":
        await _notify_backend(job_id, "approved", notes=None)
        await query.edit_message_text(
            f"✅ *批准發佈*\n🆔 Job: `{job_id}`\n🚀 Publishing...",
            parse_mode="Markdown",
        )

    elif action == "reject":
        await _notify_backend(job_id, "rejected", notes=None)
        await query.edit_message_text(
            f"❌ *已拒絕*\n🆔 Job: `{job_id}`",
            parse_mode="Markdown",
        )

    elif action == "regenerate":
        await _notify_backend(job_id, "regenerate", notes=None)
        await query.edit_message_text(
            f"🔄 *重新生成中...*\n🆔 Job: `{job_id}`",
            parse_mode="Markdown",
        )

    elif action == "revise":
        # Store job_id in user_data so next text message is treated as revision notes
        context.user_data["awaiting_revision_for"] = job_id
        await query.edit_message_text(
            f"✏️ *請輸入修改意見*\n🆔 Job: `{job_id}`\n\n請直接回覆修改要求：",
            parse_mode="Markdown",
        )

    group_action_map = {
        "approve": "✅ 人工批准，準備發佈！",
        "reject": "❌ 內容被拒絕",
        "regenerate": "🔄 要求重新生成",
        "revise": "✏️ 要求修改文案",
    }
    await send_group_message(
        f"🔔 *審核更新*\n"
        f"🆔 Job: `{job_id}`\n"
        f"{group_action_map.get(action, action)}"
    )


async def _handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Dispatch incoming text messages:
    - If awaiting revision notes → handle revision
    - If from group chat → route to agent commander for brainstorming
    """
    if not update.message or not update.message.text:
        return

    # Priority 1: revision notes (approval chat flow)
    job_id = context.user_data.get("awaiting_revision_for")
    if job_id:
        notes = update.message.text
        context.user_data.pop("awaiting_revision_for", None)
        await _notify_backend(job_id, "revision_requested", notes=notes)
        await update.message.reply_text(
            f"📝 修改意見已收到\n🆔 Job: `{job_id}`\n🔄 Rerouting to copywriter...",
            parse_mode="Markdown",
        )
        return

    # Priority 2: group chat → agent team conversation
    chat_id = str(update.message.chat_id)
    if chat_id == GROUP_CHAT_ID:
        user = update.message.from_user
        username = user.first_name or user.username or "User"
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")

        # Detect if user is proposing a content topic → trigger strategy discussion
        topic = await detect_topic_proposal(update.message.text)
        if topic:
            await update.message.reply_text(
                f"💡 *好想法！* 俾 Aria 先掃下 *{topic}* 嘅 market data...",
                parse_mode="Markdown",
            )
            asyncio.create_task(run_strategy_discussion(topic))
            return

        # Normal group conversation
        response = await commander_chat(chat_id, update.message.text, username)
        await update.message.reply_text(response, parse_mode="Markdown")


async def _handle_go_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /go [topic] — Start the full content pipeline.
    If no topic given, extracts it from conversation history.
    """
    chat_id = str(update.message.chat_id)

    # Get topic from command args or extract from history
    if context.args:
        topic = " ".join(context.args)
    else:
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        topic = await extract_topic(chat_id)

    if not topic:
        await update.message.reply_text(
            "❓ 唔知 topic 係咩。請用 `/go <你的 topic>` 或者先係 group 傾下先。",
            parse_mode="Markdown",
        )
        return

    await update.message.reply_text(
        f"🚀 *開始整！*\n📌 Topic: {topic}\n\n📊 Aria 出動緊...",
        parse_mode="Markdown",
    )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{BACKEND_URL}/pipeline/run",
                json={
                    "topic": topic,
                    "platforms": ["ig", "linkedin", "x", "threads", "fb"],
                    "tone": "casual",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            job_id = data.get("job_id", "unknown")

        clear_history(chat_id)
        await update.message.reply_text(
            f"✅ Pipeline 啟動！\n🆔 `{job_id}`\n\n各 agent 開始工作，完成後主管會係 approval chat 發審核通知。",
            parse_mode="Markdown",
        )

    except Exception as e:
        logger.error(f"[TGBot] /go pipeline start failed: {e}")
        await update.message.reply_text("❌ 啟動失敗，請稍後再試或檢查 backend logs。")


async def _handle_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/status — Show recent jobs status."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{BACKEND_URL}/jobs?limit=5")
            jobs = resp.json()

        if not jobs:
            await update.message.reply_text("📭 暫時冇進行中嘅 jobs。")
            return

        lines = ["📋 *最近 Jobs:*\n"]
        for j in jobs:
            status_emoji = {
                "pending": "⏳", "trend_done": "📊", "copy_done": "✍️",
                "image_done": "🎨", "pending_approval": "👔",
                "approved": "✅", "rejected": "❌", "failed": "💥",
            }.get(j["status"], "❓")
            lines.append(f"{status_emoji} `{j['id'][:8]}` — {j['topic'][:30]} ({j['status']})")

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    except Exception as e:
        logger.error(f"[TGBot] /status failed: {e}")
        await update.message.reply_text("❌ 查詢失敗。")


async def _handle_clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/clear — Clear conversation history for this chat."""
    chat_id = str(update.message.chat_id)
    clear_history(chat_id)
    await update.message.reply_text("🗑️ 對話記錄已清除，可以開始新話題。")


async def _notify_backend(job_id: str, action: str, notes: str | None):
    """
    Notify FastAPI backend of the approval decision.
    Backend will then resume the N8N Wait Webhook.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            payload = {"job_id": job_id, "action": action}
            if notes:
                payload["notes"] = notes
            await client.post(f"{BACKEND_URL}/webhooks/approval-callback", json=payload)
    except Exception as e:
        logger.error(f"[TGBot] Failed to notify backend: {e}")
