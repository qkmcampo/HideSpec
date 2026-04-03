"""
Leather Hide Inspection — API Server
Runs on Raspberry Pi 5 to serve inspection data to the mobile/web app.
Team 10 — TIP QC Capstone Project

Install requirements:
    pip install flask flask-cors flask-socketio --break-system-packages

Run: python3 api_server.py
API: http://0.0.0.0:5000
"""

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from flask_socketio import SocketIO
from db_manager import InspectionDB
import os
import json
from datetime import datetime, timedelta

app = Flask(__name__)

# Allow ALL origins — critical for mobile/web app connection
CORS(app, resources={r"/*": {"origins": "*"}})
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

db = InspectionDB()

# ─── System Status ──────────────────────────────────────────────
@app.route('/api/status', methods=['GET'])
def get_status():
    """Returns current system status for the mobile app."""
    stats = db.get_analytics()
    return jsonify({
        "status": "running",
        "timestamp": datetime.now().isoformat(),
        "system": {
            "model": "YOLOv8n",
            "platform": "Raspberry Pi 5",
            "camera": "Pi Camera Module 3",
            "arduino": "connected"
        },
        "session": {
            "total_inspected": stats["total_inspections"],
            "good_count": stats["good_count"],
            "bad_count": stats["bad_count"],
            "defect_rate": stats["defect_rate"]
        }
    })


# ─── Inspection Records ────────────────────────────────────────
@app.route('/api/inspections', methods=['GET'])
def get_inspections():
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    classification = request.args.get('classification', None)

    inspections = db.get_inspections(
        limit=limit,
        offset=offset,
        classification=classification
    )
    return jsonify({
        "count": len(inspections),
        "inspections": inspections
    })


@app.route('/api/inspections/<int:inspection_id>', methods=['GET'])
def get_inspection_detail(inspection_id):
    inspection = db.get_inspection(inspection_id)
    if inspection:
        return jsonify(inspection)
    return jsonify({"error": "Inspection not found"}), 404


@app.route('/api/inspections/latest', methods=['GET'])
def get_latest_inspection():
    inspections = db.get_inspections(limit=1)
    if inspections:
        return jsonify(inspections[0])
    return jsonify({"error": "No inspections yet"}), 404


# ─── Analytics ──────────────────────────────────────────────────
@app.route('/api/analytics', methods=['GET'])
def get_analytics():
    period = request.args.get('period', 'today')
    analytics = db.get_analytics(period=period)
    return jsonify(analytics)


@app.route('/api/analytics/defect-distribution', methods=['GET'])
def get_defect_distribution():
    distribution = db.get_defect_distribution()
    return jsonify({"defects": distribution})


@app.route('/api/analytics/timeline', methods=['GET'])
def get_timeline():
    period = request.args.get('period', 'today')
    timeline = db.get_timeline(period=period)
    return jsonify({"timeline": timeline})


# ─── Inspection Image ───────────────────────────────────────────
@app.route('/api/inspections/<int:inspection_id>/image', methods=['GET'])
def get_inspection_image(inspection_id):
    inspection = db.get_inspection(inspection_id)
    if inspection and inspection.get("image_path"):
        image_path = inspection["image_path"]
        if os.path.exists(image_path):
            return send_file(image_path, mimetype='image/jpeg')
    return jsonify({"error": "Image not found"}), 404


# ─── Health Check (for debugging) ──────────────────────────────
@app.route('/api/health', methods=['GET'])
def health_check():
    """Simple health check endpoint for debugging connection issues."""
    return jsonify({
        "status": "ok",
        "server": "api_server.py",
        "port": 5000,
        "timestamp": datetime.now().isoformat(),
    })


# ─── WebSocket Events ───────────────────────────────────────────
@socketio.on('connect')
def handle_connect():
    print("[WS] Mobile/web client connected")
    stats = db.get_analytics()
    socketio.emit('status_update', {
        "total_inspected": stats["total_inspections"],
        "good_count": stats["good_count"],
        "bad_count": stats["bad_count"]
    })


@socketio.on('disconnect')
def handle_disconnect():
    print("[WS] Mobile/web client disconnected")


def notify_new_inspection(inspection_data):
    """
    Call this from inference.py after each hide is processed.
    Pushes result to all connected mobile/web clients.
    """
    socketio.emit('new_inspection', inspection_data)
    stats = db.get_analytics()
    socketio.emit('status_update', {
        "total_inspected": stats["total_inspections"],
        "good_count": stats["good_count"],
        "bad_count": stats["bad_count"]
    })


# ─── Main ───────────────────────────────────────────────────────
if __name__ == '__main__':
    print()
    print("=" * 55)
    print("  HIDESPEC — DATA API SERVER")
    print("  Leather Hide Inspection System")
    print("  Team 10 · TIP QC")
    print("=" * 55)
    print()
    print("  API running at:     http://0.0.0.0:5000")
    print("  Health check:       http://0.0.0.0:5000/api/health")
    print("  System status:      http://0.0.0.0:5000/api/status")
    print("  Inspections:        http://0.0.0.0:5000/api/inspections")
    print("  Analytics:          http://0.0.0.0:5000/api/analytics")
    print()
    print("  Make sure your phone/browser is on the same WiFi.")
    print("=" * 55)
    print()

    socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)
