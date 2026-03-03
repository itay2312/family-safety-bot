import asyncio, aiohttp, time, logging, os, json
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters, ContextTypes
import db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────
BOT_TOKEN        = os.environ["BOT_TOKEN"]
ADMIN_ID         = int(os.environ["ADMIN_TELEGRAM_ID"])
COOLDOWN_SECS    = int(os.environ.get("COOLDOWN_SECONDS", 180))
REMINDER_MINS    = int(os.environ.get("REMINDER_MINUTES", 5))
ESCALATE_MINS    = int(os.environ.get("ESCALATE_MINUTES", 10))

# ─────────────────────────────────────────
# YOUR FAMILY'S ZONES
# Alert will only trigger check-ins if one
# of these Hebrew city/zone names appears
# in the Pikud HaOref alert data.
# ─────────────────────────────────────────
WATCHED_ZONES = [
    # Tel Aviv
    "תל אביב",
    "תל אביב - מזרח",
    "תל אביב - צפון",
    "תל אביב - דרום",
    "תל אביב - מרכז",
    # Ramat Gan & Givatayim
    "רמת גן",
    "גבעתיים",
    # North Tel Aviv area
    "רמת השרון",
    "הרצליה",
    "גבעת שמואל",
    "קריית אונו",
    # Central Israel
    "גוש דן",
    "מרכז",
    "פתח תקווה",
    "בני ברק",
    "רמת גן - מזרח",
    "רמת גן - מערב",
    "אזור",
    "חולון",
    "בת ים",
    "ראשון לציון",
]

OREF_URL = "https://www.oref.org.il/WarningMessages/alert/alerts.json"
OREF_HEADERS = {
    "Referer": "https://www.oref.org.il/",
    "X-Requested-With": "XMLHttpRequest",
}

# ─────────────────────────────────────────
# RUNTIME STATE
# ─────────────────────────────────────────
alert_state      = "IDLE"
last_alert_time  = None
current_event_id = None
last_alert_zones = []  # which zones triggered the last alert

# ─────────────────────────────────────────
# ZONE MATCHING
# ─────────────────────────────────────────
def is_relevant_alert(alert_data: list) -> tuple[bool, list]:
    """
    Returns (True, matched_zones) if any alert city
    matches our watched zones. False otherwise.
    """
    matched = []
    for city in alert_data:
        for zone in WATCHED_ZONES:
            if zone in city or city in zone:
                matched.append(city)
                break
    return len(matched) > 0, matched

# ─────────────────────────────────────────
# ONBOARDING
# ─────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    name = update.effective_user.first_name or "Unknown"
    member = db.get_member(uid)

    if member:
        status = member["status"]
        if status == "approved":
            await update.message.reply_text(f"✅ You're already registered, {name}!")
        elif status == "pending":
            await update.message.reply_text("⏳ Your request is pending admin approval. Hang tight!")
        elif status == "rejected":
            await update.message.reply_text("❌ Your request was not approved. Contact the admin.")
        return

    db.add_member(uid, name, status="pending")
    ctx.user_data["awaiting_name"] = True
    await update.message.reply_text(
        "👋 Welcome to the Family Safety Bot!\n\n"
        "Please reply with your *full name* so the admin can identify you.",
        parse_mode="Markdown"
    )

async def handle_name_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    member = db.get_member(uid)
    if not member or member["status"] != "pending":
        return
    if not ctx.user_data.get("awaiting_name"):
        return

    full_name = update.message.text.strip()[:60]
    db.update_name(uid, full_name)
    ctx.user_data["awaiting_name"] = False

    await update.message.reply_text(
        f"✅ Got it, *{full_name}*! Your request has been sent to the admin for approval. "
        "You'll receive a message once approved.",
        parse_mode="Markdown"
    )

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Approve", callback_data=f"approve:{uid}"),
        InlineKeyboardButton("❌ Reject",  callback_data=f"reject:{uid}"),
    ]])
    await ctx.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"🆕 *New member request*\n\nName: *{full_name}*\nTelegram ID: `{uid}`",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# ─────────────────────────────────────────
