import os, json, time, uuid
from flask import Flask, render_template_string, request, redirect, session, jsonify

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "fallback-secret")
ADMIN_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "admin123")

import db

# ─────────────────────────────────────────
# HTML TEMPLATE
# ─────────────────────────────────────────
HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>🚨 Family Safety</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #0f0f0f; color: #e0e0e0; font-family: 'Segoe UI', sans-serif; min-height: 100vh; }
  .topbar { background: #1a1a1a; padding: 16px 24px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #2a2a2a; }
  .topbar h1 { font-size: 1.2rem; font-weight: 600; }
  .topbar a { color: #888; text-decoration: none; font-size: 0.85rem; }
  .alert-banner { background: #7f1d1d; border: 1px solid #ef4444; color: #fca5a5; padding: 16px 24px; text-align: center; font-weight: 600; font-size: 1rem; animation: pulse 1.5s infinite; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.6} }
  .container { max-width: 960px; margin: 0 auto; padding: 24px; }
  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin-bottom: 28px; }
  .card { background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 10px; padding: 20px; text-align: center; }
  .card .val { font-size: 2rem; font-weight: 700; color: #fff; }
  .card .lbl { font-size: 0.8rem; color: #888; margin-top: 4px; }
  .section { background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 10px; padding: 20px; margin-bottom: 24px; }
  .section h2 { font-size: 1rem; font-weight: 600; margin-bottom: 16px; color: #ccc; }
  table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
  th { text-align: left; color: #666; font-weight: 500; padding: 8px 12px; border-bottom: 1px solid #2a2a2a; }
  td { padding: 10px 12px; border-bottom: 1px solid #1e1e1e; }
  tr:last-child td { border-bottom: none; }
  .badge { display: inline-block; padding: 2px 10px; border-radius: 20px; font-size: 0.75rem; font-weight: 600; }
  .badge-green { background: #14532d; color: #86efac; }
  .badge-yellow { background: #713f12; color: #fde68a; }
  .badge-red { background: #7f1d1d; color: #fca5a5; }
  .badge-blue { background: #1e3a5f; color: #93c5fd; }
  .btn { padding: 6px 14px; border-radius: 6px; border: none; cursor: pointer; font-size: 0.8rem; font-weight: 600; }
  .btn-green { background: #166534; color: #86efac; }
  .btn-red { background: #7f1d1d; color: #fca5a5; }
  .btn-gray { background: #2a2a2a; color: #aaa; }
  .btn-orange { background: #92400e; color: #fcd34d; font-size: 0.95rem; padding: 10px 24px; width: 100%; margin-top: 8px; }
  .login-wrap { display: flex; align-items: center; justify-content: center; min-height: 100vh; }
  .login-box { background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 12px; padding: 40px; width: 320px; text-align: center; }
  .login-box h2 { margin-bottom: 24px; font-size: 1.3rem; }
  .login-box input { width: 100%; padding: 10px 14px; background: #0f0f0f; border: 1px solid #333; border-radius: 6px; color: #fff; font-size: 0.9rem; margin-bottom: 14px; }
  .login-box button { width: 100%; padding: 10px; background: #2563eb; color: #fff; border: none; border-radius: 6px; font-size: 0.95rem; cursor: pointer; font-weight: 600; }
</style>
</head>
<body>

{% if not logged_in %}
<div class="login-wrap">
  <div class="login-box">
    <h2>🚨 Family Safety</h2>
    <p style="color:#888;margin-bottom:20px;font-size:0.85rem">Admin dashboard — sign in to continue</p>
    <form method="POST" action="/login">
      <input type="password" name="password" placeholder="Password" autofocus>
      <button type="submit">Sign in</button>
    </form>
    {% if error %}<p style="color:#f87171;margin-top:12px;font-size:0.85rem">{{ error }}</p>{% endif %}
  </div>
</div>

{% else %}

{% if alert_active %}
<div class="alert-banner">🚨 ALERT ACTIVE — {{ alert_zones }}</div>
{% endif %}

<div class="topbar">
  <h1>🚨 Family Safety Dashboard</h1>
  <a href="/logout">Sign out</a>
</div>

<div class="container">
  <div class="cards">
    <div class="card">
      <div class="val" style="color:{% if alert_active %}#ef4444{% else %}#22c55e{% endif %}">
        {% if alert_active %}🚨 ALERT{% else %}✅ IDLE{% endif %}
      </div>
      <div class="lbl">Alert State</div>
    </div>
    <div class="card"><div class="val">{{ approved }}</div><div class="lbl">Approved Members</div></div>
    <div class="card"><div class="val">{{ observers }}</div><div class="lbl">Observers</div></div>
    <div class="card"><div class="val">{{ pending }}</div><div class="lbl">Pending Approval</div></div>
  </div>

  <!-- Members -->
  <div class="section">
    <h2>👥 Members</h2>
    {% if members %}
    <table>
      <tr><th>Name</th><th>Zone</th><th>Status</th><th>Actions</th></tr>
      {% for m in members %}
      <tr>
        <td>{{ m.name }}</td>
        <td>{{ m.zone or '—' }}</td>
        <td>
          {% if m.status == 'approved' %}<span class="badge badge-green">Approved</span>
          {% elif m.status == 'pending' %}<span class="badge badge-yellow">Pending</span>
          {% else %}<span class="badge badge-red">Rejected</span>{% endif %}
        </td>
        <td>
          {% if m.status == 'pending' %}
          <form method="POST" action="/approve/{{ m.telegram_id }}" style="display:inline">
            <button class="btn btn-green">✅ Approve</button>
          </form>
          <form method="POST" action="/reject/{{ m.telegram_id }}" style="display:inline;margin-left:6px">
            <button class="btn btn-red">❌ Reject</button>
          </form>
          {% endif %}
          <form method="POST" action="/remove/{{ m.telegram_id }}" style="display:inline;margin-left:6px"
                onsubmit="return confirm('Remove {{ m.name }}?')">
            <button class="btn btn-gray">🗑 Remove</button>
          </form>
        </td>
      </tr>
      {% endfor %}
    </table>
    {% else %}
    <p style="color:#666;font-size:0.875rem">No members yet.</p>
    {% endif %}
  </div>

  <!-- Last Check-in Status -->
  {% if last_checkins %}
  <div class="section">
    <h2>📋 Last Check-in Status</h2>
    <table>
      <tr><th>Name</th><th>Zone</th><th>Response</th></tr>
      {% for m in last_checkins %}
      <tr>
        <td>{{ m.name }}</td>
        <td>{{ m.zone or '—' }}</td>
        <td>
          {% if m.response == 'ok' %}<span class="badge badge-green">✅ Safe</span>
          {% elif m.response == 'help' %}<span class="badge badge-red">🆘 Help</span>
          {% else %}<span class="badge badge-yellow">⏳ No response</span>{% endif %}
        </td>
      </tr>
      {% endfor %}
    </table>
  </div>
  {% endif %}

  <!-- Alert History -->
  {% if history %}
  <div class="section">
    <h2>📜 Alert History</h2>
    <table>
      <tr><th>Time</th><th>Zones</th><th>Type</th><th>Responses</th></tr>
      {% for h in history %}
      <tr>
        <td>{{ h.time }}</td>
        <td>{{ h.zones }}</td>
        <td>{% if h.is_test %}<span class="badge badge-blue">Test</span>{% else %}<span class="badge badge-red">Real</span>{% endif %}</td>
        <td>{{ h.responded }}/{{ h.total }} ({{ h.rate }}%)</td>
      </tr>
      {% endfor %}
    </table>
  </div>
  {% endif %}

  <!-- Test Button -->
  <div class="section">
    <h2>🧪 Test Alert</h2>
    <p style="color:#888;font-size:0.85rem;margin-bottom:12px">Sends a test check-in to all approved members and a test notification to observers.</p>
    <form method="POST" action="/test">
      <button class="btn btn-orange">🚨 Send Test Alert</button>
    </form>
  </div>
</div>

<script>
setInterval(() => {
  fetch('/api/state').then(r => r.json()).then(d => {
    document.title = d.alert_active ? '🚨 ALERT — Family Safety' : '✅ Family Safety';
  });
}, 3000);
</script>
{% endif %}
</body>
</html>
"""

# ─────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────
@app.route("/")
def index():
    if not session.get("logged_in"):
        return render_template_string(HTML, logged_in=False, error=None)
    return render_dashboard()

@app.route("/login", methods=["POST"])
def login():
    if request.form.get("password") == ADMIN_PASSWORD:
        session["logged_in"] = True
        return redirect("/")
    return render_template_string(HTML, logged_in=False, error="Wrong password")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/approve/<int:uid>", methods=["POST"])
def approve(uid):
    if not session.get("logged_in"): return redirect("/")
    db.set_status(uid, "approved")
    return redirect("/")

@app.route("/reject/<int:uid>", methods=["POST"])
def reject(uid):
    if not session.get("logged_in"): return redirect("/")
    db.set_status(uid, "rejected")
    return redirect("/")

@app.route("/remove/<int:uid>", methods=["POST"])
def remove(uid):
    if not session.get("logged_in"): return redirect("/")
    db.remove_member(uid)
    return redirect("/")

@app.route("/webhook/alert", methods=["POST"])
def webhook_alert():
    try:
        data = request.get_json(force=True)
        cities = data.get("cities", [])
        alert_id = data.get("id", "")
        if cities and alert_id:
            with open(".webhook_alert", "w") as f:
                json.dump({"id": alert_id, "cities": cities}, f)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/test", methods=["POST"])
def test_alert():
    if not session.get("logged_in"): return redirect("/")
    open(".trigger_test", "w").write("1")
    return redirect("/")

@app.route("/api/state")
def api_state():
    try:
        state_raw = open(".alert_state").read()
        parts = state_raw.split("|")
        alert_active = parts[0] == "ALERT"
        zones = parts[1] if len(parts) > 1 else ""
    except:
        alert_active = False
        zones = ""
    return jsonify({"alert_active": alert_active, "zones": zones})

# ─────────────────────────────────────────
# DASHBOARD BUILDER
# ─────────────────────────────────────────
def render_dashboard():
    members = db.get_all_members()
    approved_members = [m for m in members if m["status"] == "approved" and (m.get("zone") or "") != "🌍 Abroad"]
    observers = [m for m in members if m["status"] == "approved" and (m.get("zone") or "") == "🌍 Abroad"]
    pending = [m for m in members if m["status"] == "pending"]

    try:
        state_raw = open(".alert_state").read()
        parts = state_raw.split("|")
        alert_active = parts[0] == "ALERT"
        alert_zones = parts[1] if len(parts) > 1 else ""
    except:
        alert_active = False
        alert_zones = ""

    history_raw = db.get_alert_history(limit=10)
    history = []
    for h in history_raw:
        total = len(approved_members)
        responded = h.get("response_count", 0)
        rate = round((responded / total * 100) if total > 0 else 0)
        ts = h.get("ended_at") or h.get("started_at") or 0
        history.append({
            "time": time.strftime("%b %d %H:%M", time.localtime(ts)),
            "zones": h.get("zones") or "—",
            "is_test": h.get("is_test", False),
            "responded": responded,
            "total": total,
            "rate": rate,
        })

    last_checkins = []
    if history_raw:
        last_event_id = history_raw[0].get("id")
        if last_event_id:
            responses = {r["telegram_id"]: r["response"] for r in db.get_responses_for_event(last_event_id)}
            for m in approved_members:
                last_checkins.append({
                    "name": m["name"],
                    "zone": m.get("zone") or "—",
                    "response": responses.get(m["telegram_id"]),
                })

    return render_template_string(
        HTML,
        logged_in=True,
        alert_active=alert_active,
        alert_zones=alert_zones,
        approved=len(approved_members),
        observers=len(observers),
        pending=len(pending),
        members=members,
        history=history,
        last_checkins=last_checkins,
        error=None,
    )

if __name__ == "__main__":
    db.init()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
