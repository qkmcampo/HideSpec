from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import sqlite3
import json
from pathlib import Path
from datetime import datetime, timedelta

app = Flask(__name__)
app.config["SECRET_KEY"] = "hidespec-secret-key"

CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "hidespec.db"
CAPTURES_DIR = BASE_DIR / "captures"

CAPTURES_DIR.mkdir(parents=True, exist_ok=True)


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS inspections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hide_id TEXT NOT NULL,
            classification TEXT NOT NULL,
            total_defects INTEGER NOT NULL DEFAULT 0,
            defects_json TEXT NOT NULL DEFAULT '[]',
            snapshot_path TEXT,
            created_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


def row_to_inspection(row):
    return {
        "id": row["id"],
        "hide_id": row["hide_id"],
        "classification": row["classification"],
        "total_defects": row["total_defects"],
        "defects": json.loads(row["defects_json"] or "[]"),
        "snapshot_path": row["snapshot_path"],
        "created_at": row["created_at"],
    }


def get_session_summary():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) AS total FROM inspections")
    total_inspected = cur.fetchone()["total"]

    cur.execute("SELECT COUNT(*) AS good_count FROM inspections WHERE classification = 'Good'")
    good_count = cur.fetchone()["good_count"]

    cur.execute("SELECT COUNT(*) AS bad_count FROM inspections WHERE classification = 'Bad'")
    bad_count = cur.fetchone()["bad_count"]

    conn.close()

    defect_rate = round((bad_count / total_inspected) * 100, 2) if total_inspected > 0 else 0

    return {
        "total_inspected": total_inspected,
        "good_count": good_count,
        "bad_count": bad_count,
        "defect_rate": defect_rate,
    }


def get_defect_type_summary():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT defects_json FROM inspections ORDER BY datetime(created_at) DESC")
    rows = cur.fetchall()
    conn.close()

    counts = {}
    for row in rows:
        defects = json.loads(row["defects_json"] or "[]")
        for defect in defects:
            defect_type = defect.get("type", "unknown")
            counts[defect_type] = counts.get(defect_type, 0) + 1

    return counts


def get_period_start(period):
    now = datetime.utcnow()

    if period == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "week":
        return now - timedelta(days=7)
    if period == "month":
        return now - timedelta(days=30)
    if period == "all":
        return None

    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def get_analytics_summary(period="today"):
    conn = get_db_connection()
    cur = conn.cursor()

    start_dt = get_period_start(period)

    if start_dt is None:
        cur.execute("""
            SELECT
                COUNT(*) AS total_inspections,
                SUM(CASE WHEN classification = 'Good' THEN 1 ELSE 0 END) AS good_count,
                SUM(CASE WHEN classification = 'Bad' THEN 1 ELSE 0 END) AS bad_count,
                AVG(total_defects) AS avg_defects_per_hide
            FROM inspections
        """)
    else:
        cur.execute("""
            SELECT
                COUNT(*) AS total_inspections,
                SUM(CASE WHEN classification = 'Good' THEN 1 ELSE 0 END) AS good_count,
                SUM(CASE WHEN classification = 'Bad' THEN 1 ELSE 0 END) AS bad_count,
                AVG(total_defects) AS avg_defects_per_hide
            FROM inspections
            WHERE datetime(created_at) >= datetime(?)
        """, (start_dt.isoformat(),))

    row = cur.fetchone()
    conn.close()

    total = row["total_inspections"] or 0
    good = row["good_count"] or 0
    bad = row["bad_count"] or 0
    avg_defects = round(row["avg_defects_per_hide"] or 0, 2)
    pass_rate = round((good / total) * 100, 2) if total > 0 else 0
    defect_rate = round((bad / total) * 100, 2) if total > 0 else 0

    return {
        "period": period,
        "total_inspections": total,
        "good_count": good,
        "bad_count": bad,
        "pass_rate": pass_rate,
        "defect_rate": defect_rate,
        "avg_defects_per_hide": avg_defects,
    }


def get_defect_distribution(period="today"):
    conn = get_db_connection()
    cur = conn.cursor()

    start_dt = get_period_start(period)

    if start_dt is None:
        cur.execute("SELECT defects_json FROM inspections ORDER BY datetime(created_at) DESC")
    else:
        cur.execute("""
            SELECT defects_json
            FROM inspections
            WHERE datetime(created_at) >= datetime(?)
            ORDER BY datetime(created_at) DESC
        """, (start_dt.isoformat(),))

    rows = cur.fetchall()
    conn.close()

    counts = {}
    for row in rows:
        defects = json.loads(row["defects_json"] or "[]")
        for defect in defects:
            defect_type = defect.get("type", "unknown")
            counts[defect_type] = counts.get(defect_type, 0) + 1

    defects = [
        {"type": defect_type, "count": count}
        for defect_type, count in counts.items()
    ]
    defects.sort(key=lambda x: x["count"], reverse=True)

    return {
        "period": period,
        "defects": defects
    }


