"""
Admin web dashboard — runs on port 8080.
Protected by a simple password set via DASHBOARD_PASSWORD env var.
"""
from flask import Flask, render_template_string, request, session, redirect, jsonify
import os, time, db

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "change-this-secret-123")
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "changeme")

# ─────────────────────────────────────────
# HTML TEMPLATE
# ─────────────────────────────────────────
HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>🚨 Family Safety Dashboard</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #0f0f13; color: #e8e8f0; min-height: 100vh; }

  /* ── Live Alert Banner ── */
  #alert-banner {
    display: none;
    position: sticky; top: 0; z-index: 100;
    background: #ef4444;
    padding: 16px 32px;
    text-align: center;
    font-size: 1.1rem;
    font-weight: 700;
    letter-spacing: .03em;
    animation: pulse 1.2s infinite;
    box-shadow: 0 4px 30px rgba(239,68,68,.5);
  }
  #alert-banner.show { display: block; }
  @keyframes pulse {
    0%,100% { background: #ef4444; }
    50%      { background: #b91c1c; }
  }
  #alert-zones { font-weight: 400; font-size: 0.95rem; margin-top: 4px; opacity: .9; }

  /* ── Header ── */
  .header { background: #1a1a24; border-bottom: 1px solid #2a2a3a;
            padding: 18px 32px; display: flex; align-items: center; gap: 12px; }
  .header h1 { font-size: 1.3rem; font-weight: 700; }
  #status-badge { background: #22c55e; color: #000; font-size: 0.75rem;
                  padding: 4px 12px; border-radius: 20px; font-weight: 700;
                  transition: all .3s; }
  #status-badge.alert { background: #ef4444; color: #fff; animation: pulse 1.2s infinite; }
  #last-check { margin-left: auto; color: #555; font-size: 0.8rem; }

  /* ── Layout ── */
  .container { max-width: 1050px; margin: 32px auto; padding: 0 24px; }
  .grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 18px; margin-bottom: 26px; }
  .card { background: #1a1a24; border: 1px solid #2a2a3a; border-radius: 14px; padding: 22px; }
  .card h2 { font-size: 0.8rem; color: #888; text-transform: uppercase;
             letter-spacing: .08em; margin-bottom: 12px; }
  .stat { font-size: 2.2rem; font-weight: 800; }
  .stat small { font-size: 1rem; color: #888; font-weight: 400; }

  /* ── Alert State Card ── */
  #state-card { border-color: #2a2a3a; transition: border-color .3s, background .3s; }
  #state-card.alert-active { border-color: #ef4444; background: #2a1515; }
  #state-value { transition: color .3s; }

  /* ── Tables ── */
  table { width: 100%; border-collapse: collapse; }
  th { text-align: left; padding: 10px 14px; font-size: 0.78rem; color: #888;
       text-transform: uppercase; letter-spacing: .06em; border-bottom: 1px solid #2a2a3a; }
  td { padding: 13px 14px; border-bottom: 1px solid #1e1e2a; font-size: 0.93rem; }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: #1e1e2c; }
  .pill { display: inline-block; padding: 3px 12px; border-radius: 20px;
          font-size: 0.78rem; font-weight: 600; }
  .pill.approved { background: #14532d; color: #86efac; }
  .pill.pending  { background: #713f12; color: #fde68a; }
  .pill.rejected { background: #450a0a; color: #fca5a5; }

  /* ── Buttons ── */
  .btn { display: inline-block; padding: 7px 16px; border-radius: 8px;
         font-size: 0.83rem; font-weight: 600; cursor: pointer;
         border: none; transition: opacity .15s; }
  .btn:hover { opacity: .82; }
  .btn-green  { background: #16a34a; color: #fff; }
  .btn-red    { background: #dc2626; color: #fff; }
  .btn-orange { background: #ea580c; color: #fff; }
  form { display: inline; }

  .topbar { display: flex; justify-content: space-between; align-items: center;
            margin-bottom: 16px; }
  .section-title { font-size: 1.05rem; font-weight: 700; }
  .full { grid-column: 1 / -1; }
  .test-row { background: #1a1a10 !important; }

  /* ── Login ── */
  .login-wrap { display: flex; align-items: center; justify-content: center; min-height: 100vh; }
  .login-box  { background: #1a1a24; border: 1px solid #2a2a3a; border-radius: 16px;
                padding: 40px; width: 340px; text-align: center; }
  .login-box h1 { font-size: 1.5rem; margin-bottom: 8px; }
  .login-box p  { color: #888; font-size: 0.9rem; margin-bottom: 24px; }
  input[type=password] { width: 100%; padding: 12px 16px; background: #0f0f13;
    border: 1px solid #2a2a3a; border-radius: 8px; color: #fff;
    font-size: 1rem; margin-bottom: 14px; }
  .error { color: #f87171; font-size: 0.85rem; margin-bottom: 12px; }

  /* ── Live dot ── */
  .live-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%;
              background: #22c55e; margin-right: 6px; animation: blink 2s infinite; }
  .live-dot.red { background: #ef4444; }
  @keyframes blink { 0%,100%{opacity:1} 50%{opacity:.3} }
</style>
</head>
<body>

{% if not logged_in %}
<div class="login-wrap">
  <div class="login-box">
    <h1>🚨 Safety Bot</h1>
    <p>Admin Dashboard</p>
    {% if error %}<div class="error">{{ error }}</div>{% endif %}
    <form method="POST" action="/login">
      <input type="password" name="password" placeholder="Enter password" autofocus>
      <button class="btn btn-green" style="width:100%;padding:12px" type="submit">Login</button>
    </form>
  </div>
</div>

{% else %}

<!-- Live alert banner (shown/hidden by JS) -->
<div id="alert-banner">
  🚨 ROCKET ALERT ACTIVE IN YOUR AREA 🚨
  <div id="alert-zones"></div>
</div>

<div class="header">
  <span style="font-size:1.5rem">🚨</span>
  <h1>Family Safety Dashboard</h1>
  <span id="status-badge">✅ All Clear</span>
  <span id="last-check">Checking...</span>
  <div style="margin-left:auto; display:flex; gap:10px; align-items:center">
    <span><span class="live-dot" id="live-dot"></span><span style="font-size:.8rem;color:#555">Live</span></span>
    <a href="/logout" class="btn btn-red">Logout</a>
  </div>
</div>

<div class="container">

  <!-- Stats -->
  <div class="grid">
    <div class="card" id="state-card">
      <h2>Alert State</h2>
      <div class="stat" id="state-value">—</div>
    </div>
    <div class="card">
      <h2>Approved Members</h2>
      <div class="stat">{{ approved_count }} <small>people</small></div>
    </div>
    <div class="card">
      <h2>Pending Approval</h2>
      <div class="stat">{{ pending_count }} <small>requests</small></div>
    </div>
  </div>

  <!-- Members table -->
  <div class="topbar">
    <div class="section-title">👥 Members</div>
    <form method="POST" action="/test">
      <button class="btn btn-orange" type="submit"
        onclick="return confirm('Send test check-in to all approved members?')">
        🧪 Send Test Check-in
      </button>
    </form>
  </div>

  <div class="card full" style="margin-bottom:28px">
    <table>
      <thead>
        <tr>
          <th>Name</th>
          <th>Zone</th>
          <th>Status</th>
          <th>Joined</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody>
        {% for m in members %}
        <tr>
          <td><strong>{{ m.name }}</strong></td>
          <td style="color:#a78bfa">📍 {{ m.zone or '—' }}</td>
          <td><span class="pill {{ m.status }}">{{ m.status }}</span></td>
          <td style="color:#888">{{ m.joined_fmt }}</td>
          <td style="display:flex;gap:8px;flex-wrap:wrap">
            {% if m.status == 'pending' %}
            <form method="POST" action="/approve/{{ m.telegram_id }}">
              <button class="btn btn-green" type="submit">✅ Approve</button>
            </form>
            <form method="POST" action="/reject/{{ m.telegram_id }}">
              <button class="btn btn-red" type="submit">❌ Reject</button>
            </form>
            {% elif m.status == 'approved' %}
            <form method="POST" action="/reject/{{ m.telegram_id }}">
              <button class="btn btn-red" type="submit">Remove</button>
            </form>
            {% elif m.status == 'rejected' %}
            <form method="POST" action="/approve/{{ m.telegram_id }}">
              <button class="btn btn-green" type="submit">Re-approve</button>
            </form>
            {% endif %}
          </td>
        </tr>
        {% endfor %}
        {% if not members %}
        <tr><td colspan="5" style="color:#888;text-align:center;padding:32px">
          No members yet. Share your bot link so family can join!
        </td></tr>
        {% endif %}
      </tbody>
    </table>
  </div>

  <!-- Recent events -->
  <div class="section-title" style="margin-bottom:16px">📜 Recent Alert Events</div>
  <div class="card full">
    <table>
      <thead>
        <tr><th>Time</th><th>Type</th><th>Zones</th><th>Responded</th><th>No Response</th></tr>
      </thead>
      <tbody>
        {% for e in events %}
        <tr {% if e.is_test %}class="test-row"{% endif %}>
          <td>{{ e.time_fmt }}</td>
          <td><span class="pill {% if e.is_test %}pending{% else %}approved{% endif %}">
            {{ '🧪 Test' if e.is_test else '🚨 Real' }}
          </span></td>
          <td style="color:#a78bfa">{{ e.zones or '—' }}</td>
          <td style="color:#86efac">{{ e.ok_count }} ✅&nbsp; {{ e.help_count }} ❗</td>
          <td style="color:#fca5a5">{{ e.no_resp }}</td>
        </tr>
        {% endfor %}
        {% if not events %}
        <tr><td colspan="5" style="color:#888;text-align:center;padding:32px">
          No events yet. Use the Test button above!
        </td></tr>
        {% endif %}
      </tbody>
    </table>
  </div>

</div>

<!-- ── Live polling JS ── -->
<script>
const POLL_MS = 3000; // check every 3 seconds

async function checkAlertState() {
  try {
    const res  = await fetch('/api/state');
    const data = await res.json();

    const banner    = document.getElementById('alert-banner');
    const badge     = document.getElementById('status-badge');
    const stateVal  = document.getElementById('state-value');
    const stateCard = document.getElementById('state-card');
    const dot       = document.getElementById('live-dot');
    const lastCheck = document.getElementById('last-check');
    const zonesDiv  = document.getElementById('alert-zones');

    // Update last-checked time
    const now = new Date();
    lastCheck.textContent = 'Updated ' + now.toLocaleTimeString();
    dot.classList.remove('red');

    if (data.state === 'ALERT') {
      // Show red banner
      banner.classList.add('show');
      badge.textContent = '🚨 ALERT ACTIVE';
      badge.classList.add('alert');
      stateVal.textContent = '🚨 ACTIVE';
      stateVal.style.color = '#ef4444';
      stateCard.classList.add('alert-active');
      zonesDiv.textContent = data.zones ? '📍 ' + data.zones : '';
      document.title = '🚨 ALERT — Family Safety';
    } else {
      // All clear
      banner.classList.remove('show');
      badge.textContent = '✅ All Clear';
      badge.classList.remove('alert');
      stateVal.textContent = '✅ All Clear';
      stateVal.style.color = '#22c55e';
      stateCard.classList.remove('alert-active');
      document.title = '🚨 Family Safety Dashboard';
    }
  } catch(e) {
    // Connection issue — show red dot
    document.getElementById('live-dot').classList.add('red');
    document.getElementById('last-check').textContent = 'Connection error';
  }
}

// Run immediately then every 3 seconds
checkAlertState();
setInterval(checkAlertState, POLL_MS);
</script>

{% endif %}
</body>
</html>
"""

# ─────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────
def fmt_time(ts):
    if not ts: return "—"
    import datetime
    return datetime.datetime.fromtimestamp(ts).strftime("%d %b %Y, %H:%M")

def read_state_file():
    """Read alert state written by bot.py"""
    try:
        if os.path.exists(".alert_state"):
            parts = open(".alert_state").read().strip().split("|")
            return parts[0], parts[1] if len(parts) > 1 else ""
    except Exception:
        pass
    return "IDLE", ""

@app.route("/")
def index():
    if not session.get("admin"):
        return render_template_string(HTML, logged_in=False, error=None)

    members_raw = db.get_all_members()
    members = []
    for m in members_raw:
        m["joined_fmt"] = fmt_time(m.get("joined_at"))
        members.append(m)

    events_raw = db.get_recent_events(20)
    events = []
    for e in events_raw:
        resps    = db.get_responses_for_event(e["id"])
        approved = db.get_approved_members()
        resp_ids = {r["telegram_id"] for r in resps}
        no_resp  = [m["name"] for m in approved if m["telegram_id"] not in resp_ids]
        events.append({
            **e,
            "time_fmt":   fmt_time(e.get("ended_at") or e.get("started_at")),
            "ok_count":   sum(1 for r in resps if r["response"] == "ok"),
            "help_count": sum(1 for r in resps if r["response"] == "help"),
            "no_resp":    ", ".join(no_resp) if no_resp else "Everyone responded ✅",
            "zones":      e.get("zones", ""),
        })

    return render_template_string(HTML,
        logged_in=True,
        members=members,
        events=events,
        approved_count=sum(1 for m in members_raw if m["status"] == "approved"),
        pending_count=sum(1 for m in members_raw if m["status"] == "pending"),
    )

@app.route("/api/state")
def api_state():
    """Called every 3s by the dashboard JS to get live alert state."""
    if not session.get("admin"):
        return jsonify({"error": "unauthorized"}), 401
    state, zones = read_state_file()
    return jsonify({"state": state, "zones": zones})

@app.route("/login", methods=["POST"])
def login():
    if request.form.get("password") == DASHBOARD_PASSWORD:
        session["admin"] = True
        return redirect("/")
    return render_template_string(HTML, logged_in=False, error="Wrong password. Try again.")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/approve/<int:uid>", methods=["POST"])
def approve(uid):
    if not session.get("admin"): return redirect("/")
    db.set_status(uid, "approved")
    return redirect("/")

@app.route("/reject/<int:uid>", methods=["POST"])
def reject(uid):
    if not session.get("admin"): return redirect("/")
    db.set_status(uid, "rejected")
    return redirect("/")

@app.route("/test", methods=["POST"])
def test_alert():
    if not session.get("admin"): return redirect("/")
    open(".trigger_test", "w").write("1")
    return redirect("/")

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    db.init()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
