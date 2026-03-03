import asyncio, aiohttp, time, logging, os, json
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters, ContextTypes
import db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────
BOT_TOKEN     = os.environ["BOT_TOKEN"]
ADMIN_ID      = int(os.environ["ADMIN_TELEGRAM_ID"])
COOLDOWN_SECS = int(os.environ.get("COOLDOWN_SECONDS", 180))
REMINDER_MINS = int(os.environ.get("REMINDER_MINUTES", 5))
ESCALATE_MINS = int(os.environ.get("ESCALATE_MINUTES", 10))

# ─────────────────────────────────────────
# ZONE DEFINITIONS
# Each entry: "Display Name": ["Hebrew keywords"]
# If ANY keyword appears in the alert data,
# that zone is considered "hit".
# ─────────────────────────────────────────
ZONES = {
    "Tel Aviv":        ["תל אביב"],
    "Ramat Gan":       ["רמת גן", "גבעתיים"],
    "North Tel Aviv":  ["רמת השרון", "הרצליה", "גבעת שמואל"],
    "Petah Tikva":     ["פתח תקווה", "קריית אונו"],
    "Bnei Brak":       ["בני ברק"],
    "Holon":           ["חולון"],
    "Bat Yam":         ["בת ים"],
    "Rishon LeZion":   ["ראשון לציון"],
    "Whole Center":    ["גוש דן", "מרכז", "אזור"],
}

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
active_zones     = []  # zones hit in current/last alert

# ─────────────────────────────────────────
# ZONE HELPERS
# ─────────────────────────────────────────
def get_hit_zones(alert_cities: list) -> list:
    """Return list of display-name zones that were hit."""
    hit = []
    for zone_name, keywords in ZONES.items():
        for city in alert_cities:
            if any(kw in city for kw in keywords):
                if zone_name not in hit:
                    hit.append(zone_name)
                break
    return hit

def member_is_affected(member_zone: str, hit_zones: list) -> bool:
    if not member_zone:
        return True  # no zone set → always notify
    if member_zone == "Whole Center":
        return True  # whole center = always relevant
    return member_zone in hit_zones

