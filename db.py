import pg8000.native, ssl, os, time, uuid, json

def _parse_url():
    url = os.environ["DATABASE_URL"]
    url = url.replace("postgresql://", "").replace("postgres://", "")
    user_pass, rest = url.split("@", 1)
    user, password = user_pass.split(":", 1)
    host_port, dbname = rest.split("/", 1)
    dbname = dbname.split("?")[0]
    if ":" in host_port:
        host, port = host_port.split(":", 1)
        port = int(port)
    else:
        host = host_port
        port = 5432
    return user, password, host, port, dbname

def _conn():
    user, password, host, port, dbname = _parse_url()
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    return pg8000.native.Connection(
        user=user, password=password, host=host,
        port=port, database=dbname, ssl_context=ssl_ctx
    )

def init():
    con = _conn()
    con.run("""
        CREATE TABLE IF NOT EXISTS members (
            telegram_id BIGINT PRIMARY KEY,
            name TEXT,
            status TEXT DEFAULT 'pending',
            zone TEXT,
            joined_at BIGINT
        )
    """)
    con.run("""
        CREATE TABLE IF NOT EXISTS alert_events (
            id TEXT PRIMARY KEY,
            started_at BIGINT,
            ended_at BIGINT,
            zones TEXT,
            is_test BOOLEAN DEFAULT FALSE
        )
    """)
    con.run("""
        CREATE TABLE IF NOT EXISTS responses (
            id TEXT PRIMARY KEY,
            event_id TEXT,
            telegram_id BIGINT,
            response TEXT,
            responded_at BIGINT,
            UNIQUE(event_id, telegram_id)
        )
    """)
    # Shared state table — used instead of files so Flask + bot can communicate
    con.run("""
        CREATE TABLE IF NOT EXISTS kv_store (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at BIGINT
        )
    """)
    # Tracks when each member last received a check-in message (for spam prevention)
    con.run("""
        CREATE TABLE IF NOT EXISTS checkin_sent (
            telegram_id BIGINT PRIMARY KEY,
            sent_at BIGINT
        )
    """)
    try:
        con.run("ALTER TABLE alert_events ADD COLUMN response_count INTEGER DEFAULT 0")
    except Exception:
        pass
    con.close()

def record_checkin_sent(telegram_id):
    """Record the timestamp when a check-in was sent to a member."""
    con = _conn()
    con.run(
        "INSERT INTO checkin_sent (telegram_id, sent_at) VALUES (:uid, :ts) "
        "ON CONFLICT (telegram_id) DO UPDATE SET sent_at = :ts",
        uid=telegram_id, ts=int(time.time())
    )
    con.close()

def get_last_checkin_sent_time(telegram_id):
    """Return the epoch timestamp of the last check-in sent, or None."""
    con = _conn()
    rows = con.run("SELECT sent_at FROM checkin_sent WHERE telegram_id = :uid", uid=telegram_id)
    con.close()
    return rows[0][0] if rows else None

def get_latest_response_with_time(telegram_id):
    """Return the latest response dict {response, responded_at} or None."""
    con = _conn()
    rows = con.run(
        "SELECT response, responded_at FROM responses WHERE telegram_id = :uid ORDER BY responded_at DESC LIMIT 1",
        uid=telegram_id
    )
    con.close()
    if rows:
        return {"response": rows[0][0], "responded_at": rows[0][1]}
    return None

# ── KV helpers ────────────────────────────────────────────────────────────────

def _kv_set(key, value):
    con = _conn()
    con.run(
        "INSERT INTO kv_store (key, value, updated_at) VALUES (:k, :v, :ts) "
        "ON CONFLICT (key) DO UPDATE SET value = :v, updated_at = :ts",
        k=key, v=value, ts=int(time.time())
    )
    con.close()

def _kv_get(key):
    con = _conn()
    rows = con.run("SELECT value FROM kv_store WHERE key = :k", k=key)
    con.close()
    return rows[0][0] if rows else None

def _kv_get_ts(key):
    con = _conn()
    rows = con.run("SELECT value, updated_at FROM kv_store WHERE key = :k", k=key)
    con.close()
    if rows:
        return rows[0][0], rows[0][1]
    return None, None

# ── Poller ping ───────────────────────────────────────────────────────────────

def update_ping_timestamp():
    _kv_set("last_ping", str(time.time()))

def get_ping_timestamp():
    val = _kv_get("last_ping")
    return float(val) if val else None

# ── Webhook alert queue ───────────────────────────────────────────────────────
# Flask writes here; bot.py reads and clears it.

def push_webhook_alert(alert_id, cities):
    """Store incoming alert from GCP poller. Bot polls this."""
    _kv_set("pending_alert", json.dumps({"id": alert_id, "cities": cities}))

def pop_webhook_alert():
    """Read and clear the pending alert. Returns dict or None."""
    val, _ = _kv_get_ts("pending_alert")
    if not val:
        return None
    con = _conn()
    con.run("DELETE FROM kv_store WHERE key = 'pending_alert'")
    con.close()
    try:
        return json.loads(val)
    except Exception:
        return None

# ── Test trigger ──────────────────────────────────────────────────────────────

def push_test_trigger():
    _kv_set("test_trigger", "1")

