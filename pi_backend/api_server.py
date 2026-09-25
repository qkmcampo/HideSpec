from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from pathlib import Path
import os
from db_manager import InspectionDB

app = Flask(__name__)
app.config["SECRET_KEY"] = "hidespec-secret-key"

CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "hidespec.db"
CAPTURES_DIR = BASE_DIR / "captures"
API_PORT = int(os.getenv("HIDESPEC_API_PORT", "5001"))
STREAM_PORT = int(os.getenv("HIDESPEC_STREAM_PORT", "5000"))

CAPTURES_DIR.mkdir(parents=True, exist_ok=True)


inspection_db = InspectionDB(str(DB_PATH))


def init_db():
    """Ensure the shared SQLite database schema exists."""
    inspection_db._init_db()


def get_session_summary():
    analytics = inspection_db.get_analytics("all")
    return {
        "total_inspected": analytics["total_inspections"],
        "good_count": analytics["good_count"],
        "bad_count": analytics["bad_count"],
        "defect_rate": analytics["defect_rate"],
    }


def get_defect_type_summary():
    return {
        defect["type"]: defect["count"]
        for defect in inspection_db.get_defect_distribution("all")
    }


def get_analytics_summary(period="today"):
    return inspection_db.get_analytics(period)


def get_defect_distribution(period="today"):
    return {
        "period": period,
        "defects": inspection_db.get_defect_distribution(period),
    }


def get_quality_distribution(period="today"):
    return inspection_db.get_quality_distribution(period)


def get_defect_area_distribution(period="today"):
    return inspection_db.get_defect_area_distribution(period)


def get_timeline_data(period="today"):
    return {
        "period": period,
        "timeline": inspection_db.get_timeline(period),
    }


def emit_realtime_updates():
    inspections = inspection_db.get_inspections(limit=1)
    if inspections:
        socketio.emit("new_inspection", inspections[0])

    socketio.emit("status_update", get_session_summary())


def create_inspection_record(
    hide_id,
    defects,
    classification=None,
    snapshot_path=None,
    created_at=None,
    defect_area_percent=0,
    leather_area=0,
    defect_area=0,
    machine_status=None,
):
    total_defects = len(defects)
    classification = classification if classification in ("Good", "Bad") else (
        "Bad" if float(defect_area_percent or 0) >= 20 else "Good"
    )
    inspection_id = inspection_db.save_inspection(
        hide_id=hide_id,
        classification=classification,
        defects=defects,
        total_defects=total_defects,
        defect_area_percent=defect_area_percent,
        leather_area=leather_area,
        defect_area=defect_area,
        image_path=snapshot_path,
        machine_status=machine_status,
        created_at=created_at,
    )
    inspection = inspection_db.get_inspection(inspection_id)

    socketio.emit("new_inspection", inspection)
    socketio.emit("status_update", get_session_summary())
    return inspection


def reset_history(delete_captures=False):
    inspection_db.clear_all()
    deleted_files = []

    if delete_captures:
        for file_path in CAPTURES_DIR.glob("*.jpg"):
            try:
                file_path.unlink()
                deleted_files.append(file_path.name)
            except OSError as error:
                print(f"Failed to delete {file_path}: {error}")

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
        "ports": {
            "api": API_PORT,
            "stream": STREAM_PORT,
        },
        "session": get_session_summary(),
        "analytics": {
            "defects_by_type": get_defect_type_summary()
        }
    })


@app.route("/api/stream/status", methods=["GET"])
def stream_status():
    return jsonify({
        "status": "running",
        "streaming": True,
        "camera_connected": True,
        "source": "app5.py",
        "port": STREAM_PORT,
        "video_feed": f"http://0.0.0.0:{STREAM_PORT}/video_feed",
    })


@app.route("/api/inspections/latest", methods=["GET"])
def latest_inspection():
    inspections = inspection_db.get_inspections(limit=1)
    if not inspections:
        return jsonify(None)

    return jsonify(inspections[0])