# CALLBACKS (approve/reject + check-in)
# ─────────────────────────────────────────
async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("approve:") or data.startswith("reject:"):
        if query.from_user.id != ADMIN_ID:
            return
        action, uid_str = data.split(":", 1)
        uid = int(uid_str)
        member = db.get_member(uid)
        if not member:
            await query.edit_message_text("⚠️ Member not found.")
            return
        if action == "approve":
            db.set_status(uid, "approved")
            await query.edit_message_text(f"✅ *{member['name']}* approved.", parse_mode="Markdown")
            await ctx.bot.send_message(
                chat_id=uid,
                text="🎉 You've been approved! You'll now receive safety check-ins after rocket alerts in the Tel Aviv area."
            )
        else:
            db.set_status(uid, "rejected")
            await query.edit_message_text(f"❌ *{member['name']}* rejected.", parse_mode="Markdown")
            await ctx.bot.send_message(chat_id=uid, text="❌ Your request was not approved.")
        return

    if ":" in data:
        action, event_id = data.split(":", 1)
        if action not in ("ok", "help"):
            return
        if event_id != current_event_id:
            await query.edit_message_text("This check-in has expired.")
            return
        uid    = query.from_user.id
        member = db.get_member(uid)
        name   = member["name"] if member else "Unknown"
        db.save_response(event_id, uid, action)
        if action == "ok":
            await query.edit_message_text(f"✅ Got it, {name}. Glad you're safe!")
            await ctx.bot.send_message(chat_id=ADMIN_ID, text=f"✅ {name} is safe.")
        else:
            await query.edit_message_text(f"❗ Help is on the way, {name}. Stay where you are!")
            await ctx.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"🚨 URGENT: {name} needs help! Call them immediately."
            )

# ─────────────────────────────────────────
# ALERT POLLING
# ─────────────────────────────────────────
async def poll_alerts(app: Application):
    global alert_state, last_alert_time, current_event_id, last_alert_zones

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(
                    OREF_URL, headers=OREF_HEADERS,
                    timeout=aiohttp.ClientTimeout(total=3)
                ) as resp:
                    text = await resp.text(encoding="utf-8-sig")
                    text = text.strip()

                    alert_cities = []
                    relevant     = False

                    if len(text) > 10:
                        try:
                            data = json.loads(text)
                            alert_cities = data.get("data", [])
                            relevant, matched = is_relevant_alert(alert_cities)
                            if relevant:
                                last_alert_zones = matched
                        except Exception:
                            relevant = False

                    if relevant:
                        last_alert_time = time.time()
                        if alert_state == "IDLE":
                            alert_state = "ALERT"
                            zones_str = ", ".join(last_alert_zones[:5])
                            logger.info(f"🚨 RELEVANT ALERT: {zones_str}")
                            db.log_alert_start()
                            # Notify admin immediately
                            await app.bot.send_message(
                                chat_id=ADMIN_ID,
                                text=f"🚨 *Alert in your area!*\n\nZones: {zones_str}\n\nWaiting for all-clear...",
                                parse_mode="Markdown"
                            )
                    elif alert_state == "ALERT":
                        elapsed = time.time() - (last_alert_time or 0)
                        if elapsed >= COOLDOWN_SECS:
                            alert_state = "IDLE"
                            zones_str = ", ".join(last_alert_zones[:5])
                            logger.info("✅ ALL CLEAR — sending check-ins")
                            event_id = db.log_alert_end()
                            current_event_id = event_id
                            await send_checkins(app.bot, event_id, zones_str)

            except Exception as e:
                logger.warning(f"Poll error: {e}")

            # Also check for test trigger from dashboard
            if os.path.exists(".trigger_test"):
                try:
                    os.remove(".trigger_test")
                    event_id = db.log_alert_end(is_test=True)
                    current_event_id = event_id
                    await send_checkins(app.bot, event_id, "TEST — Tel Aviv area")
                except Exception as e:
                    logger.error(f"Test trigger error: {e}")

            await asyncio.sleep(1)

