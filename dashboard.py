"""
Admin web dashboard — runs on port 8080.
Protected by a simple password set via DASHBOARD_PASSWORD env var.
Access it at your Railway public URL.
"""
from flask import Flask, render_template_string, request, session, redirect, url_for, jsonify
import os, time, db

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "change-this-secret-123")
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "changeme")

# ─────────────────────────────────────────
# HTML TEMPLATE (single-file, no extra files needed)
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
  .header { background: #1a1a24; border-bottom: 1px solid #2a2a3a;
            padding: 18px 32px; display: flex; align-items: center; gap: 12px; }
  .header h1 { font-size: 1.3rem; font-weight: 700; }
  .badge { background: #22c55e; color: #000; font-size: 0.7rem;
           padding: 3px 10px; border-radius: 20px; font-weight: 700; }
  .badge.alert { background: #ef4444; color: #fff; }
  .container { max-width: 1000px; margin: 32px auto; padding: 0 24px; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 28px; }
  .card { background: #1a1a24; border: 1px solid #2a2a3a; border-radius: 14px; padding: 22px; }
  .card h2 { font-size: 0.85rem; color: #888; text-transform: uppercase;
             letter-spacing: .08em; margin-bottom: 14px; }
  .stat { font-size: 2.4rem; font-weight: 800; color: #fff; }
  .stat small { font-size: 1rem; color: #888; font-weight: 400; }
  table { width: 100%; border-collapse: collapse; }
  th { text-align: left; padding: 10px 14px; font-size: 0.8rem;
       color: #888; text-transform: uppercase; letter-spacing: .06em;
       border-bottom: 1px solid #2a2a3a; }
  td { padding: 13px 14px; border-bottom: 1px solid #1e1e2a; font-size: 0.95rem; }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: #1e1e2c; }
  .pill { display: inline-block; padding: 3px 12px; border-radius: 20px;
          font-size: 0.78rem; font-weight: 600; }
  .pill.approved { background: #14532d; color: #86efac; }
  .pill.pending  { background: #713f12; color: #fde68a; }
  .pill.rejected { background: #450a0a; color: #fca5a5; }
  .btn { display: inline-block; padding: 8px 18px; border-radius: 8px;
         font-size: 0.85rem; font-weight: 600; cursor: pointer;
         border: none; transition: opacity .15s; }
  .btn:hover { opacity: 0.85; }
  .btn-green  { background: #16a34a; color: #fff; }
  .btn-red    { background: #dc2626; color: #fff; }
  .btn-blue   { background: #2563eb; color: #fff; }
  .btn-orange { background: #ea580c; color: #fff; }
  form { display: inline; }
  .section-title { font-size: 1.1rem; font-weight: 700; margin-bottom: 16px; }
  .full { grid-column: 1 / -1; }
  .alert-row { background: #2a1515 !important; }
  .login-wrap { display: flex; align-items: center; justify-content: center;
                min-height: 100vh; }
  .login-box { background: #1a1a24; border: 1px solid #2a2a3a; border-radius: 16px;
               padding: 40px; width: 340px; text-align: center; }
  .login-box h1 { font-size: 1.5rem; margin-bottom: 8px; }
  .login-box p  { color: #888; font-size: 0.9rem; margin-bottom: 24px; }
  input[type=password] { width: 100%; padding: 12px 16px; background: #0f0f13;
    border: 1px solid #2a2a3a; border-radius: 8px; color: #fff;
    font-size: 1rem; margin-bottom: 14px; }
  .error { color: #f87171; font-size: 0.85rem; margin-bottom: 12px; }
  .topbar { display: flex; justify-content: space-between; align-items: center;
            margin-bottom: 24px; }
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
      <button class="btn btn-blue" style="width:100%;padding:12px" type="submit">Login</button>
    </form>
  </div>
</div>

{% else %}
<div class="header">
  <span style="font-size:1.5rem">🚨</span>
  <h1>Family Safety Dashboard</h1>
  <span class="badge {% if alert_state == 'ALERT' %}alert{% endif %}">
    {{ '🚨 ALERT ACTIVE' if alert_state == 'ALERT' else '✅ All Clear' }}
  </span>
  <div style="margin-left:auto">
    <a href="/logout" class="btn btn-red">Logout</a>
  </div>
</div>

<div class="container">

  <!-- Stats row -->
  <div class="grid">
    <div class="card">
      <h2>Approved Members</h2>
      <div class="stat">{{ approved_count }} <small>people</small></div>
    </div>
    <div class="card">
      <h2>Pending Approval</h2>
      <div class="stat">{{ pending_count }} <small>requests</small></div>
    </div>
  </div>

  <!-- Actions -->
  <div class="topbar">
    <div class="section-title">👥 Members</div>
    <form method="POST" action="/test">
      <button class="btn btn-orange" type="submit"
        onclick="return confirm('Send test check-in to all approved members?')">
        🧪 Send Test Check-in
      </button>
    </form>
  </div>

  <!-- Members table -->
  <div class="card full" style="margin-bottom:28px">
    <table>
      <thead>
        <tr>
          <th>Name</th>
          <th>Telegram ID</th>
          <th>Status</th>
          <th>Joined</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody>
        {% for m in members %}
        <tr>
          <td><strong>{{ m.name }}</strong></td>
          <td><code style="color:#888">{{ m.telegram_id }}</code></td>
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
  <div class="section-title">📜 Recent Alert Events</div>
  <div class="card full">
    <table>
      <thead>
        <tr>
          <th>Time</th>
          <th>Type</th>
          <th>Responses</th>
          <th>No Response</th>
        </tr>
      </thead>
      <tbody>
        {% for e in events %}
        <tr {% if e.is_test %}class="alert-row"{% endif %}>
          <td>{{ e.time_fmt }}</td>
          <td><span class="pill {% if e.is_test %}pending{% else %}approved{% endif %}">
            {{ '🧪 Test' if e.is_test else '🚨 Real Alert' }}
          </span></td>
          <td style="color:#86efac">{{ e.ok_count }} ✅ &nbsp; {{ e.help_count }} ❗</td>
          <td style="color:#fca5a5">{{ e.no_resp }}</td>
        </tr>
        {% endfor %}
        {% if not events %}
        <tr><td colspan="4" style="color:#888;text-align:center;padding:32px">
          No events yet. Use the Test button above!
        </td></tr>
        {% endif %}
      </tbody>
    </table>
  </div>

</div>
{% endif %}
</body>
</html>
"""

# ─────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────

def fmt_time(ts):
    if not ts:
        return "—"
    import datetime
    return datetime.datetime.fromtimestamp(ts).strftime("%d %b %Y, %H:%M")

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
        resps = db.get_responses_for_event(e["id"])
        approved = db.get_approved_members()
        responded_ids = {r["telegram_id"] for r in resps}
        no_resp_names = [m["name"] for m in approved if m["telegram_id"] not in responded_ids]
        events.append({
            **e,
            "time_fmt":   fmt_time(e.get("ended_at") or e.get("started_at")),
            "ok_count":   sum(1 for r in resps if r["response"] == "ok"),
            "help_count": sum(1 for r in resps if r["response"] == "help"),
            "no_resp":    ", ".join(no_resp_names) if no_resp_names else "Everyone responded ✅",
        })

    # get alert state from bot (shared via file flag)
    alert_state = "IDLE"
    try:
        if os.path.exists(".alert_state"):
            alert_state = open(".alert_state").read().strip()
    except Exception:
        pass

    return render_template_string(HTML,
        logged_in=True,
        members=members,
        events=events,
        alert_state=alert_state,
        approved_count=sum(1 for m in members_raw if m["status"] == "approved"),
        pending_count=sum(1 for m in members_raw if m["status"] == "pending"),
    )

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
    if not session.get("admin"):
        return redirect("/")
    db.set_status(uid, "approved")
    return redirect("/")

@app.route("/reject/<int:uid>", methods=["POST"])
def reject(uid):
    if not session.get("admin"):
        return redirect("/")
    db.set_status(uid, "rejected")
    return redirect("/")

@app.route("/test", methods=["POST"])
def test_alert():
    if not session.get("admin"):
        return redirect("/")
    # Write a flag file that bot.py checks
    open(".trigger_test", "w").write("1")
    return redirect("/")

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    db.init()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
