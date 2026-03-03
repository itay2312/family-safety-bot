"""
Simple SQLite database layer.
All data is stored in family_safety.db — Railway persists this automatically.
"""
import sqlite3, time, uuid, os

DB_PATH = os.environ.get("DB_PATH", "family_safety.db")

def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def init():
    with _conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS members (
            telegram_id  INTEGER PRIMARY KEY,
            name         TEXT    NOT NULL,
            status       TEXT    NOT NULL DEFAULT 'pending',
            joined_at    INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS alert_events (
            id           TEXT    PRIMARY KEY,
            started_at   INTEGER,
            ended_at     INTEGER,
            is_test      INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS responses (
            id           TEXT    PRIMARY KEY,
            event_id     TEXT    NOT NULL,
            telegram_id  INTEGER NOT NULL,
            response     TEXT    NOT NULL,
            responded_at INTEGER NOT NULL
        );
        """)

# ── Members ──────────────────────────────

def add_member(telegram_id: int, name: str, status="pending"):
    with _conn() as c:
        c.execute(
            "INSERT OR IGNORE INTO members (telegram_id, name, status, joined_at) VALUES (?,?,?,?)",
            (telegram_id, name, status, int(time.time()))
        )

def get_member(telegram_id: int):
    with _conn() as c:
        row = c.execute("SELECT * FROM members WHERE telegram_id=?", (telegram_id,)).fetchone()
        return dict(row) if row else None

def get_all_members():
    with _conn() as c:
        rows = c.execute("SELECT * FROM members ORDER BY joined_at DESC").fetchall()
        return [dict(r) for r in rows]

def get_approved_members():
    with _conn() as c:
        rows = c.execute("SELECT * FROM members WHERE status='approved'").fetchall()
        return [dict(r) for r in rows]

def get_pending_members():
    with _conn() as c:
        rows = c.execute("SELECT * FROM members WHERE status='pending'").fetchall()
        return [dict(r) for r in rows]

def update_name(telegram_id: int, name: str):
    with _conn() as c:
        c.execute("UPDATE members SET name=? WHERE telegram_id=?", (name, telegram_id))

def set_status(telegram_id: int, status: str):
    with _conn() as c:
        c.execute("UPDATE members SET status=? WHERE telegram_id=?", (status, telegram_id))

def remove_member(telegram_id: int):
    with _conn() as c:
        c.execute("DELETE FROM members WHERE telegram_id=?", (telegram_id,))

# ── Alert Events ─────────────────────────

def log_alert_start():
    event_id = str(uuid.uuid4())
    with _conn() as c:
        c.execute(
            "INSERT INTO alert_events (id, started_at) VALUES (?,?)",
            (event_id, int(time.time()))
        )
    return event_id

def log_alert_end(is_test=False):
    event_id = str(uuid.uuid4())
    now = int(time.time())
    with _conn() as c:
        c.execute(
            "INSERT INTO alert_events (id, started_at, ended_at, is_test) VALUES (?,?,?,?)",
            (event_id, now, now, 1 if is_test else 0)
        )
    return event_id

def get_recent_events(limit=20):
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM alert_events ORDER BY ended_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

# ── Responses ────────────────────────────

def save_response(event_id: str, telegram_id: int, response: str):
    with _conn() as c:
        # Upsert — if they tap twice, update
        existing = c.execute(
            "SELECT id FROM responses WHERE event_id=? AND telegram_id=?",
            (event_id, telegram_id)
        ).fetchone()
        if existing:
            c.execute(
                "UPDATE responses SET response=?, responded_at=? WHERE id=?",
                (response, int(time.time()), existing["id"])
            )
        else:
            c.execute(
                "INSERT INTO responses (id, event_id, telegram_id, response, responded_at) VALUES (?,?,?,?,?)",
                (str(uuid.uuid4()), event_id, telegram_id, response, int(time.time()))
            )

def get_responses_for_event(event_id: str):
    with _conn() as c:
        rows = c.execute(
            "SELECT r.*, m.name FROM responses r "
            "JOIN members m ON m.telegram_id = r.telegram_id "
            "WHERE r.event_id=?", (event_id,)
        ).fetchall()
        return [dict(r) for r in rows]

def get_no_response(event_id: str):
    approved = get_approved_members()
    with _conn() as c:
        responded_ids = {
            r["telegram_id"] for r in
            c.execute("SELECT telegram_id FROM responses WHERE event_id=?", (event_id,)).fetchall()
        }
    return [m for m in approved if m["telegram_id"] not in responded_ids]

def get_latest_response(telegram_id: int):
    with _conn() as c:
        row = c.execute(
            "SELECT response FROM responses WHERE telegram_id=? ORDER BY responded_at DESC LIMIT 1",
            (telegram_id,)
        ).fetchone()
        return row["response"] if row else None