# ─────────────────────────────────────────
# SEND CHECK-INS
# ─────────────────────────────────────────
async def send_checkins(bot: Bot, event_id: str, zones_str: str = ""):
    members = db.get_approved_members()
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ I'm OK",    callback_data=f"ok:{event_id}"),
        InlineKeyboardButton("❗ Need Help", callback_data=f"help:{event_id}"),
    ]])
    zone_line = f"\n📍 _{zones_str}_" if zones_str else ""
    for m in members:
        try:
            await bot.send_message(
                chat_id=m["telegram_id"],
                text=f"🚨 *Rocket alert just ended.*{zone_line}\n\nAre you safe, {m['name']}?",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"Failed to reach {m['name']}: {e}")

    asyncio.create_task(escalation_loop(bot, event_id))

# ─────────────────────────────────────────
# ESCALATION
# ─────────────────────────────────────────
async def escalation_loop(bot: Bot, event_id: str):
    await asyncio.sleep(REMINDER_MINS * 60)
    if event_id != current_event_id:
        return

    no_resp = db.get_no_response(event_id)
    if no_resp:
        names = ", ".join(m["name"] for m in no_resp)
        await bot.send_message(chat_id=ADMIN_ID, text=f"⚠️ No response yet from: {names}")
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ I'm OK",    callback_data=f"ok:{event_id}"),
            InlineKeyboardButton("❗ Need Help", callback_data=f"help:{event_id}"),
        ]])
        for m in no_resp:
            try:
                await bot.send_message(
                    chat_id=m["telegram_id"],
                    text="👋 Reminder: Please confirm you're safe!",
                    reply_markup=keyboard
                )
            except Exception:
                pass

    await asyncio.sleep((ESCALATE_MINS - REMINDER_MINS) * 60)
    still = db.get_no_response(event_id)
    if still:
        names = ", ".join(m["name"] for m in still)
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🚨 URGENT — Still no response from: {names}. Call them directly."
        )

# ─────────────────────────────────────────
# ADMIN COMMANDS
# ─────────────────────────────────────────
async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    members = db.get_approved_members()
    if not members:
        await update.message.reply_text("No approved members yet.")
        return
    lines = [f"🤖 *Bot Status* — Alert state: {alert_state}\n"]
    for m in members:
        r = db.get_latest_response(m["telegram_id"])
        emoji = "✅" if r == "ok" else ("❗" if r == "help" else "⏳")
        lines.append(f"{emoji} {m['name']}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_test(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin only.")
        return
    global current_event_id
    await update.message.reply_text("🧪 Sending test check-in to all approved members...")
    event_id = db.log_alert_end(is_test=True)
    current_event_id = event_id
    await send_checkins(ctx.bot, event_id, "TEST — Tel Aviv area")

async def cmd_zones(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Show which zones are being watched"""
    if update.effective_user.id != ADMIN_ID:
        return
    zones = "\n".join(f"• {z}" for z in WATCHED_ZONES)
    await update.message.reply_text(
        f"📍 *Watching these zones:*\n\n{zones}",
        parse_mode="Markdown"
    )

async def cmd_members(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    members = db.get_all_members()
    if not members:
        await update.message.reply_text("No members yet.")
        return
    lines = ["👥 *All Members:*\n"]
    for m in members:
        emoji = {"approved": "✅", "pending": "⏳", "rejected": "❌"}.get(m["status"], "❓")
        lines.append(f"{emoji} {m['name']} (`{m['telegram_id']}`)")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────
async def main():
    db.init()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("status",  cmd_status))
    app.add_handler(CommandHandler("test",    cmd_test))
    app.add_handler(CommandHandler("zones",   cmd_zones))
    app.add_handler(CommandHandler("members", cmd_members))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_name_input))

    await app.initialize()
    await app.start()
    logger.info("🤖 Bot running with Tel Aviv area zone filter...")

    await asyncio.gather(
        poll_alerts(app),
        app.updater.start_polling(),
    )

if __name__ == "__main__":
    asyncio.run(main())
