"""
Leather Hide Inspection — API Server
Runs on Raspberry Pi 5 to serve inspection data to the mobile app.
Team 10 — TIP QC Capstone Project
"""

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from flask_socketio import SocketIO
from db_manager import InspectionDB
import os
import json
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

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
            "camera": "connected",
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
    """
    Returns inspection history.
    Query params:
      - limit (int): number of records (default 50)
      - offset (int): pagination offset (default 0)
      - classification (str): filter by 'Good' or 'Bad'
    """
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
    """Returns detailed info for a single inspection."""
    inspection = db.get_inspection(inspection_id)
    if inspection:
        return jsonify(inspection)
    return jsonify({"error": "Inspection not found"}), 404


@app.route('/api/inspections/latest', methods=['GET'])
def get_latest_inspection():
    """Returns the most recent inspection result."""
    inspections = db.get_inspections(limit=1)
    if inspections:
        return jsonify(inspections[0])
    return jsonify({"error": "No inspections yet"}), 404


# ─── Analytics ──────────────────────────────────────────────────
@app.route('/api/analytics', methods=['GET'])
def get_analytics():
    """
    Returns aggregated analytics data.
    Query params:
      - period (str): 'today', 'week', 'month', 'all' (default 'today')
    """
    period = request.args.get('period', 'today')
    analytics = db.get_analytics(period=period)
    return jsonify(analytics)


@app.route('/api/analytics/defect-distribution', methods=['GET'])
def get_defect_distribution():
    """Returns count of each defect type."""
    distribution = db.get_defect_distribution()
    return jsonify({"defects": distribution})


@app.route('/api/analytics/timeline', methods=['GET'])
def get_timeline():
    """
    Returns inspection counts over time for charting.
    Query params:
      - period (str): 'today' (hourly), 'week' (daily), 'month' (daily)
    """
    period = request.args.get('period', 'today')
    timeline = db.get_timeline(period=period)
    return jsonify({"timeline": timeline})


# ─── Inspection Image ───────────────────────────────────────────
@app.route('/api/inspections/<int:inspection_id>/image', methods=['GET'])
def get_inspection_image(inspection_id):
    """Serves the captured image for a specific inspection."""
    inspection = db.get_inspection(inspection_id)
    if inspection and inspection.get("image_path"):
        image_path = inspection["image_path"]
        if os.path.exists(image_path):
            return send_file(image_path, mimetype='image/jpeg')
    return jsonify({"error": "Image not found"}), 404


# ─── WebSocket Events ───────────────────────────────────────────
@socketio.on('connect')
def handle_connect():
    print("[WS] Mobile client connected")
    # Send current status on connect
    stats = db.get_analytics()
    socketio.emit('status_update', {
        "total_inspected": stats["total_inspections"],
        "good_count": stats["good_count"],
        "bad_count": stats["bad_count"]
    })


@socketio.on('disconnect')
def handle_disconnect():
    print("[WS] Mobile client disconnected")


def notify_new_inspection(inspection_data):
    """
    Call this from your main inspection pipeline after each hide is processed.
    It pushes the result to all connected mobile clients in real-time.
    """
    socketio.emit('new_inspection', inspection_data)
    # Also send updated stats
    stats = db.get_analytics()
    socketio.emit('status_update', {
        "total_inspected": stats["total_inspections"],
        "good_count": stats["good_count"],
        "bad_count": stats["bad_count"]
    })


# ─── Main ───────────────────────────────────────────────────────
if __name__ == '__main__':
    print("=" * 50)
    print("Leather Inspection API Server")
    print("Team 10 — TIP QC Capstone")
    print("=" * 50)
    print("Starting on http://0.0.0.0:5000")
    print("Make sure your phone is on the same WiFi network.")
    print()

    # Run with WebSocket support
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)
