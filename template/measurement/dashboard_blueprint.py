"""
Drop-in Flask Blueprint for the measurement dashboard. Wire into any
blend-zone tool's existing app.py:

    from measurement.dashboard_blueprint import build_measurement_blueprint
    app.register_blueprint(build_measurement_blueprint(db_path="tool.db", tool_name="bay-log"))

Then visit /measurement/dashboard. The blueprint owns its own routes and
templates — it doesn't touch your tool's existing routes or database
tables beyond the measurement_* tables it creates via logger.init_db().

Template version: see VERSION in this folder.
"""
from flask import Blueprint, render_template_string, request, redirect, url_for, jsonify

from measurement.logger import init_db, get_summary, log_manual_entry


DASHBOARD_TEMPLATE = """
<!doctype html>
<html>
<head>
  <title>{{ tool_name }} — Measurement Dashboard</title>
  <style>
    body { font-family: 'IBM Plex Sans', sans-serif; background: #fafaf9; color: #1c1917; max-width: 900px; margin: 40px auto; padding: 0 16px; }
    h1 { font-size: 20px; } h2 { font-size: 15px; color: #57534e; margin-top: 32px; }
    .stat-row { display: flex; gap: 16px; flex-wrap: wrap; margin: 12px 0; }
    .stat { background: #fff; border: 1px solid #e7e5e4; border-radius: 10px; padding: 12px 16px; min-width: 140px; }
    .stat .label { font-size: 11px; color: #78716c; text-transform: uppercase; }
    .stat .value { font-size: 22px; font-weight: 600; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 8px; }
    th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid #e7e5e4; }
    .empty { color: #a8a29e; font-size: 13px; padding: 12px 0; }
    form.manual { background: #fff; border: 1px solid #e7e5e4; border-radius: 10px; padding: 16px; margin-top: 8px; }
    form.manual input, form.manual select { display: block; width: 100%; margin: 4px 0 12px; padding: 6px 8px; border: 1px solid #d6d3d1; border-radius: 6px; }
    form.manual button { background: #171717; color: #fff; border: none; padding: 8px 16px; border-radius: 8px; cursor: pointer; }
  </style>
</head>
<body>
  <h1>{{ tool_name }} — Measurement Dashboard</h1>
  <p style="color:#78716c; font-size:13px;">Phase-gated tool health, per the Deployment Measurement Framework. Not a curriculum/student-outcome evaluation.</p>

  <h2>Technical Reliability</h2>
  <div class="stat-row">
    <div class="stat"><div class="label">Total events</div><div class="value">{{ s.total_events }}</div></div>
    <div class="stat"><div class="label">Success rate</div><div class="value">{{ s.success_rate ~ '%' if s.success_rate is not none else '—' }}</div></div>
    <div class="stat"><div class="label">Avg latency</div><div class="value">{{ (s.avg_latency_ms ~ ' ms') if s.avg_latency_ms else '—' }}</div></div>
    <div class="stat"><div class="label">p95 latency</div><div class="value">{{ (s.p95_latency_ms ~ ' ms') if s.p95_latency_ms else '—' }}</div></div>
  </div>

  <h2>By Action</h2>
  {% if s.by_action %}
  <table><tr><th>Action</th><th>Count</th><th>Success rate</th></tr>
    {% for a in s.by_action %}
    <tr><td>{{ a.action }}</td><td>{{ a.n }}</td><td>{{ ((100 * a.ok / a.n) | round(1)) if a.n else '—' }}%</td></tr>
    {% endfor %}
  </table>
  {% else %}<div class="empty">No events logged yet.</div>{% endif %}

  <h2>Errors by Type</h2>
  {% if s.errors_by_type %}
  <table><tr><th>Error type</th><th>Count</th></tr>
    {% for e in s.errors_by_type %}<tr><td>{{ e.error_type }}</td><td>{{ e.n }}</td></tr>{% endfor %}
  </table>
  {% else %}<div class="empty">No errors logged.</div>{% endif %}

  <h2>Log a manual entry (time saved / edit rate)</h2>
  <form class="manual" method="post" action="{{ url_for('measurement.log_manual', tool_name=tool_name) }}">
    <label>Unit label (e.g. ticket ID, package ID)</label>
    <input name="unit_label" required>
    <label>Time spent (minutes)</label>
    <input name="time_spent_min" type="number" step="0.1">
    <label>Manual/paper baseline (minutes, if known)</label>
    <input name="baseline_min" type="number" step="0.1">
    <label>Edit type</label>
    <select name="edit_type">
      <option value="none">None — used as-is</option>
      <option value="cosmetic">Cosmetic (wording/formatting)</option>
      <option value="substantive">Substantive (content/logic changes)</option>
    </select>
    <label>Notes</label>
    <input name="notes">
    <button type="submit">Log entry</button>
  </form>

  <h2>Recent manual entries</h2>
  {% if s.recent_manual_entries %}
  <table><tr><th>Unit</th><th>Time (min)</th><th>Baseline (min)</th><th>Edit type</th><th>When</th></tr>
    {% for m in s.recent_manual_entries %}
    <tr><td>{{ m.unit_label }}</td><td>{{ m.time_spent_min or '—' }}</td><td>{{ m.baseline_min or '—' }}</td><td>{{ m.edit_type or '—' }}</td><td>{{ m.logged_at }}</td></tr>
    {% endfor %}
  </table>
  {% else %}<div class="empty">No manual entries yet.</div>{% endif %}
</body>
</html>
"""


def build_measurement_blueprint(db_path: str, tool_name: str) -> Blueprint:
    bp = Blueprint("measurement", __name__, url_prefix="/measurement")
    init_db(db_path)

    @bp.route("/dashboard")
    def dashboard():
        summary = get_summary(db_path, tool_name)
        return render_template_string(DASHBOARD_TEMPLATE, s=summary, tool_name=tool_name)

    @bp.route("/log/<tool_name>", methods=["POST"], endpoint="log_manual")
    def log_manual(tool_name):
        log_manual_entry(
            db_path,
            tool_name=tool_name,
            unit_label=request.form["unit_label"],
            time_spent_min=request.form.get("time_spent_min", type=float),
            baseline_min=request.form.get("baseline_min", type=float),
            edit_type=request.form.get("edit_type") or None,
            notes=request.form.get("notes") or None,
        )
        return redirect(url_for("measurement.dashboard"))

    @bp.route("/api/summary")
    def api_summary():
        return jsonify(get_summary(db_path, tool_name))

    return bp