def zone_keyboard():
    """Build an inline keyboard with all zone choices."""
    buttons = []
    row = []
    for i, zone_name in enumerate(ZONES.keys()):
        row.append(InlineKeyboardButton(zone_name, callback_data=f"zone:{zone_name}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)

# ─────────────────────────────────────────
# ONBOARDING — /start
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

    # Step 1 — ask for name
    db.add_member(uid, name, status="pending")
    ctx.user_data["awaiting_name"] = True
    await update.message.reply_text(
        "👋 Welcome to the *Family Safety Bot!*\n\n"
        "You'll receive a check-in message after rocket alerts in your area.\n\n"
        "First — please reply with your *full name*:",
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
    ctx.user_data["awaiting_zone"] = True

    # Step 2 — ask for zone
    await update.message.reply_text(
        f"Nice to meet you, *{full_name}!* 👋\n\n"
        "📍 Now tap the area where you live so we only alert you when *your* area is targeted:",
        parse_mode="Markdown",
        reply_markup=zone_keyboard()
    )

# ─────────────────────────────────────────
# CALLBACKS
# ─────────────────────────────────────────
async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data  = query.data
    uid   = query.from_user.id

    # ── Zone selection during onboarding ──
    if data.startswith("zone:"):
        zone_name = data.split(":", 1)[1]
        member = db.get_member(uid)
        if not member or member["status"] != "pending":
            return

        db.set_zone(uid, zone_name)
        ctx.user_data["awaiting_zone"] = False

        await query.edit_message_text(
            f"📍 Got it — *{zone_name}*.\n\n"
            "Your request has been sent to the admin for approval. "
            "You'll get a message once you're approved! 🙏",
            parse_mode="Markdown"
        )

        # Notify admin
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Approve", callback_data=f"approve:{uid}"),
            InlineKeyboardButton("❌ Reject",  callback_data=f"reject:{uid}"),
        ]])
        await ctx.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                f"🆕 *New member request*\n\n"
                f"Name: *{member['name']}*\n"
                f"Zone: *{zone_name}*\n"
                f"Telegram ID: `{uid}`"
            ),
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        return

    # ── Admin approve / reject ──
    if data.startswith("approve:") or data.startswith("reject:"):
        if uid != ADMIN_ID:
            return
        action, uid_str = data.split(":", 1)
        target_uid = int(uid_str)
        member = db.get_member(target_uid)
        if not member:
            await query.edit_message_text("⚠️ Member not found.")
            return
        if action == "approve":
            db.set_status(target_uid, "approved")
            zone = member.get("zone") or "not set"
            await query.edit_message_text(
                f"✅ *{member['name']}* approved.\nZone: {zone}",
                parse_mode="Markdown"
            )
            await ctx.bot.send_message(
                chat_id=target_uid,
                text=(
                    f"🎉 You've been approved!\n\n"
                    f"📍 Your alert zone: *{zone}*\n\n"
                    "You'll receive safety check-ins whenever there's a rocket alert in your area."
                ),
                parse_mode="Markdown"
            )
        else:
            db.set_status(target_uid, "rejected")
            await query.edit_message_text(
                f"❌ *{member['name']}* rejected.",
                parse_mode="Markdown"
            )
            await ctx.bot.send_message(
                chat_id=target_uid,
                text="❌ Your request was not approved. Contact the admin if you think this is a mistake."
            )
        return

    # ── Check-in responses ──
    if ":" in data:
        action, event_id = data.split(":", 1)
        if action not in ("ok", "help"):
            return
        if event_id != current_event_id:
            await query.edit_message_text("This check-in has expired.")
            return
        member = db.get_member(uid)
        name   = member["name"] if member else "Unknown"
        db.save_response(event_id, uid, action)
        members = db.get_approved_members()

        if action == "ok":
            await query.edit_message_text(f"✅ Got it, {name}. Glad you're safe!")
            # Notify everyone except the person who just responded
            for m in members:
                if m["telegram_id"] == uid:
                    continue
                try:
                    await ctx.bot.send_message(
                        chat_id=m["telegram_id"],
                        text=f"✅ *{name}* is safe.",
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass

        else:
            await query.edit_message_text(f"❗ Help is on the way, {name}. Stay where you are!")
            # Notify EVERYONE immediately (including admin)
            for m in members:
                if m["telegram_id"] == uid:
                    continue
                try:
                    await ctx.bot.send_message(
                        chat_id=m["telegram_id"],
                        text=f"🚨 *URGENT: {name} needs help!*\n\nCheck on them immediately.",
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass
            # Always notify admin separately with more detail
            await ctx.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"🚨 *URGENT: {name} needs help!*\n\nTelegram ID: `{uid}`\nCall them immediately.",
                parse_mode="Markdown"
            )

# ─────────────────────────────────────────
# ALERT POLLING
# ─────────────────────────────────────────
async def poll_alerts(app: Application):
    global alert_state, last_alert_time, current_event_id, active_zones

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(
                    OREF_URL, headers=OREF_HEADERS,
                    timeout=aiohttp.ClientTimeout(total=3)
                ) as resp:
                    text = await resp.text(encoding="utf-8-sig")
                    text = text.strip()

                    hit_zones = []
                    if len(text) > 10:
                        try:
                            payload   = json.loads(text)
                            cities    = payload.get("data", [])
                            hit_zones = get_hit_zones(cities)
                        except Exception:
                            pass

                    if hit_zones:
                        last_alert_time = time.time()
                        active_zones    = hit_zones
                        if alert_state == "IDLE":
                            alert_state = "ALERT"
                            zones_str   = ", ".join(hit_zones)
                            logger.info(f"🚨 ALERT: {zones_str}")
                            db.log_alert_start()
                            # Write state for dashboard to read
                            open(".alert_state", "w").write(f"ALERT|{zones_str}")
                            await app.bot.send_message(
                                chat_id=ADMIN_ID,
                                text=f"🚨 *Alert in:* {zones_str}\n\nWaiting for all-clear...",
                                parse_mode="Markdown"
                            )

                    elif alert_state == "ALERT":
                        elapsed = time.time() - (last_alert_time or 0)
                        if elapsed >= COOLDOWN_SECS:
                            alert_state = "IDLE"
                            open(".alert_state", "w").write("IDLE|")
                            logger.info("✅ ALL CLEAR")
                            event_id         = db.log_alert_end()
                            current_event_id = event_id
                            await send_checkins(app.bot, event_id, active_zones)

            except Exception as e:
                logger.warning(f"Poll error: {e}")

            # Test trigger from dashboard
            if os.path.exists(".trigger_test"):
                try:
                    os.remove(".trigger_test")
                    event_id         = db.log_alert_end(is_test=True)
                    current_event_id = event_id
                    # For test, hit all zones
                    await send_checkins(app.bot, event_id, list(ZONES.keys()), is_test=True)
                except Exception as e:
                    logger.error(f"Test trigger error: {e}")

            await asyncio.sleep(1)

# ─────────────────────────────────────────
# SEND CHECK-INS (zone-aware)
# ─────────────────────────────────────────
async def send_checkins(bot: Bot, event_id: str, hit_zones: list, is_test=False):
    members  = db.get_approved_members()
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ I'm OK",    callback_data=f"ok:{event_id}"),
        InlineKeyboardButton("❗ Need Help", callback_data=f"help:{event_id}"),
    ]])
    zones_str  = ", ".join(hit_zones)
    test_label = "🧪 *TEST* — " if is_test else ""

    sent = 0
    for m in members:
        member_zone = m.get("zone") or ""
        if not is_test and not member_is_affected(member_zone, hit_zones):
            logger.info(f"Skipping {m['name']} — zone {member_zone} not affected")
            continue
        try:
            await bot.send_message(
                chat_id=m["telegram_id"],
                text=(
                    f"{test_label}🚨 *Rocket alert just ended.*\n"
                    f"📍 _{zones_str}_\n\n"
                    f"Are you safe, {m['name']}?"
                ),
                parse_mode="Markdown",
                reply_markup=keyboard
            )
            sent += 1
        except Exception as e:
            logger.error(f"Failed to reach {m['name']}: {e}")

    logger.info(f"Check-ins sent to {sent}/{len(members)} members")
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
    lines = [f"🤖 *Status* — Alert: {alert_state}\n"]
    for m in members:
        r     = db.get_latest_response(m["telegram_id"])
        emoji = "✅" if r == "ok" else ("❗" if r == "help" else "⏳")
        zone  = m.get("zone") or "no zone"
        lines.append(f"{emoji} {m['name']} — 📍 {zone}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_test(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin only.")
        return
    global current_event_id
    await update.message.reply_text("🧪 Sending test check-in to all approved members...")
    event_id         = db.log_alert_end(is_test=True)
    current_event_id = event_id
    await send_checkins(ctx.bot, event_id, list(ZONES.keys()), is_test=True)

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
        zone  = m.get("zone") or "no zone"
        lines.append(f"{emoji} {m['name']} — 📍 {zone}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_zones(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    lines = ["📍 *Available zones:*\n"]
    for name, keywords in ZONES.items():
        lines.append(f"• *{name}:* {', '.join(keywords)}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────
async def main():
    db.init()

    # Make sure zone column exists (for existing databases)
    try:
        import sqlite3
        conn = sqlite3.connect(os.environ.get("DB_PATH", "family_safety.db"))
        conn.execute("ALTER TABLE members ADD COLUMN zone TEXT")
        conn.commit()
        conn.close()
    except Exception:
        pass  # column already exists

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
    logger.info("🤖 Bot running with per-member zone filtering...")

    await asyncio.gather(
        poll_alerts(app),
        app.updater.start_polling(),
    )

if __name__ == "__main__":
    asyncio.run(main())
