"""
Database layer using PostgreSQL via pg8000.
Pure Python driver — no system libraries needed.
"""
import os, time, uuid, ssl
import pg8000.native
from urllib.parse import urlparse

DATABASE_URL = os.environ["DATABASE_URL"]

def _conn():
    url = urlparse(DATABASE_URL)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return pg8000.native.Connection(
        user=url.username,
        password=url.password,
        host=url.hostname,
        port=url.port or 5432,
        database=url.path.lstrip("/"),
        ssl_context=ctx
    )

def _row_to_dict(columns, row):
    return dict(zip(columns, row))

def _rows_to_dicts(columns, rows):
    return [_row_to_dict(columns, r) for r in rows]

def init():
    conn = _conn()
    conn.run("""
        CREATE TABLE IF NOT EXISTS members (
            telegram_id  BIGINT PRIMARY KEY,
            name         TEXT   NOT NULL,
            status       TEXT   NOT NULL DEFAULT 'pending',
            zone         TEXT,
            joined_at    BIGINT NOT NULL
        )
    """)
    conn.run("""
        CREATE TABLE IF NOT EXISTS alert_events (
            id           TEXT   PRIMARY KEY,
            started_at   BIGINT,
            ended_at     BIGINT,
            zones        TEXT,
            is_test      BOOLEAN DEFAULT FALSE
        )
    """)
    conn.run("""
        CREATE TABLE IF NOT EXISTS responses (
            id           TEXT   PRIMARY KEY,
            event_id     TEXT   NOT NULL,
            telegram_id  BIGINT NOT NULL,
            response     TEXT   NOT NULL,
            responded_at BIGINT NOT NULL,
            UNIQUE(event_id, telegram_id)
        )
    """)
    conn.close()

# ── Members ──────────────────────────────

def add_member(telegram_id: int, name: str, status="pending"):
    conn = _conn()
    try:
        conn.run(
            "INSERT INTO members (telegram_id, name, status, joined_at) "
            "VALUES (:tid, :name, :status, :joined) "
            "ON CONFLICT (telegram_id) DO NOTHING",
            tid=telegram_id, name=name, status=status, joined=int(time.time())
        )
    finally:
        conn.close()

def get_member(telegram_id: int):
    conn = _conn()
    try:
        rows = conn.run(
            "SELECT telegram_id, name, status, zone, joined_at "
            "FROM members WHERE telegram_id=:tid",
            tid=telegram_id
        )
        if not rows:
            return None
        cols = ["telegram_id","name","status","zone","joined_at"]
        return _row_to_dict(cols, rows[0])
    finally:
        conn.close()

def get_all_members():
    conn = _conn()
    try:
        rows = conn.run(
            "SELECT telegram_id, name, status, zone, joined_at "
            "FROM members ORDER BY joined_at DESC"
        )
        cols = ["telegram_id","name","status","zone","joined_at"]
        return _rows_to_dicts(cols, rows)
    finally:
        conn.close()

def get_approved_members():
    conn = _conn()
    try:
        rows = conn.run(
            "SELECT telegram_id, name, status, zone, joined_at "
            "FROM members WHERE status='approved'"
        )
        cols = ["telegram_id","name","status","zone","joined_at"]
        return _rows_to_dicts(cols, rows)
    finally:
        conn.close()

def get_pending_members():
    conn = _conn()
    try:
        rows = conn.run(
            "SELECT telegram_id, name, status, zone, joined_at "
            "FROM members WHERE status='pending'"
        )
        cols = ["telegram_id","name","status","zone","joined_at"]
        return _rows_to_dicts(cols, rows)
    finally:
        conn.close()

def update_name(telegram_id: int, name: str):
    conn = _conn()
    try:
        conn.run("UPDATE members SET name=:name WHERE telegram_id=:tid",
                 name=name, tid=telegram_id)
    finally:
        conn.close()

