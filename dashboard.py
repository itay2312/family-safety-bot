from flask import Flask, render_template_string, request, session, redirect, jsonify
import os, time, db

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "change-this-secret-123")
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "changeme")

HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>🚨 Family Safety</title>
<style>
:root {
  --bg:       #08090d;
  --surface:  #111318;
  --border:   #1e2028;
  --border2:  #2a2d3a;
  --text:     #e8eaf0;
  --muted:    #5a5f72;
  --green:    #22c55e;
  --green-bg: #0d2318;
  --red:      #ef4444;
  --red-bg:   #2a0f0f;
  --yellow:   #f59e0b;
  --yellow-bg:#2a1f08;
  --blue:     #3b82f6;
  --purple:   #a78bfa;
  --radius:   12px;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: var(--bg); color: var(--text); min-height: 100vh; font-size: 14px; }

/* ── Alert Banner ── */
#alert-banner {
  display: none; position: sticky; top: 0; z-index: 200;
  background: var(--red); color: #fff;
  padding: 14px 24px; text-align: center;
  font-weight: 700; font-size: 1rem; letter-spacing: .04em;
  animation: bgpulse 1.2s infinite;
  box-shadow: 0 4px 40px rgba(239,68,68,.4);
}
#alert-banner.show { display: block; }
#alert-zones { font-weight: 400; font-size: .85rem; margin-top: 3px; opacity: .9; }
@keyframes bgpulse { 0%,100%{background:#ef4444} 50%{background:#b91c1c} }

/* ── Header ── */
.header {
  background: var(--surface); border-bottom: 1px solid var(--border);
  padding: 0 32px; height: 60px;
  display: flex; align-items: center; gap: 14px;
  position: sticky; top: 0; z-index: 100;
}
.header-logo { font-size: 1.3rem; }
.header-title { font-size: 1rem; font-weight: 700; color: var(--text); }
.header-subtitle { font-size: .75rem; color: var(--muted); margin-top: 1px; }
.spacer { flex: 1; }
.live-indicator { display: flex; align-items: center; gap: 6px;
                  font-size: .75rem; color: var(--muted); }
.dot { width: 7px; height: 7px; border-radius: 50%; background: var(--green);
       animation: blink 2s infinite; }
.dot.red { background: var(--red); }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:.25} }
.badge { padding: 4px 12px; border-radius: 20px; font-size: .72rem;
         font-weight: 700; letter-spacing: .04em; }