@app.route("/api/inspections", methods=["GET"])
def get_inspections():
    limit = request.args.get("limit", default=20, type=int)
    limit = max(1, min(limit, 100))
    inspections = inspection_db.get_inspections(limit=limit)

    return jsonify({
        "count": len(inspections),
        "inspections": inspections,
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


@app.route("/api/analytics/quality", methods=["GET"])
def analytics_quality():
    period = request.args.get("period", default="today", type=str)
    return jsonify(get_quality_distribution(period))


@app.route("/api/analytics/defect-area", methods=["GET"])
def analytics_defect_area():
    period = request.args.get("period", default="today", type=str)
    return jsonify(get_defect_area_distribution(period))


@app.route("/api/config", methods=["GET"])
def api_config():
    return jsonify({
        "api_port": API_PORT,
        "stream_port": STREAM_PORT,
        "database": str(DB_PATH),
        "captures_dir": str(CAPTURES_DIR),
    })


@app.route("/captures/<path:filename>", methods=["GET"])
def captured_image(filename):
    return send_from_directory(CAPTURES_DIR, filename)


@app.route("/api/inspections", methods=["POST"])
def create_inspection():
    data = request.get_json(silent=True) or {}

    hide_id = data.get("hide_id")
    defects = data.get("defects", [])
    snapshot_path = data.get("snapshot_path")
    created_at = data.get("created_at")
    defect_area_percent = data.get("defect_area_percent", 0)
    leather_area = data.get("leather_area", 0)
    defect_area = data.get("defect_area", 0)
    classification = data.get("classification")
    machine_status = data.get("machine_status")

    if not hide_id:
        return jsonify({"error": "hide_id is required"}), 400

    if not isinstance(defects, list):
        return jsonify({"error": "defects must be a list"}), 400

    inspection = create_inspection_record(
        hide_id=hide_id,
        defects=defects,
        classification=classification,
        snapshot_path=snapshot_path,
        created_at=created_at,
        defect_area_percent=defect_area_percent,
        leather_area=leather_area,
        defect_area=defect_area,
        machine_status=machine_status,
    )

    return jsonify(inspection), 201


@app.route("/api/trigger-update", methods=["POST"])
def trigger_update():
    emit_realtime_updates()
    return jsonify({"status": "ok"})


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
        <p><a href="/api/stream/status" style="color:#4da3ff;">/api/stream/status</a></p>
        <p><a href="/api/inspections/latest" style="color:#4da3ff;">/api/inspections/latest</a></p>
        <p><a href="/api/inspections" style="color:#4da3ff;">/api/inspections</a></p>
        <p><a href="/api/analytics/summary" style="color:#4da3ff;">/api/analytics/summary</a></p>
        <p><a href="/api/analytics?period=today" style="color:#4da3ff;">/api/analytics?period=today</a></p>
        <p><a href="/api/analytics/defects?period=today" style="color:#4da3ff;">/api/analytics/defects?period=today</a></p>
        <p><a href="/api/analytics/timeline?period=today" style="color:#4da3ff;">/api/analytics/timeline?period=today</a></p>
        <p><a href="/api/trigger-update" style="color:#4da3ff;">/api/trigger-update</a></p>

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
    print(f"API status: http://0.0.0.0:{API_PORT}/api/status")
    print(f"Stream status: http://0.0.0.0:{API_PORT}/api/stream/status")
    print(f"Latest inspection: http://0.0.0.0:{API_PORT}/api/inspections/latest")
    print(f"Inspection history: http://0.0.0.0:{API_PORT}/api/inspections")
    print(f"Analytics summary: http://0.0.0.0:{API_PORT}/api/analytics/summary")
    print(f"Analytics overview: http://0.0.0.0:{API_PORT}/api/analytics?period=today")
    print(f"Analytics defects: http://0.0.0.0:{API_PORT}/api/analytics/defects?period=today")
    print(f"Analytics timeline: http://0.0.0.0:{API_PORT}/api/analytics/timeline?period=today")
    print(f"Trigger update: http://0.0.0.0:{API_PORT}/api/trigger-update")
    print(f"Reset history: http://0.0.0.0:{API_PORT}/api/history/reset")

    socketio.run(app, host="0.0.0.0", port=5001, debug=False)


