import os, json, time
from flask import Flask, render_template_string, request, redirect, session, jsonify

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "fallback-secret")
ADMIN_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "admin123")

import db

HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
<title>Family Safety</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root {
  --bg: #080c10; --surface: #0d1117; --border: #1e2732;
  --text: #cdd9e5; --muted: #545d68; --accent: #388bfd;
  --green: #3fb950; --red: #f85149; --yellow: #d29922;
  --mono: 'IBM Plex Mono', monospace; --sans: 'IBM Plex Sans', sans-serif;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: var(--bg); color: var(--text); font-family: var(--sans); min-height: 100vh; }
.alert-banner { background: #2d0e0e; border-bottom: 2px solid var(--red); color: #ff8f8a; padding: 14px 20px; text-align: center; font-family: var(--mono); font-size: 0.85rem; font-weight: 600; animation: blink 1.4s ease-in-out infinite; }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:0.5} }
.topbar { background: var(--surface); border-bottom: 1px solid var(--border); padding: 14px 20px; display: flex; justify-content: space-between; align-items: center; position: sticky; top: 0; z-index: 100; }
.topbar-title { font-family: var(--mono); font-size: 0.9rem; font-weight: 600; }
.topbar-title span { color: var(--red); }
.signout { color: var(--muted); text-decoration: none; font-size: 0.8rem; font-family: var(--mono); border: 1px solid var(--border); padding: 5px 10px; border-radius: 4px; }
.page { max-width: 640px; margin: 0 auto; padding: 16px; }
.status-row { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; padding: 14px 16px; background: var(--surface); border: 1px solid var(--border); border-radius: 10px; }
.status-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.status-dot.idle { background: var(--green); box-shadow: 0 0 8px var(--green); }
.status-dot.alert { background: var(--red); box-shadow: 0 0 8px var(--red); animation: blink 1s infinite; }
.status-label { font-family: var(--mono); font-size: 0.85rem; font-weight: 600; }
.status-label.idle { color: var(--green); }
.status-label.alert { color: var(--red); }
.status-zones { font-size: 0.8rem; color: var(--muted); margin-left: auto; }
.poller-row { display: flex; align-items: center; gap: 10px; margin-bottom: 20px; padding: 12px 16px; background: var(--surface); border: 1px solid var(--border); border-radius: 10px; }
.poller-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.poller-dot.ok { background: var(--green); box-shadow: 0 0 6px var(--green); }
.poller-dot.warn { background: var(--yellow); box-shadow: 0 0 6px var(--yellow); }
.poller-dot.dead { background: var(--red); box-shadow: 0 0 6px var(--red); }
.poller-label { font-family: var(--mono); font-size: 0.78rem; color: var(--muted); flex: 1; }
.poller-label strong { color: var(--text); }
.cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 20px; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 14px 12px; text-align: center; }
.card-val { font-family: var(--mono); font-size: 1.6rem; font-weight: 600; line-height: 1; }
.card-lbl { font-size: 0.7rem; color: var(--muted); margin-top: 5px; text-transform: uppercase; letter-spacing: 0.05em; }
.section { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; margin-bottom: 16px; overflow: hidden; }
.section-header { padding: 12px 16px; border-bottom: 1px solid var(--border); font-family: var(--mono); font-size: 0.8rem; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.08em; }
.member-row { padding: 12px 16px; border-bottom: 1px solid var(--border); display: flex; align-items: center; gap: 10px; }
.member-row:last-child { border-bottom: none; }
.member-name { font-weight: 500; font-size: 0.9rem; flex: 1; min-width: 0; }
.member-zone { font-size: 0.75rem; color: var(--muted); font-family: var(--mono); white-space: nowrap; }
.member-actions { display: flex; gap: 6px; flex-shrink: 0; }
.badge { display: inline-flex; align-items: center; padding: 3px 8px; border-radius: 4px; font-size: 0.72rem; font-family: var(--mono); font-weight: 600; white-space: nowrap; }
.badge-green { background: #122118; color: var(--green); border: 1px solid #1e3a28; }
.badge-red { background: #200d0d; color: var(--red); border: 1px solid #3d1414; }
.badge-yellow { background: #1f1608; color: var(--yellow); border: 1px solid #3d2e0a; }
.badge-blue { background: #0d1a2d; color: var(--accent); border: 1px solid #1a3050; }
.btn { padding: 5px 10px; border-radius: 5px; border: none; cursor: pointer; font-size: 0.75rem; font-family: var(--mono); font-weight: 600; white-space: nowrap; }
.btn-approve { background: #122118; color: var(--green); border: 1px solid #1e3a28; }
.btn-reject { background: #200d0d; color: var(--red); border: 1px solid #3d1414; }
.btn-remove { background: #111; color: var(--muted); border: 1px solid var(--border); }
.test-btn { display: block; width: 100%; padding: 14px; background: #1a0d00; color: #f0883e; border: 1px solid #4a2800; border-radius: 8px; font-family: var(--mono); font-size: 0.9rem; font-weight: 600; cursor: pointer; text-align: center; }
.history-row { padding: 11px 16px; border-bottom: 1px solid var(--border); display: flex; align-items: center; gap: 10px; }
.history-row:last-child { border-bottom: none; }
.history-time { font-family: var(--mono); font-size: 0.72rem; color: var(--muted); white-space: nowrap; flex-shrink: 0; }
.history-zones { font-size: 0.82rem; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.history-rate { font-family: var(--mono); font-size: 0.75rem; color: var(--muted); white-space: nowrap; }
.empty { padding: 20px 16px; color: var(--muted); font-size: 0.85rem; text-align: center; font-family: var(--mono); }
.login-wrap { min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 20px; }
.login-box { background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 36px 28px; width: 100%; max-width: 340px; }
.login-logo { font-size: 1.8rem; text-align: center; margin-bottom: 6px; }
.login-sub { text-align: center; color: var(--muted); font-size: 0.82rem; margin-bottom: 28px; }
.login-input { width: 100%; padding: 11px 14px; background: var(--bg); border: 1px solid var(--border); border-radius: 7px; color: var(--text); font-size: 0.9rem; margin-bottom: 12px; outline: none; }
.login-input:focus { border-color: var(--accent); }
.login-btn { width: 100%; padding: 11px; background: var(--accent); color: #fff; border: none; border-radius: 7px; font-size: 0.9rem; font-weight: 600; cursor: pointer; }
.login-error { color: var(--red); font-size: 0.82rem; text-align: center; margin-top: 10px; font-family: var(--mono); }
</style>
</head>
<body>

{% if not logged_in %}
<div class="login-wrap">
  <div class="login-box">
    <div class="login-logo">🚨</div>
    <div class="login-sub">Family Safety — Admin</div>
    <form method="POST" action="/login">
      <input class="login-input" type="password" name="password" placeholder="Password" autofocus>
      <button class="login-btn" type="submit">Sign in</button>
    </form>
    {% if error %}<div class="login-error">{{ error }}</div>{% endif %}
  </div>
</div>

{% else %}

{% if alert_active %}
<div class="alert-banner">ALERT ACTIVE — {{ alert_zones }}</div>
{% endif %}

<div class="topbar">
  <div class="topbar-title"><span>⬤</span> Family Safety</div>
  <a class="signout" href="/logout">sign out</a>
</div>

<div class="page">

  <div class="status-row">
    <div class="status-dot {{ 'alert' if alert_active else 'idle' }}"></div>
    <div class="status-label {{ 'alert' if alert_active else 'idle' }}">
      {{ 'ALERT' if alert_active else 'ALL CLEAR' }}
    </div>
    {% if alert_active and alert_zones %}
    <div class="status-zones">{{ alert_zones }}</div>
    {% endif %}
  </div>

  <div class="poller-row">
    <div class="poller-dot {{ poller_status }}"></div>
    <div class="poller-label"><strong>GCP Poller</strong> — {{ poller_msg }}</div>
  </div>

  <div class="cards">
    <div class="card"><div class="card-val">{{ approved }}</div><div class="card-lbl">Members</div></div>
    <div class="card"><div class="card-val">{{ observers }}</div><div class="card-lbl">Observers</div></div>
    <div class="card"><div class="card-val">{{ pending }}</div><div class="card-lbl">Pending</div></div>
  </div>

  <div class="section">
    <div class="section-header">Members</div>
    {% if members %}
      {% for m in members %}
      <div class="member-row">
        <div>
          <div class="member-name">{{ m.name }}</div>
          <div class="member-zone">{{ m.zone or '—' }}</div>
        </div>
        {% if m.status == 'approved' %}<span class="badge badge-green">approved</span>
        {% elif m.status == 'pending' %}<span class="badge badge-yellow">pending</span>
        {% else %}<span class="badge badge-red">rejected</span>{% endif %}
        <div class="member-actions">
          {% if m.status == 'pending' %}
          <form method="POST" action="/approve/{{ m.telegram_id }}">
            <button class="btn btn-approve">Approve</button>
          </form>
          <form method="POST" action="/reject/{{ m.telegram_id }}">
            <button class="btn btn-reject">Reject</button>
          </form>
          {% endif %}
          <form method="POST" action="/remove/{{ m.telegram_id }}" onsubmit="return confirm('Remove {{ m.name }}?')">
            <button class="btn btn-remove">Remove</button>
          </form>
        </div>
      </div>
      {% endfor %}
    {% else %}
      <div class="empty">No members yet</div>
    {% endif %}
  </div>

  {% if last_checkins %}
  <div class="section">
    <div class="section-header">Last Check-in</div>
    {% for m in last_checkins %}
    <div class="member-row">
      <div class="member-name">{{ m.name }}</div>
      <div class="member-zone">{{ m.zone or '—' }}</div>
      {% if m.response == 'ok' %}<span class="badge badge-green">Safe</span>
      {% elif m.response == 'help' %}<span class="badge badge-red">Help</span>
      {% else %}<span class="badge badge-yellow">Waiting</span>{% endif %}
    </div>
    {% endfor %}
  </div>
  {% endif %}

  {% if history %}
  <div class="section">
    <div class="section-header">History</div>
    {% for h in history %}
    <div class="history-row">
      <div class="history-time">{{ h.time }}</div>
      <div class="history-zones">{{ h.zones }}</div>
      {% if h.is_test %}<span class="badge badge-blue">test</span>{% endif %}
      <div class="history-rate">{{ h.responded }}/{{ h.total }}</div>
    </div>
    {% endfor %}
  </div>
  {% endif %}

  <div class="section">
    <div class="section-header">Test</div>
    <div style="padding:14px">
      <form method="POST" action="/test">
        <button class="test-btn" type="submit">Send Test Alert</button>
      </form>
    </div>
  </div>

</div>

<script>
setInterval(function() {
  fetch('/api/state').then(function(r) { return r.json(); }).then(function(d) {
    document.title = d.alert_active ? 'ALERT — Family Safety' : 'Family Safety';
  }).catch(function() {});
}, 3000);
</script>

{% endif %}
</body>
</html>
"""

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

@app.
