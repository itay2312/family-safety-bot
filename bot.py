import asyncio, aiohttp, time, logging, os, json
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters, ContextTypes
import db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────
BOT_TOKEN          = os.environ["BOT_TOKEN"]
ADMIN_ID           = int(os.environ["ADMIN_TELEGRAM_ID"])
COOLDOWN_SECS      = int(os.environ.get("COOLDOWN_SECONDS", 180))
NO_RESPONSE_MINS   = int(os.environ.get("NO_RESPONSE_MINUTES", 60))
SKIP_WINDOW_MINS   = 20   # unanswered check-in within this window → skip silently
SAFE_WINDOW_MINS   = 20   # confirmed safe within this window → skip + notify admin

# ─────────────────────────────────────────
# ZONE DEFINITIONS
# ─────────────────────────────────────────
ZONES = {
    "Tel Aviv":       ["תל אביב"],
    "Ramat Gan":      ["רמת גן", "גבעתיים"],
    "North Tel Aviv": ["רמת השרון", "הרצליה", "גבעת שמואל"],
    "Petah Tikva":    ["פתח תקווה", "קריית אונו"],
    "Bnei Brak":      ["בני ברק"],
    "Holon":          ["חולון"],
    "Bat Yam":        ["בת ים"],
    "Rishon LeZion":  ["ראשון לציון"],
    "Whole Center":   [
        "גוש דן",
        "תל אביב",
        "רמת גן", "גבעתיים", "בני ברק", "פתח תקווה",
        "חולון", "בת ים", "בת-ים", "אור יהודה",
        "קריית אונו", "גבעת שמואל", "רמת השרון", "הרצליה",
        "יהוד", "מונוסון", "סביון", "גני תקווה",
    ],
    "🌍 Abroad":      [],
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
active_zones     = []

# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────
def is_observer(member: dict) -> bool:
    return (member.get("zone") or "") == "🌍 Abroad"

def get_hit_zones(alert_cities: list) -> list:
    hit = []
    for zone_name, keywords in ZONES.items():
        if zone_name == "🌍 Abroad":
            continue
        for city in alert_cities:
            if any(kw in city for kw in keywords):
                if zone_name not in hit:
                    hit.append(zone_name)
                break
    return hit

def member_is_affected(member_zone: str, hit_zones: list) -> bool:
    if not member_zone or member_zone == "🌍 Abroad":
        return False
    if "Whole Center" in hit_zones:
        return True
    if member_zone == "Whole Center":
        return True
    return member_zone in hit_zones

def who_is_affected_text(hit_zones: list) -> str:
    members = db.get_approved_members()
    affected_names = []
    for m in members:
        if is_observer(m):
            continue
        zone = m.get("zone") or ""
        if member_is_affected(zone, hit_zones):
            affected_names.append(f"*{m['name']}* ({zone})")
    if not affected_names:
        return "No registered members in affected zones."
    return ", ".join(affected_names)

def zone_keyboard():
    buttons = []
    row = []
    for zone_name in ZONES.keys():
        row.append(InlineKeyboardButton(zone_name, callback_data=f"zone:{zone_name}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)

async def notify_observers(bot: Bot, message: str):
    members = db.get_approved_members()
    for m in members:
        if not is_observer(m):
            continue
        try:
            await bot.send_message(chat_id=m["telegram_id"], text=message, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Failed to notify observer {m['name']}: {e}")

async def notify_all_approved(bot: Bot, message: str, exclude_id: int = None):
    members = db.get_approved_members()
    for m in members:
        if exclude_id and m["telegram_id"] == exclude_id:
            continue
        try:
            await bot.send_message(chat_id=m["telegram_id"], text=message, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Failed to notify {m['name']}: {e}")

async def broadcast_status_board(bot: Bot, event_id: str):
    members   = db.get_approved_members()
    checkable = [m for m in members if not is_observer(m)]
    if not checkable:
        return
    responses = {r["telegram_id"]: r["response"] for r in db.get_responses_for_event(event_id)}
    lines = ["📋 *Family Status Update*\n"]
    all_safe     = True
    someone_help = False
    for m in checkable:
        r = responses.get(m["telegram_id"])
        if r == "ok":
            emoji = "✅"
        elif r == "help":
            emoji = "🆘"
            someone_help = True
            all_safe = False
        else:
            emoji = "⏳"
            all_safe = False
        lines.append(f"{emoji} {m['name']}")
    if someone_help:
        lines.append("\n🚨 *Someone needs help — act immediately!*")
    elif all_safe:
        lines.append("\n🎉 *Everyone is safe!*")
    else:
        lines.append("\n⏳ _Still waiting for some responses..._")
    board_text = "\n".join(lines)
    for m in members:
        try:
            await bot.send_message(chat_id=m["telegram_id"], text=board_text, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Status board failed for {m['name']}: {e}")

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
            role = "🌍 Observer" if is_observer(member) else "📍 Member"
            await update.message.reply_text(f"✅ You're already registered as {role}, {name}!")
        elif status == "pending":
            await update.message.reply_text("⏳ Your request is pending admin approval. Hang tight!")
        elif status == "rejected":
            await update.message.reply_text("❌ Your request was not approved. Contact the admin.")
        return
    db.add_member(uid, name, status="pending")
    ctx.user_data["awaiting_name"] = True
    await update.message.reply_text(
        "👋 Welcome to the *Family Safety Bot!*\n\n"
        "You'll receive updates about rocket alerts affecting the family.\n\n"
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
    await update.message.reply_text(
        f"Nice to meet you, *{full_name}!* 👋\n\n"
        "📍 Where are you based?\n\n"
        "If you're *outside Israel*, choose 🌍 *Abroad* — "
        "you'll get full updates about the family without being asked to check in yourself:",
        parse_mode="Markdown",
        reply_markup=zone_keyboard()
    )

# ─────────────────────────────────────────
# /PING — any approved member can check on the family
# ─────────────────────────────────────────
async def cmd_ping(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid    = update.effective_user.id
    member = db.get_member(uid)
    if not member or member["status"] != "approved":
        await update.message.reply_text("❌ You need to be an approved member to send a ping.")
        return

    sender_name = member["name"]
    event_id    = db.log_alert_end(zones=f"Ping from {sender_name}", is_test=False)

    global current_event_id
    current_event_id = event_id

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ I'm OK",    callback_data=f"ok:{event_id}"),
        InlineKeyboardButton("❗ Need Help", callback_data=f"help:{event_id}"),
    ]])

    members = db.get_approved_members()
    sent = 0
    for m in members:
        if m["telegram_id"] == uid:
            continue  # don't ping yourself
        try:
            if is_observer(m):
                # Observers just get the notification, no buttons
                await ctx.bot.send_message(
                    chat_id=m["telegram_id"],
                    text=f"💛 *{sender_name}* is checking in on the family.",
                    parse_mode="Markdown"
                )
            else:
                await ctx.bot.send_message(
                    chat_id=m["telegram_id"],
                    text=f"💛 *{sender_name} wants to know you're OK.*\n\nAre you safe?",
                    parse_mode="Markdown",
                    reply_markup=keyboard
                )
            sent += 1
        except Exception as e:
            logger.error(f"Ping failed to {m['name']}: {e}")

    await update.message.reply_text(
        f"✅ Ping sent to {sent} people. You'll see their responses as they come in."
    )
    logger.info(f"Ping sent by {sender_name} to {sent} members")

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
        is_abroad = zone_name == "🌍 Abroad"
        if is_abroad:
            confirmation = (
                "🌍 Got it — you're set as an *Observer*.\n\n"
                "You'll receive:\n"
                "• 🚨 Alert notifications when family is affected\n"
                "• ✅ Updates as each person checks in\n\n"
                "You won't be asked to check in yourself.\n\n"
                "Waiting for admin approval... 🙏"
            )
        else:
            confirmation = (
                f"📍 Got it — *{zone_name}*.\n\n"
                "You'll receive safety check-ins after rocket alerts in your area.\n\n"
                "Waiting for admin approval... 🙏"
            )
        await query.edit_message_text(confirmation, parse_mode="Markdown")
        role_label = "🌍 Observer (Abroad)" if is_abroad else f"📍 Member — {zone_name}"
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Approve", callback_data=f"approve:{uid}"),
            InlineKeyboardButton("❌ Reject",  callback_data=f"reject:{uid}"),
        ]])
        await ctx.bot.send_message(
            chat_id=ADMIN_ID,
            text=(f"🆕 *New request*\n\nName: *{member['name']}*\nRole: {role_label}\nTelegram ID: `{uid}`"),
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        return

    # ── Admin approve/reject ──
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
            is_abroad = zone == "🌍 Abroad"
            await query.edit_message_text(
                f"✅ *{member['name']}* approved.\nRole: {'🌍 Observer' if is_abroad else f'📍 {zone}'}",
                parse_mode="Markdown"
            )
            if is_abroad:
                await ctx.bot.send_message(
                    chat_id=target_uid,
                    text=(
                        "🎉 You've been approved as an *Observer!*\n\n"
                        "You'll now receive real-time updates whenever family members "
                        "are experiencing rocket alerts.\n\nStay safe 🙏"
                    ),
                    parse_mode="Markdown"
                )
            else:
                await ctx.bot.send_message(
                    chat_id=target_uid,
                    text=(
                        f"🎉 You've been approved!\n\n"
                        f"📍 Your alert zone: *{zone}*\n\n"
                        f"You'll receive safety check-ins after rocket alerts in your area.\n\n"
                        f"You can also send /ping anytime to check on the family."
                    ),
                    parse_mode="Markdown"
                )
        else:
            db.set_status(target_uid, "rejected")
            await query.edit_message_text(f"❌ *{member['name']}* rejected.", parse_mode="Markdown")
            await ctx.bot.send_message(chat_id=target_uid, text="❌ Your request was not approved. Contact the admin.")
        return

    # ── Admin override: force re-send check-in to a skipped member ──
    if data.startswith("override:"):
        if uid != ADMIN_ID:
            return
        parts = data.split(":")
        target_uid = int(parts[1])
        event_id   = parts[2]
        member = db.get_member(target_uid)
        if not member:
            return
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ I'm OK",    callback_data=f"ok:{event_id}"),
            InlineKeyboardButton("❗ Need Help", callback_data=f"help:{event_id}"),
        ]])
        try:
            await ctx.bot.send_message(
                chat_id=target_uid,
                text=f"🚨 *Rocket alert — please confirm you're safe, {member['name']}.*",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
            await query.edit_message_text(f"✅ Override sent to {member['name']}.", parse_mode="Markdown")
        except Exception as e:
            await query.edit_message_text(f"❌ Failed to reach {member['name']}: {e}")
        return

    # ── Check-in response (ok / help) ──
    if ":" in data:
        action, event_id = data.split(":", 1)
        if action not in ("ok", "help"):
            return
        if event_id != current_event_id:
            await query.edit_message_text("This check-in has expired.")
            return
        member = db.get_member(uid)
        name   = member["name"] if member else "Unknown"
        zone   = member.get("zone") or "" if member else ""
        db.save_response(event_id, uid, action)
        if action == "ok":
            await query.edit_message_text(f"✅ Got it, {name}. Glad you're safe!")
            await notify_all_approved(ctx.bot, f"✅ *{name}* is safe.", exclude_id=uid)
        else:
            await query.edit_message_text(f"❗ Help is on the way, {name}. Stay where you are!")
            await notify_all_approved(ctx.bot, f"🚨 *URGENT: {name} needs help!*\n\nCheck on them immediately.", exclude_id=uid)
            await ctx.bot.send_message(
                chat_id=ADMIN_ID,
                text=(f"🚨 *URGENT: {name} needs help!*\nZone: {zone}\nTelegram ID: `{uid}`\nCall them immediately."),
                parse_mode="Markdown"
            )
        await broadcast_status_board(ctx.bot, event_id)

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
                            affected    = who_is_affected_text(hit_zones)
                            logger.info(f"🚨 ALERT: {zones_str}")
                            db.log_alert_start()
                            db.set_alert_state("ALERT", zones_str)
                            await app.bot.send_message(
                                chat_id=ADMIN_ID,
                                text=(f"🚨 *Alert in:* {zones_str}\n\n👥 Affected family: {affected}\n\nWaiting for all-clear..."),
                                parse_mode="Markdown"
                            )
                            await notify_observers(
                                app.bot,
                                f"🚨 *Rocket alert in Israel!*\n\n📍 Zones: *{zones_str}*\n\n👥 Family members in affected areas:\n{affected}\n\n⏳ Check-ins will be sent after the all-clear."
                            )

                    elif alert_state == "ALERT":
                        elapsed = time.time() - (last_alert_time or 0)
                        if elapsed >= COOLDOWN_SECS:
                            alert_state = "IDLE"
                            db.set_alert_state("IDLE")
                            zones_str = ", ".join(active_zones)
                            logger.info("✅ ALL CLEAR")
                            await notify_observers(
                                app.bot,
                                f"✅ *All clear in {zones_str}*\n\nCheck-in messages are being sent to family members now. You'll see their responses as they come in."
                            )
                            event_id         = db.log_alert_end(zones=zones_str)
                            current_event_id = event_id
                            await send_checkins(app.bot, event_id, active_zones)

            except Exception as e:
                logger.warning(f"Poll error: {e}")

            # ── Webhook trigger from GCP poller (via DB) ──
            try:
                wdata = db.pop_webhook_alert()
                if wdata and alert_state == "IDLE":
                    cities    = wdata.get("cities", [])
                    hit_zones = get_hit_zones(cities)
                    if hit_zones:
                        alert_state     = "ALERT"
                        last_alert_time = time.time()
                        active_zones    = hit_zones
                        zones_str       = ", ".join(hit_zones)
                        affected        = who_is_affected_text(hit_zones)
                        logger.info(f"🚨 WEBHOOK ALERT: {zones_str}")
                        db.log_alert_start()
                        db.set_alert_state("ALERT", zones_str)
                        await app.bot.send_message(
                            chat_id=ADMIN_ID,
                            text=(f"🚨 *Alert in:* {zones_str}\n\n👥 Affected family: {affected}\n\nWaiting for all-clear..."),
                            parse_mode="Markdown"
                        )
                        await notify_observers(
                            app.bot,
                            f"🚨 *Rocket alert in Israel!*\n\n📍 Zones: *{zones_str}*\n\n👥 Family members in affected areas:\n{affected}\n\n⏳ Check-ins will be sent after the all-clear."
                        )
            except Exception as e:
                logger.error(f"Webhook alert error: {e}")

            # ── Test trigger from dashboard (via DB) ──
            try:
                if db.pop_test_trigger():
                    zones_str        = "TEST — Tel Aviv area"
                    event_id         = db.log_alert_end(is_test=True, zones=zones_str)
                    current_event_id = event_id
                    await notify_observers(
                        app.bot,
                        f"🧪 *TEST ALERT*\n\n📍 Zones: *{zones_str}*\n\nThis is a test. Check-ins being sent to family members now."
                    )
                    await send_checkins(app.bot, event_id, list(ZONES.keys()), is_test=True)
            except Exception as e:
                logger.error(f"Test trigger error: {e}")

            await asyncio.sleep(1)

# ─────────────────────────────────────────
# SEND CHECK-INS (with spam prevention)
# ─────────────────────────────────────────
async def send_checkins(bot: Bot, event_id: str, hit_zones: list, is_test=False):
    members   = db.get_approved_members()
    now       = time.time()
    skip_secs = SKIP_WINDOW_MINS * 60
    safe_secs = SAFE_WINDOW_MINS * 60
    zones_str  = ", ".join(z for z in hit_zones if z != "🌍 Abroad")
    test_label = "🧪 *TEST* — " if is_test else ""

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ I'm OK",    callback_data=f"ok:{event_id}"),
        InlineKeyboardButton("❗ Need Help", callback_data=f"help:{event_id}"),
    ]])

    sent = 0
    for m in members:
        if is_observer(m):
            continue
        member_zone = m.get("zone") or ""
        if not is_test and not member_is_affected(member_zone, hit_zones):
            continue

        uid = m["telegram_id"]

        if not is_test:
            last_sent     = db.get_last_checkin_sent_time(uid)
            last_response = db.get_latest_response_with_time(uid)
            last_resp_val  = last_response["response"] if last_response else None
            last_resp_time = last_response["responded_at"] if last_response else 0

            if last_sent and (now - last_sent) < skip_secs:
                if last_resp_val == "help":
                    # Always re-ask if they previously said help
                    pass
                elif last_resp_val == "ok" and (now - last_resp_time) < safe_secs:
                    # Confirmed safe recently — notify admin with override
                    mins_ago = int((now - last_resp_time) / 60)
                    override_keyboard = InlineKeyboardMarkup([[
                        InlineKeyboardButton(
                            f"📨 Re-send to {m['name']}",
                            callback_data=f"override:{uid}:{event_id}"
                        )
                    ]])
                    await bot.send_message(
                        chat_id=ADMIN_ID,
                        text=f"⏭ *{m['name']}* confirmed safe {mins_ago}m ago — skipping check-in.\nTap below to force re-send.",
                        parse_mode="Markdown",
                        reply_markup=override_keyboard
                    )
                    logger.info(f"Skipped {m['name']} — confirmed safe {mins_ago}m ago")
                    continue
                elif last_resp_val is None:
                    # Unanswered check-in still pending — skip silently
                    logger.info(f"Skipped {m['name']} — unanswered check-in still pending")
                    continue

        try:
            await bot.send_message(
                chat_id=uid,
                text=(f"{test_label}🚨 *Rocket alert just ended.*\n📍 _{zones_str}_\n\nAre you safe, {m['name']}?"),
                parse_mode="Markdown",
                reply_markup=keyboard
            )
            db.record_checkin_sent(uid)
            sent += 1
        except Exception as e:
            logger.error(f"Failed to reach {m['name']}: {e}")

    logger.info(f"Check-ins sent to {sent} members")
    asyncio.create_task(escalation_loop(bot, event_id))