def set_status(telegram_id: int, status: str):
    conn = _conn()
    try:
        conn.run("UPDATE members SET status=:status WHERE telegram_id=:tid",
                 status=status, tid=telegram_id)
    finally:
        conn.close()

def set_zone(telegram_id: int, zone: str):
    conn = _conn()
    try:
        conn.run("UPDATE members SET zone=:zone WHERE telegram_id=:tid",
                 zone=zone, tid=telegram_id)
    finally:
        conn.close()

def remove_member(telegram_id: int):
    conn = _conn()
    try:
        conn.run("DELETE FROM members WHERE telegram_id=:tid", tid=telegram_id)
    finally:
        conn.close()

# ── Alert Events ─────────────────────────

def log_alert_start():
    event_id = str(uuid.uuid4())
    conn = _conn()
    try:
        conn.run(
            "INSERT INTO alert_events (id, started_at) VALUES (:id, :ts)",
            id=event_id, ts=int(time.time())
        )
    finally:
        conn.close()
    return event_id

def log_alert_end(is_test=False, zones=""):
    event_id = str(uuid.uuid4())
    now = int(time.time())
    conn = _conn()
    try:
        conn.run(
            "INSERT INTO alert_events (id, started_at, ended_at, zones, is_test) "
            "VALUES (:id, :ts, :ts, :zones, :test)",
            id=event_id, ts=now, zones=zones, test=is_test
        )
    finally:
        conn.close()
    return event_id

def get_recent_events(limit=20):
    conn = _conn()
    try:
        rows = conn.run(
            "SELECT id, started_at, ended_at, zones, is_test "
            "FROM alert_events ORDER BY ended_at DESC NULLS LAST LIMIT :lim",
            lim=limit
        )
        cols = ["id","started_at","ended_at","zones","is_test"]
        return _rows_to_dicts(cols, rows)
    finally:
        conn.close()

# ── Responses ────────────────────────────

def save_response(event_id: str, telegram_id: int, response: str):
    conn = _conn()
    try:
        existing = conn.run(
            "SELECT id FROM responses WHERE event_id=:eid AND telegram_id=:tid",
            eid=event_id, tid=telegram_id
        )
        if existing:
            conn.run(
                "UPDATE responses SET response=:resp, responded_at=:ts "
                "WHERE event_id=:eid AND telegram_id=:tid",
                resp=response, ts=int(time.time()), eid=event_id, tid=telegram_id
            )
        else:
            conn.run(
                "INSERT INTO responses (id, event_id, telegram_id, response, responded_at) "
                "VALUES (:id, :eid, :tid, :resp, :ts)",
                id=str(uuid.uuid4()), eid=event_id, tid=telegram_id,
                resp=response, ts=int(time.time())
            )
    finally:
        conn.close()

def get_responses_for_event(event_id: str):
    conn = _conn()
    try:
        rows = conn.run(
            "SELECT r.id, r.event_id, r.telegram_id, r.response, r.responded_at, m.name "
            "FROM responses r JOIN members m ON m.telegram_id = r.telegram_id "
            "WHERE r.event_id=:eid",
            eid=event_id
        )
        cols = ["id","event_id","telegram_id","response","responded_at","name"]
        return _rows_to_dicts(cols, rows)
    finally:
        conn.close()

def get_no_response(event_id: str):
    approved = get_approved_members()
    conn = _conn()
    try:
        rows = conn.run(
            "SELECT telegram_id FROM responses WHERE event_id=:eid",
            eid=event_id
        )
        responded_ids = {r[0] for r in rows}
    finally:
        conn.close()
    return [m for m in approved if m["telegram_id"] not in responded_ids]

def get_latest_response(telegram_id: int):
    conn = _conn()
    try:
        rows = conn.run(
            "SELECT response FROM responses WHERE telegram_id=:tid "
            "ORDER BY responded_at DESC LIMIT 1",
            tid=telegram_id
        )
        return rows[0][0] if rows else None
    finally:
        conn.close()
