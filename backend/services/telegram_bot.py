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
from telegram.ext import Application, CallbackQueryHandler, MessageHandler, filters, ContextTypes

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
    _application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_revision_text)
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


async def _handle_revision_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle revision notes sent as a text message after pressing ✏️ Revise."""
    job_id = context.user_data.get("awaiting_revision_for")
    if not job_id:
        return  # Not waiting for revision input

    notes = update.message.text
    context.user_data.pop("awaiting_revision_for", None)

    await _notify_backend(job_id, "revision_requested", notes=notes)
    await update.message.reply_text(
        f"📝 修改意見已收到\n🆔 Job: `{job_id}`\n🔄 Rerouting to copywriter...",
        parse_mode="Markdown",
    )


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