# ─────────────────────────────────────────
# ESCALATION — admin only after 1 hour
# ─────────────────────────────────────────
async def escalation_loop(bot: Bot, event_id: str):
    await asyncio.sleep(NO_RESPONSE_MINS * 60)
    if event_id != current_event_id:
        return
    no_resp = db.get_no_response(event_id)
    no_resp = [m for m in no_resp if not is_observer(m)]
    if no_resp:
        names = ", ".join(m["name"] for m in no_resp)
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=f"⚠️ *1 hour since alert — still no response from:* {names}\n\nConsider calling them directly.",
            parse_mode="Markdown"
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
        role  = "🌍 Observer" if is_observer(m) else f"📍 {m.get('zone') or '—'}"
        if is_observer(m):
            emoji = "👁"
        lines.append(f"{emoji} {m['name']} — {role}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_test(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin only.")
        return
    global current_event_id
    await update.message.reply_text("🧪 Sending test alert to observers + check-ins to members...")
    zones_str        = "TEST — Tel Aviv area"
    event_id         = db.log_alert_end(is_test=True, zones=zones_str)
    current_event_id = event_id
    await notify_observers(ctx.bot, f"🧪 *TEST ALERT*\n\n📍 Zones: *{zones_str}*\n\nCheck-ins being sent to family members now.")
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
        status_emoji = {"approved": "✅", "pending": "⏳", "rejected": "❌"}.get(m["status"], "❓")
        role = "🌍 Observer" if (m.get("zone") or "") == "🌍 Abroad" else f"📍 {m.get('zone') or '—'}"
        lines.append(f"{status_emoji} {m['name']} — {role}")
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
    app.add_handler(CommandHandler("members", cmd_members))
    app.add_handler(CommandHandler("ping",    cmd_ping))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_name_input))
    await app.initialize()
    await app.start()
    logger.info("🤖 Bot running...")
    await asyncio.gather(poll_alerts(app), app.updater.start_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES))

if __name__ == "__main__":
    asyncio.run(main())