def get_timeline_data(period="today"):
    conn = get_db_connection()
    cur = conn.cursor()

    start_dt = get_period_start(period)

    if period == "today":
        group_fmt = "%H:00"
    elif period in ("week", "month"):
        group_fmt = "%Y-%m-%d"
    else:
        group_fmt = "%Y-%m"

    if start_dt is None:
        cur.execute(f"""
            SELECT
                strftime('{group_fmt}', created_at) AS time_label,
                SUM(CASE WHEN classification = 'Good' THEN 1 ELSE 0 END) AS good,
                SUM(CASE WHEN classification = 'Bad' THEN 1 ELSE 0 END) AS bad
            FROM inspections
            GROUP BY time_label
            ORDER BY time_label ASC
        """)
    else:
        cur.execute(f"""
            SELECT
                strftime('{group_fmt}', created_at) AS time_label,
                SUM(CASE WHEN classification = 'Good' THEN 1 ELSE 0 END) AS good,
                SUM(CASE WHEN classification = 'Bad' THEN 1 ELSE 0 END) AS bad
            FROM inspections
            WHERE datetime(created_at) >= datetime(?)
            GROUP BY time_label
            ORDER BY time_label ASC
        """, (start_dt.isoformat(),))

    rows = cur.fetchall()
    conn.close()

    return {
        "period": period,
        "timeline": [
            {
                "time_label": row["time_label"] or "",
                "good": row["good"] or 0,
                "bad": row["bad"] or 0,
            }
            for row in rows
        ]
    }


def create_inspection_record(hide_id, defects, snapshot_path=None, created_at=None):
    if created_at is None:
        created_at = datetime.utcnow().isoformat()

    total_defects = len(defects)
    classification = "Bad" if total_defects > 0 else "Good"

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO inspections (
            hide_id,
            classification,
            total_defects,
            defects_json,
            snapshot_path,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        hide_id,
        classification,
        total_defects,
        json.dumps(defects),
        snapshot_path,
        created_at,
    ))

    inspection_id = cur.lastrowid
    conn.commit()

    cur.execute("SELECT * FROM inspections WHERE id = ?", (inspection_id,))
    row = cur.fetchone()
    conn.close()

    inspection = row_to_inspection(row)

    socketio.emit("new_inspection", inspection)
    socketio.emit("status_update", get_session_summary())

    return inspection


def reset_history(delete_captures=False):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM inspections")
    conn.commit()
    conn.close()

    deleted_files = []

    if delete_captures:
        for file_path in CAPTURES_DIR.glob("*.jpg"):
            try:
                file_path.unlink()
                deleted_files.append(file_path.name)
            except Exception as e:
                print(f"Failed to delete {file_path}: {e}")

    socketio.emit("status_update", {
        "total_inspected": 0,
        "good_count": 0,
        "bad_count": 0,
        "defect_rate": 0,
    })

    return deleted_files


@app.route("/api/status", methods=["GET"])
def api_status():
    return jsonify({
        "status": "online",
        "message": "HideSpec API server running",
        "system": {
            "model": "YOLOv8n",
            "platform": "Raspberry Pi 5",
            "camera": "Pi Camera Module 3",
        },
        "session": get_session_summary(),
        "analytics": {
            "defects_by_type": get_defect_type_summary()
        }
    })


@app.route("/api/inspections/latest", methods=["GET"])
def latest_inspection():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM inspections ORDER BY datetime(created_at) DESC LIMIT 1")
    row = cur.fetchone()
    conn.close()

    if row is None:
        return jsonify({
            "message": "No inspection has been recorded yet"
        }), 404

    return jsonify(row_to_inspection(row))


@app.route("/api/inspections", methods=["GET"])
def get_inspections():
    limit = request.args.get("limit", default=20, type=int)
    limit = max(1, min(limit, 100))

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT * FROM inspections ORDER BY datetime(created_at) DESC LIMIT ?",
        (limit,)
    )
    rows = cur.fetchall()
    conn.close()

    inspections = [row_to_inspection(row) for row in rows]

    return jsonify({
        "count": len(inspections),
        "inspections": inspections
    })


@app.route("/api/analytics/summary", methods=["GET"])
def analytics_summary():
    return jsonify({
        "session": get_session_summary(),
        "defects_by_type": get_defect_type_summary()
    })


