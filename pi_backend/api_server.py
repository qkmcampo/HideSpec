from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import sqlite3
import json
import os
from datetime import datetime
from pathlib import Path

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

    cur.execute("SELECT defects_json FROM inspections ORDER BY created_at DESC")
    rows = cur.fetchall()
    conn.close()

    counts = {}
    for row in rows:
        defects = json.loads(row["defects_json"] or "[]")
        for defect in defects:
            defect_type = defect.get("type", "unknown")
            counts[defect_type] = counts.get(defect_type, 0) + 1

    return counts


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


@app.route("/api/inspections", methods=["POST"])
def create_inspection():
    """
    Temporary/manual endpoint so you can create inspection records now.
    Later, this can be called automatically from your detection pipeline.
    """
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
      <body style="font-family:Arial;background:#111;color:#fff;text-align:center;padding-top:40px;">
        <h1>HideSpec API Server</h1>
        <p>API status: <a href="/api/status" style="color:#4da3ff;">/api/status</a></p>
        <p>Latest inspection: <a href="/api/inspections/latest" style="color:#4da3ff;">/api/inspections/latest</a></p>
        <p>Inspection history: <a href="/api/inspections" style="color:#4da3ff;">/api/inspections</a></p>
        <p>Analytics summary: <a href="/api/analytics/summary" style="color:#4da3ff;">/api/analytics/summary</a></p>
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
    socketio.run(app, host="0.0.0.0", port=5000, debug=False)