def pop_test_trigger():
    val = _kv_get("test_trigger")
    if not val:
        return False
    con = _conn()
    con.run("DELETE FROM kv_store WHERE key = 'test_trigger'")
    con.close()
    return True

# ── Alert state (so dashboard can read what bot is doing) ─────────────────────

def set_alert_state(status, zones=""):
    _kv_set("alert_state", json.dumps({"status": status, "zones": zones}))

def get_alert_state():
    val = _kv_get("alert_state")
    if not val:
        return {"status": "IDLE", "zones": ""}
    try:
        return json.loads(val)
    except Exception:
        return {"status": "IDLE", "zones": ""}

# ── Members ───────────────────────────────────────────────────────────────────

def get_member(telegram_id):
    con = _conn()
    rows = con.run("SELECT telegram_id, name, status, zone, joined_at FROM members WHERE telegram_id = :uid", uid=telegram_id)
    con.close()
    if not rows:
        return None
    r = rows[0]
    return {"telegram_id": r[0], "name": r[1], "status": r[2], "zone": r[3], "joined_at": r[4]}

def get_all_members():
    con = _conn()
    rows = con.run("SELECT telegram_id, name, status, zone, joined_at FROM members ORDER BY joined_at DESC")
    con.close()
    return [{"telegram_id": r[0], "name": r[1], "status": r[2], "zone": r[3], "joined_at": r[4]} for r in rows]

def get_approved_members():
    con = _conn()
    rows = con.run("SELECT telegram_id, name, status, zone, joined_at FROM members WHERE status = 'approved'")
    con.close()
    return [{"telegram_id": r[0], "name": r[1], "status": r[2], "zone": r[3], "joined_at": r[4]} for r in rows]

def add_member(telegram_id, name, status="pending"):
    con = _conn()
    con.run(
        "INSERT INTO members (telegram_id, name, status, joined_at) VALUES (:uid, :name, :status, :ts) ON CONFLICT DO NOTHING",
        uid=telegram_id, name=name, status=status, ts=int(time.time())
    )
    con.close()

def update_name(telegram_id, name):
    con = _conn()
    con.run("UPDATE members SET name = :name WHERE telegram_id = :uid", name=name, uid=telegram_id)
    con.close()

def set_zone(telegram_id, zone):
    con = _conn()
    con.run("UPDATE members SET zone = :zone WHERE telegram_id = :uid", zone=zone, uid=telegram_id)
    con.close()

def set_status(telegram_id, status):
    con = _conn()
    con.run("UPDATE members SET status = :status WHERE telegram_id = :uid", status=status, uid=telegram_id)
    con.close()

def remove_member(telegram_id):
    con = _conn()
    con.run("DELETE FROM members WHERE telegram_id = :uid", uid=telegram_id)
    con.close()

# ── Alert events ──────────────────────────────────────────────────────────────

def log_alert_start():
    pass

def log_alert_end(zones="", is_test=False):
    event_id = str(uuid.uuid4())
    con = _conn()
    con.run(
        "INSERT INTO alert_events (id, started_at, ended_at, zones, is_test, response_count) VALUES (:id, :ts, :ts, :zones, :is_test, 0)",
        id=event_id, ts=int(time.time()), zones=zones, is_test=is_test
    )
    con.close()
    return event_id

def save_response(event_id, telegram_id, response):
    con = _conn()
    resp_id = str(uuid.uuid4())
    try:
        con.run(
            "INSERT INTO responses (id, event_id, telegram_id, response, responded_at) VALUES (:id, :eid, :uid, :resp, :ts) ON CONFLICT (event_id, telegram_id) DO UPDATE SET response = :resp",
            id=resp_id, eid=event_id, uid=telegram_id, resp=response, ts=int(time.time())
        )
        con.run(
            "UPDATE alert_events SET response_count = (SELECT COUNT(*) FROM responses WHERE event_id = :eid) WHERE id = :eid",
            eid=event_id
        )
    except Exception:
        pass
    con.close()

def get_responses_for_event(event_id):
    con = _conn()
    rows = con.run(
        "SELECT id, event_id, telegram_id, response, responded_at FROM responses WHERE event_id = :eid",
        eid=event_id
    )
    con.close()
    return [{"id": r[0], "event_id": r[1], "telegram_id": r[2], "response": r[3], "responded_at": r[4]} for r in rows]

def get_no_response(event_id):
    approved = get_approved_members()
    responses = {r["telegram_id"] for r in get_responses_for_event(event_id)}
    return [m for m in approved if m["telegram_id"] not in responses]

def get_latest_response(telegram_id):
    con = _conn()
    rows = con.run(
        "SELECT response FROM responses WHERE telegram_id = :uid ORDER BY responded_at DESC LIMIT 1",
        uid=telegram_id
    )
    con.close()
    if rows:
        return rows[0][0]
    return None

def get_alert_history(limit=10):
    con = _conn()
    rows = con.run(
        "SELECT id, started_at, ended_at, zones, is_test, COALESCE(response_count, 0) FROM alert_events ORDER BY ended_at DESC LIMIT :lim",
        lim=limit
    )
    con.close()
    return [{"id": r[0], "started_at": r[1], "ended_at": r[2], "zones": r[3], "is_test": r[4], "response_count": r[5]} for r in rows]