.badge-green { background: var(--green-bg); color: var(--green); border: 1px solid #16a34a44; }
.badge-red   { background: var(--red-bg);   color: var(--red);   border: 1px solid #ef444444;
               animation: bgpulse 1.2s infinite; }
.btn { padding: 7px 16px; border-radius: 8px; font-size: .8rem; font-weight: 600;
       cursor: pointer; border: none; transition: opacity .15s; text-decoration: none;
       display: inline-block; }
.btn:hover { opacity: .8; }
.btn-red    { background: #dc2626; color: #fff; }
.btn-orange { background: #ea580c; color: #fff; }
.btn-green  { background: #16a34a; color: #fff; }
.btn-ghost  { background: var(--border2); color: var(--text); }

/* ── Layout ── */
.page { max-width: 1100px; margin: 0 auto; padding: 28px 24px; }
.section-label { font-size: .7rem; font-weight: 700; color: var(--muted);
                 text-transform: uppercase; letter-spacing: .1em; margin-bottom: 12px; }

/* ── Stat Cards ── */
.stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 28px; }
.stat-card { background: var(--surface); border: 1px solid var(--border);
             border-radius: var(--radius); padding: 18px 20px; }
.stat-card .label { font-size: .72rem; color: var(--muted); text-transform: uppercase;
                    letter-spacing: .07em; margin-bottom: 10px; }
.stat-card .value { font-size: 2rem; font-weight: 800; line-height: 1; }
.stat-card .sub   { font-size: .75rem; color: var(--muted); margin-top: 4px; }
.stat-card.alert-active { border-color: var(--red); background: var(--red-bg); }

/* ── Two column layout ── */
.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 24px; }
.full-col { margin-bottom: 24px; }

/* ── Cards ── */
.card { background: var(--surface); border: 1px solid var(--border);
        border-radius: var(--radius); overflow: hidden; }
.card-header { padding: 16px 20px; border-bottom: 1px solid var(--border);
               display: flex; align-items: center; justify-content: space-between; }
.card-title { font-size: .85rem; font-weight: 700; }
.card-body { padding: 0; }

/* ── Tables ── */
table { width: 100%; border-collapse: collapse; }
th { padding: 10px 16px; text-align: left; font-size: .7rem; color: var(--muted);
     text-transform: uppercase; letter-spacing: .07em;
     border-bottom: 1px solid var(--border); background: var(--surface); }
td { padding: 12px 16px; border-bottom: 1px solid var(--border); font-size: .85rem;
     vertical-align: middle; }
tr:last-child td { border-bottom: none; }
tbody tr:hover td { background: #ffffff05; }

/* ── Pills ── */
.pill { display: inline-block; padding: 3px 10px; border-radius: 20px;
        font-size: .72rem; font-weight: 600; }
.pill-green  { background: var(--green-bg); color: var(--green); }
.pill-yellow { background: var(--yellow-bg); color: var(--yellow); }
.pill-red    { background: var(--red-bg); color: var(--red); }
.pill-purple { background: #2d1f4a; color: var(--purple); }
.pill-blue   { background: #0f1f3a; color: var(--blue); }

/* ── Action buttons in table ── */
.action-group { display: flex; gap: 6px; flex-wrap: wrap; }
form { display: inline; }

/* ── Alert log entries ── */
.log-entry { padding: 14px 20px; border-bottom: 1px solid var(--border);
             display: grid; grid-template-columns: 140px 80px 1fr auto;
             gap: 16px; align-items: center; font-size: .83rem; }
.log-entry:last-child { border-bottom: none; }
.log-entry:hover { background: #ffffff04; }
.log-time { color: var(--muted); font-size: .78rem; }
.log-zones { color: var(--purple); font-size: .8rem; }
.log-responses { display: flex; gap: 8px; align-items: center; }
.resp-chip { display: flex; align-items: center; gap: 4px; padding: 3px 8px;
             border-radius: 6px; font-size: .75rem; font-weight: 600; }
.resp-ok   { background: var(--green-bg); color: var(--green); }
.resp-help { background: var(--red-bg);   color: var(--red); }
.resp-wait { background: var(--border2);  color: var(--muted); }
.response-rate { font-size: .75rem; color: var(--muted); text-align: right; }

/* ── Empty state ── */
.empty { padding: 40px; text-align: center; color: var(--muted); font-size: .85rem; }
.empty-icon { font-size: 2rem; margin-bottom: 8px; }

/* ── Login ── */
.login-wrap { display: flex; align-items: center; justify-content: center;
              min-height: 100vh; }
.login-box  { background: var(--surface); border: 1px solid var(--border);
              border-radius: 16px; padding: 40px; width: 360px; }
.login-box h1 { font-size: 1.6rem; margin-bottom: 6px; }
.login-box p  { color: var(--muted); font-size: .85rem; margin-bottom: 28px; }
input[type=password] { width: 100%; padding: 12px 16px; background: var(--bg);
  border: 1px solid var(--border2); border-radius: 8px; color: var(--text);
  font-size: .95rem; margin-bottom: 12px; outline: none; }
input[type=password]:focus { border-color: var(--blue); }
.login-error { color: var(--red); font-size: .82rem; margin-bottom: 10px; }

/* ── Topbar ── */
.topbar { display: flex; align-items: center; justify-content: space-between;
          margin-bottom: 14px; }
</style>
</head>
<body>

{% if not logged_in %}
<div class="login-wrap">
  <div class="login-box">
    <h1>🚨 Family Safety</h1>
    <p>Admin dashboard — sign in to continue</p>
    {% if error %}<div class="login-error">{{ error }}</div>{% endif %}
    <form method="POST" action="/login">
      <input type="password" name="password" placeholder="Password" autofocus>
      <button class="btn btn-green" style="width:100%;padding:12px;font-size:.95rem" type="submit">
        Sign in
      </button>
    </form>
  </div>
</div>

{% else %}

<!-- Alert banner -->
<div id="alert-banner">
  🚨 ROCKET ALERT ACTIVE IN YOUR AREA 🚨
  <div id="alert-zones"></div>
</div>

<!-- Header -->
<div class="header">
  <div class="header-logo">🚨</div>
  <div>
    <div class="header-title">Family Safety</div>
    <div class="header-subtitle">Admin Dashboard</div>
  </div>
  <div class="spacer"></div>
  <div class="live-indicator">
    <div class="dot" id="live-dot"></div>
    <span id="last-updated">Connecting...</span>
  </div>
  <span id="status-badge" class="badge badge-green">✅ All Clear</span>
  <a href="/logout" class="btn btn-ghost" style="margin-left:8px">Sign out</a>
</div>

<div class="page">

  <!-- Stat cards -->
  <div class="stats">
    <div class="stat-card" id="state-card">
      <div class="label">Alert State</div>
      <div class="value" id="state-value" style="color:var(--green)">—</div>
      <div class="sub" id="state-sub">Loading...</div>
    </div>
    <div class="stat-card">
      <div class="label">Approved Members</div>
      <div class="value" style="color:var(--blue)">{{ approved_count }}</div>
      <div class="sub">in family group</div>
    </div>
    <div class="stat-card">
      <div class="label">Observers</div>
      <div class="value" style="color:var(--purple)">{{ observer_count }}</div>
      <div class="sub">abroad / watching</div>
    </div>
    <div class="stat-card">
      <div class="label">Pending Approval</div>
      <div class="value" style="color:var(--yellow)">{{ pending_count }}</div>
      <div class="sub">awaiting review</div>
    </div>
  </div>

  <!-- Members + Recent event side by side -->
  <div class="two-col">

    <!-- Members -->
    <div class="card">
      <div class="card-header">
        <div class="card-title">👥 Members</div>
        <form method="POST" action="/test">
          <button class="btn btn-orange" type="submit"
            onclick="return confirm('Send test check-in to all approved members?')">
            🧪 Test Alert
          </button>
        </form>
      </div>
      <div class="card-body">
        {% if members %}
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Zone</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {% for m in members %}
            <tr>
              <td><strong>{{ m.name }}</strong></td>
              <td>
                {% if m.zone == '🌍 Abroad' %}
                  <span class="pill pill-purple">🌍 Observer</span>
                {% elif m.zone %}
                  <span style="color:var(--purple);font-size:.8rem">📍 {{ m.zone }}</span>
                {% else %}
                  <span style="color:var(--muted)">—</span>
                {% endif %}
              </td>
              <td>
                {% if m.status == 'approved' %}
                  <span class="pill pill-green">Approved</span>
                {% elif m.status == 'pending' %}
                  <span class="pill pill-yellow">Pending</span>
                {% else %}
                  <span class="pill pill-red">Rejected</span>
                {% endif %}
              </td>
              <td>
                <div class="action-group">
                  {% if m.status == 'pending' %}
                  <form method="POST" action="/approve/{{ m.telegram_id }}">
                    <button class="btn btn-green" type="submit">✅</button>
                  </form>
                  <form method="POST" action="/reject/{{ m.telegram_id }}">
                    <button class="btn btn-red" type="submit">❌</button>
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
                </div>
              </td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
        {% else %}
        <div class="empty">
          <div class="empty-icon">👥</div>
          No members yet. Share your bot link!
        </div>
        {% endif %}
      </div>
    </div>

    <!-- Last event status board -->
    <div class="card">
      <div class="card-header">
        <div class="card-title">📋 Last Check-in Status</div>
        {% if last_event %}
        <span style="font-size:.75rem;color:var(--muted)">{{ last_event.time_fmt }}</span>
        {% endif %}
      </div>
      <div class="card-body">
        {% if last_event and last_event.responses %}
        <table>
          <thead>
            <tr><th>Name</th><th>Zone</th><th>Response</th></tr>
          </thead>
          <tbody>
            {% for r in last_event.responses %}
            <tr>
              <td><strong>{{ r.name }}</strong></td>
              <td style="color:var(--purple);font-size:.8rem">{{ r.zone or '—' }}</td>
              <td>
                {% if r.response == 'ok' %}
                  <span class="pill pill-green">✅ Safe</span>
                {% elif r.response == 'help' %}
                  <span class="pill pill-red">🆘 Help</span>
                {% else %}
                  <span class="pill" style="background:var(--border2);color:var(--muted)">⏳ Waiting</span>
                {% endif %}
              </td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
        {% else %}
        <div class="empty">
          <div class="empty-icon">📋</div>
          No check-ins yet. Run a test!
        </div>
        {% endif %}
      </div>
    </div>

  </div>

  <!-- Alert History Log -->
  <div class="full-col">
    <div class="topbar">
      <div class="section-label">📜 Alert History</div>
    </div>
    <div class="card">
      <div class="card-body">
        {% if events %}
        {% for e in events %}
        <div class="log-entry">
          <div>
            <div style="font-weight:600">{{ e.time_fmt }}</div>
            <div class="log-time">{{ e.date_fmt }}</div>
          </div>
          <div>
            {% if e.is_test %}
              <span class="pill pill-yellow">🧪 Test</span>
            {% else %}
              <span class="pill pill-red">🚨 Real</span>
            {% endif %}
          </div>
          <div>
            <div class="log-zones">📍 {{ e.zones or 'Unknown zones' }}</div>
            <div class="log-responses" style="margin-top:6px">
              <span class="resp-chip resp-ok">✅ {{ e.ok_count }} safe</span>
              {% if e.help_count > 0 %}
              <span class="resp-chip resp-help">🆘 {{ e.help_count }} help</span>
              {% endif %}
              {% if e.waiting_count > 0 %}
              <span class="resp-chip resp-wait">⏳ {{ e.waiting_count }} waiting</span>
              {% endif %}
            </div>
          </div>
          <div class="response-rate">
            {% if e.total > 0 %}
            <div style="font-size:1.1rem;font-weight:800;color:{% if e.rate == 100 %}var(--green){% elif e.rate >= 50 %}var(--yellow){% else %}var(--red){% endif %}">
              {{ e.rate }}%
            </div>
            <div style="color:var(--muted);font-size:.72rem">responded</div>
            {% endif %}
          </div>
        </div>
        {% endfor %}
        {% else %}
        <div class="empty">
          <div class="empty-icon">📜</div>
          No alert events yet. Use the Test button above!
        </div>
        {% endif %}
      </div>
    </div>
  </div>

</div>

<!-- Live polling JS -->
<script>
async function poll() {
  try {
    const res  = await fetch('/api/state');
    const data = await res.json();
    const isAlert = data.state === 'ALERT';

    document.getElementById('alert-banner').className = isAlert ? 'show' : '';
    document.getElementById('alert-zones').textContent = data.zones ? '📍 ' + data.zones : '';

    const badge = document.getElementById('status-badge');
    badge.textContent  = isAlert ? '🚨 ALERT' : '✅ All Clear';
    badge.className    = 'badge ' + (isAlert ? 'badge-red' : 'badge-green');

    const card = document.getElementById('state-card');
    card.className = 'stat-card' + (isAlert ? ' alert-active' : '');

    const val = document.getElementById('state-value');
    val.textContent = isAlert ? '🚨 ACTIVE' : '✅ Clear';
    val.style.color = isAlert ? 'var(--red)' : 'var(--green)';

    document.getElementById('state-sub').textContent = isAlert
      ? (data.zones || 'Alert in progress')
      : 'No active alerts';

    document.title = isAlert ? '🚨 ALERT — Family Safety' : '🚨 Family Safety';

    const dot = document.getElementById('live-dot');
    dot.className = 'dot' + (isAlert ? ' red' : '');

    const now = new Date();
    document.getElementById('last-updated').textContent =
      'Updated ' + now.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'});

  } catch(e) {
    document.getElementById('live-dot').className = 'dot red';
    document.getElementById('last-updated').textContent = 'Connection error';
  }
}

poll();
setInterval(poll, 3000);
</script>

{% endif %}
</body>
</html>
"""

# ── Helpers ──────────────────────────────

def fmt_time(ts):
    if not ts: return "—"
    import datetime
    dt = datetime.datetime.fromtimestamp(ts)
    return dt.strftime("%H:%M:%S"), dt.strftime("%d %b %Y")

def read_state():
    try:
        if os.path.exists(".alert_state"):
            parts = open(".alert_state").read().strip().split("|")
            return parts[0], parts[1] if len(parts) > 1 else ""
    except Exception:
        pass
    return "IDLE", ""

# ── Routes ───────────────────────────────

@app.route("/")
def index():
    if not session.get("admin"):
        return render_template_string(HTML, logged_in=False, error=None)

    members_raw = db.get_all_members()
    members = []
    for m in members_raw:
        members.append(m)

    # Build events with full response detail
    events_raw = db.get_recent_events(30)
    events = []
    approved = db.get_approved_members()
    non_observer_approved = [m for m in approved if m.get("zone") != "🌍 Abroad"]

    for e in events_raw:
        resps    = db.get_responses_for_event(e["id"])
        resp_map = {r["telegram_id"]: r["response"] for r in resps}
        ok_count   = sum(1 for r in resps if r["response"] == "ok")
        help_count = sum(1 for r in resps if r["response"] == "help")
        total      = len(non_observer_approved)
        responded  = ok_count + help_count
        waiting    = max(0, total - responded)
        rate       = int(responded / total * 100) if total > 0 else 0
        t_fmt, d_fmt = fmt_time(e.get("ended_at") or e.get("started_at"))
        events.append({
            **e,
            "time_fmt":     t_fmt,
            "date_fmt":     d_fmt,
            "ok_count":     ok_count,
            "help_count":   help_count,
            "waiting_count":waiting,
            "total":        total,
            "rate":         rate,
        })

    # Last event for status board
    last_event = None
    if events:
        e = events[0]
        resps = db.get_responses_for_event(e["id"])
        resp_map = {r["telegram_id"]: r["response"] for r in resps}
        board = []
        for m in non_observer_approved:
            board.append({
                "name":     m["name"],
                "zone":     m.get("zone") or "",
                "response": resp_map.get(m["telegram_id"])
            })
        last_event = {**e, "responses": board}

    return render_template_string(HTML,
        logged_in=True,
        members=members,
        events=events,
        last_event=last_event,
        approved_count=sum(1 for m in members_raw if m["status"] == "approved" and m.get("zone") != "🌍 Abroad"),
        observer_count=sum(1 for m in members_raw if m["status"] == "approved" and m.get("zone") == "🌍 Abroad"),
        pending_count=sum(1 for m in members_raw if m["status"] == "pending"),
    )

@app.route("/api/state")
def api_state():
    if not session.get("admin"):
        return jsonify({"error": "unauthorized"}), 401
    state, zones = read_state()
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
    from flask import jsonify
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    db.init()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