@app.route("/api/analytics", methods=["GET"])
def analytics_overview():
    period = request.args.get("period", default="today", type=str)
    return jsonify(get_analytics_summary(period))


@app.route("/api/analytics/defects", methods=["GET"])
def analytics_defects():
    period = request.args.get("period", default="today", type=str)
    return jsonify(get_defect_distribution(period))


@app.route("/api/analytics/timeline", methods=["GET"])
def analytics_timeline():
    period = request.args.get("period", default="today", type=str)
    return jsonify(get_timeline_data(period))


@app.route("/api/inspections", methods=["POST"])
def create_inspection():
    data = request.get_json(silent=True) or {}

    hide_id = data.get("hide_id")
    defects = data.get("defects", [])
    snapshot_path = data.get("snapshot_path")

    if not hide_id:
        return jsonify({"error": "hide_id is required"}), 400

    if not isinstance(defects, list):
        return jsonify({"error": "defects must be a list"}), 400

    inspection = create_inspection_record(
        hide_id=hide_id,
        defects=defects,
        snapshot_path=snapshot_path
    )

    return jsonify(inspection), 201


@app.route("/api/history/reset", methods=["POST"])
def reset_history_route():
    data = request.get_json(silent=True) or {}
    delete_captures = bool(data.get("delete_captures", False))

    deleted_files = reset_history(delete_captures=delete_captures)

    return jsonify({
        "status": "ok",
        "message": "Inspection history reset successfully",
        "deleted_captures": deleted_files,
        "deleted_capture_count": len(deleted_files),
    })


@socketio.on("connect")
def handle_connect():
    emit("connected", {
        "message": "WebSocket connected",
        "session": get_session_summary()
    })


@socketio.on("disconnect")
def handle_disconnect():
    print("Client disconnected")


@app.route("/", methods=["GET"])
def home():
    return """
    <html>
      <head>
        <title>HideSpec API Server</title>
      </head>
      <body style="font-family:Arial;background:#111;color:#fff;text-align:center;padding-top:40px;">
        <h1>HideSpec API Server</h1>

        <p><a href="/api/status" style="color:#4da3ff;">/api/status</a></p>
        <p><a href="/api/inspections/latest" style="color:#4da3ff;">/api/inspections/latest</a></p>
        <p><a href="/api/inspections" style="color:#4da3ff;">/api/inspections</a></p>
        <p><a href="/api/analytics/summary" style="color:#4da3ff;">/api/analytics/summary</a></p>
        <p><a href="/api/analytics?period=today" style="color:#4da3ff;">/api/analytics?period=today</a></p>
        <p><a href="/api/analytics/defects?period=today" style="color:#4da3ff;">/api/analytics/defects?period=today</a></p>
        <p><a href="/api/analytics/timeline?period=today" style="color:#4da3ff;">/api/analytics/timeline?period=today</a></p>

        <div style="margin-top:30px;">
          <button
            onclick="resetHistory(false)"
            style="padding:12px 20px;background:#d73a49;color:white;border:none;border-radius:8px;cursor:pointer;font-size:16px;margin-right:10px;"
          >
            Reset History Only
          </button>

          <button
            onclick="resetHistory(true)"
            style="padding:12px 20px;background:#8b0000;color:white;border:none;border-radius:8px;cursor:pointer;font-size:16px;"
          >
            Reset History + Captures
          </button>
        </div>

        <script>
          async function resetHistory(deleteCaptures) {
            const label = deleteCaptures ? "history and captured images" : "history";
            const ok = confirm("Delete all " + label + "?");
            if (!ok) return;

            const res = await fetch('/api/history/reset', {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json'
              },
              body: JSON.stringify({
                delete_captures: deleteCaptures
              })
            });

            const data = await res.json();
            alert(data.message || 'History reset');
            location.reload();
          }
        </script>
      </body>
    </html>
    """


if __name__ == "__main__":
    print("=" * 55)
    print("HIDESPEC - API SERVER")
    print("=" * 55)

    init_db()

    print(f"Database: {DB_PATH}")
    print("API status: http://0.0.0.0:5000/api/status")
    print("Latest inspection: http://0.0.0.0:5000/api/inspections/latest")
    print("Inspection history: http://0.0.0.0:5000/api/inspections")
    print("Analytics summary: http://0.0.0.0:5000/api/analytics/summary")
    print("Analytics overview: http://0.0.0.0:5000/api/analytics?period=today")
    print("Analytics defects: http://0.0.0.0:5000/api/analytics/defects?period=today")
    print("Analytics timeline: http://0.0.0.0:5000/api/analytics/timeline?period=today")
    print("Reset history: http://0.0.0.0:5000/api/history/reset")

    socketio.run(app, host="0.0.0.0", port=5000, debug=False)