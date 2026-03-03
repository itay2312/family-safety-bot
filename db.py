"""
Database layer using PostgreSQL (Supabase).
Data persists across all Railway redeploys.
"""
import os, time, uuid
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.environ["DATABASE_URL"]

def _conn():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return conn

def init():
    """Create tables if they don't exist. Safe to run on every startup."""
    with _conn() as conn:
        with conn.cursor() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS members (
                    telegram_id  BIGINT PRIMARY KEY,
                    name         TEXT   NOT NULL,
                    status       TEXT   NOT NULL DEFAULT 'pending',
                    zone         TEXT,
                    joined_at    BIGINT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS alert_events (
                    id           TEXT   PRIMARY KEY,
                    started_at   BIGINT,
                    ended_at     BIGINT,
                    zones        TEXT,
                    is_test      BOOLEAN DEFAULT FALSE
                );

                CREATE TABLE IF NOT EXISTS responses (
                    id           TEXT   PRIMARY KEY,
                    event_id     TEXT   NOT NULL,
                    telegram_id  BIGINT NOT NULL,
                    response     TEXT   NOT NULL,
                    responded_at BIGINT NOT NULL,
                    UNIQUE(event_id, telegram_id)
                );
            """)
        conn.commit()

# ── Members ──────────────────────────────

def add_member(telegram_id: int, name: str, status="pending"):
    with _conn() as conn:
        with conn.cursor() as c:
            c.execute("""
                INSERT INTO members (telegram_id, name, status, joined_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (telegram_id) DO NOTHING
            """, (telegram_id, name, status, int(time.time())))
        conn.commit()

def get_member(telegram_id: int):
    with _conn() as conn:
        with conn.cursor() as c:
            c.execute("SELECT * FROM members WHERE telegram_id=%s", (telegram_id,))
            row = c.fetchone()
            return dict(row) if row else None

def get_all_members():
    with _conn() as conn:
        with conn.cursor() as c:
            c.execute("SELECT * FROM members ORDER BY joined_at DESC")
            return [dict(r) for r in c.fetchall()]

def get_approved_members():
    with _conn() as conn:
        with conn.cursor() as c:
            c.execute("SELECT * FROM members WHERE status='approved'")
            return [dict(r) for r in c.fetchall()]

def get_pending_members():
    with _conn() as conn:
        with conn.cursor() as c:
            c.execute("SELECT * FROM members WHERE status='pending'")
            return [dict(r) for r in c.fetchall()]

def update_name(telegram_id: int, name: str):
    with _conn() as conn:
        with conn.cursor() as c:
            c.execute("UPDATE members SET name=%s WHERE telegram_id=%s", (name, telegram_id))
        conn.commit()

def set_status(telegram_id: int, status: str):
    with _conn() as conn:
        with conn.cursor() as c:
            c.execute("UPDATE members SET status=%s WHERE telegram_id=%s", (status, telegram_id))
        conn.commit()

def set_zone(telegram_id: int, zone: str):
    with _conn() as conn:
        with conn.cursor() as c:
            c.execute("UPDATE members SET zone=%s WHERE telegram_id=%s", (zone, telegram_id))
        conn.commit()

def remove_member(telegram_id: int):
    with _conn() as conn:
        with conn.cursor() as c:
            c.execute("DELETE FROM members WHERE telegram_id=%s", (telegram_id,))
        conn.commit()

# ── Alert Events ─────────────────────────

def log_alert_start():
    event_id = str(uuid.uuid4())
    with _conn() as conn:
        with conn.cursor() as c:
            c.execute(
                "INSERT INTO alert_events (id, started_at) VALUES (%s, %s)",
                (event_id, int(time.time()))
            )
        conn.commit()
    return event_id

def log_alert_end(is_test=False, zones=""):
    event_id = str(uuid.uuid4())
    now = int(time.time())
    with _conn() as conn:
        with conn.cursor() as c:
            c.execute(
                "INSERT INTO alert_events (id, started_at, ended_at, zones, is_test) VALUES (%s,%s,%s,%s,%s)",
                (event_id, now, now, zones, is_test)
            )
        conn.commit()
    return event_id

def get_recent_events(limit=20):
    with _conn() as conn:
        with conn.cursor() as c:
            c.execute(
                "SELECT * FROM alert_events ORDER BY ended_at DESC NULLS LAST LIMIT %s",
                (limit,)
            )
            return [dict(r) for r in c.fetchall()]

# ── Responses ────────────────────────────

def save_response(event_id: str, telegram_id: int, response: str):
    with _conn() as conn:
        with conn.cursor() as c:
            c.execute("""
                INSERT INTO responses (id, event_id, telegram_id, response, responded_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (event_id, telegram_id)
                DO UPDATE SET response=%s, responded_at=%s
            """, (
                str(uuid.uuid4()), event_id, telegram_id, response, int(time.time()),
                response, int(time.time())
            ))
        conn.commit()

def get_responses_for_event(event_id: str):
    with _conn() as conn:
        with conn.cursor() as c:
            c.execute("""
                SELECT r.*, m.name FROM responses r
                JOIN members m ON m.telegram_id = r.telegram_id
                WHERE r.event_id=%s
            """, (event_id,))
            return [dict(r) for r in c.fetchall()]

def get_no_response(event_id: str):
    approved = get_approved_members()
    with _conn() as conn:
        with conn.cursor() as c:
            c.execute(
                "SELECT telegram_id FROM responses WHERE event_id=%s",
                (event_id,)
            )
            responded_ids = {r["telegram_id"] for r in c.fetchall()}
    return [m for m in approved if m["telegram_id"] not in responded_ids]

def get_latest_response(telegram_id: int):
    with _conn() as conn:
        with conn.cursor() as c:
            c.execute(
                "SELECT response FROM responses WHERE telegram_id=%s ORDER BY responded_at DESC LIMIT 1",
                (telegram_id,)
            )
            row = c.fetchone()
            return row["response"] if row else None
