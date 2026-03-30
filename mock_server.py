"""
Mock Inspection Server
Simulates the Raspberry Pi 5 API so you can test the mobile app
WITHOUT any hardware. Run this on your computer.

Usage:
    pip install flask flask-cors flask-socketio
    python mock_server.py
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO
import random
import time
import threading
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

DEFECT_TYPES = ['color_defect', 'hole', 'fold']
inspection_counter = 0
inspections_db = []


def generate_fake_inspection():
    global inspection_counter
    inspection_counter += 1

    num_defects = random.choices(
        [0, 1, 2, 3, 4],
        weights=[50, 25, 15, 7, 3],
        k=1
    )[0]

    defects = []
    for _ in range(num_defects):
        defect_type = random.choice(DEFECT_TYPES)
        defects.append({
            "type": defect_type,
            "confidence": round(random.uniform(0.72, 0.98), 2),
            "x": random.randint(50, 500),
            "y": random.randint(50, 400),
            "w": random.randint(20, 120),
            "h": random.randint(20, 100),
        })

    has_hole = any(d['type'] == 'hole' for d in defects)
    classification = 'Bad' if (num_defects >= 2 or has_hole) else 'Good'

    inspection = {
        "id": inspection_counter,
        "hide_id": f"HIDE-{inspection_counter:04d}",
        "classification": classification,
        "total_defects": num_defects,
        "defects": defects,
        "image_path": None,
        "created_at": datetime.now().isoformat(),
    }

    inspections_db.insert(0, inspection)
    return inspection


def generate_initial_data():
    global inspections_db, inspection_counter

    for i in range(30):
        inspection_counter += 1
        hours_ago = random.randint(1, 168)
        timestamp = datetime.now() - timedelta(hours=hours_ago)

        num_defects = random.choices([0, 1, 2, 3], weights=[50, 25, 15, 10], k=1)[0]
        defects = []
        for _ in range(num_defects):
            defects.append({
                "type": random.choice(DEFECT_TYPES),
                "confidence": round(random.uniform(0.72, 0.98), 2),
                "x": random.randint(50, 500),
                "y": random.randint(50, 400),
                "w": random.randint(20, 120),
                "h": random.randint(20, 100),
            })

        has_hole = any(d['type'] == 'hole' for d in defects)
        classification = 'Bad' if (num_defects >= 2 or has_hole) else 'Good'

        inspections_db.append({
            "id": inspection_counter,
            "hide_id": f"HIDE-{inspection_counter:04d}",
            "classification": classification,
            "total_defects": num_defects,
            "defects": defects,
            "image_path": None,
            "created_at": timestamp.isoformat(),
        })

    inspections_db.sort(key=lambda x: x['created_at'], reverse=True)
    print(f"Generated {len(inspections_db)} historical inspections")


def auto_simulate():
    while True:
        time.sleep(15)
        inspection = generate_fake_inspection()
        print(f"[SIM] New inspection: {inspection['hide_id']} -> {inspection['classification']} "
              f"({inspection['total_defects']} defects)")

        socketio.emit('new_inspection', inspection)

        stats = compute_analytics('today')
        socketio.emit('status_update', {
            "total_inspected": stats["total_inspections"],
            "good_count": stats["good_count"],
            "bad_count": stats["bad_count"],
        })


def compute_analytics(period='today'):
    now = datetime.now()
    if period == 'today':
        cutoff = now.replace(hour=0, minute=0, second=0)
    elif period == 'week':
        cutoff = now - timedelta(days=7)
    elif period == 'month':
        cutoff = now - timedelta(days=30)
    else:
        cutoff = datetime(2000, 1, 1)

    filtered = [i for i in inspections_db
                if datetime.fromisoformat(i['created_at']) >= cutoff]

    total = len(filtered)
    good = sum(1 for i in filtered if i['classification'] == 'Good')
    bad = total - good
    avg_defects = (sum(i['total_defects'] for i in filtered) / total) if total > 0 else 0

    return {
        "total_inspections": total,
        "good_count": good,
        "bad_count": bad,
        "pass_rate": round((good / total * 100), 1) if total > 0 else 0,
        "defect_rate": round((bad / total * 100), 1) if total > 0 else 0,
        "avg_defects_per_hide": round(avg_defects, 2),
        "period": period,
    }


@app.route('/api/status', methods=['GET'])
def get_status():
    stats = compute_analytics('today')
    return jsonify({
        "status": "running",
        "timestamp": datetime.now().isoformat(),
        "system": {
            "model": "YOLOv8n",
            "platform": "Mock Server (simulating Raspberry Pi 5)",
            "camera": "simulated",
            "arduino": "simulated"
        },
        "session": {
            "total_inspected": stats["total_inspections"],
            "good_count": stats["good_count"],
            "bad_count": stats["bad_count"],
            "defect_rate": stats["defect_rate"]
        }
    })


@app.route('/api/inspections', methods=['GET'])
def get_inspections():
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    classification = request.args.get('classification', None)

    filtered = inspections_db
    if classification:
        filtered = [i for i in filtered if i['classification'] == classification]

    page = filtered[offset:offset + limit]
    return jsonify({"count": len(page), "inspections": page})


@app.route('/api/inspections/latest', methods=['GET'])
def get_latest():
    if inspections_db:
        return jsonify(inspections_db[0])
    return jsonify({"error": "No inspections yet"}), 404


@app.route('/api/analytics', methods=['GET'])
def get_analytics():
    period = request.args.get('period', 'today')
    return jsonify(compute_analytics(period))


@app.route('/api/analytics/defect-distribution', methods=['GET'])
def get_defect_distribution():
    counts = {}
    for inspection in inspections_db:
        for defect in inspection['defects']:
            t = defect['type']
            counts[t] = counts.get(t, 0) + 1

    distribution = [{"type": k, "count": v} for k, v in
                    sorted(counts.items(), key=lambda x: x[1], reverse=True)]
    return jsonify({"defects": distribution})


@app.route('/api/analytics/timeline', methods=['GET'])
def get_timeline():
    period = request.args.get('period', 'today')
    now = datetime.now()

    if period == 'today':
        cutoff = now.replace(hour=0, minute=0, second=0)
        fmt = '%H:00'
    else:
        days = 7 if period == 'week' else 30
        cutoff = now - timedelta(days=days)
        fmt = '%m/%d'

    filtered = [i for i in inspections_db
                if datetime.fromisoformat(i['created_at']) >= cutoff]

    buckets = {}
    for i in filtered:
        label = datetime.fromisoformat(i['created_at']).strftime(fmt)
        if label not in buckets:
            buckets[label] = {"time_label": label, "total": 0, "good": 0, "bad": 0}
        buckets[label]["total"] += 1
        if i['classification'] == 'Good':
            buckets[label]["good"] += 1
        else:
            buckets[label]["bad"] += 1

    timeline = sorted(buckets.values(), key=lambda x: x['time_label'])
    return jsonify({"timeline": timeline})


@socketio.on('connect')
def handle_connect():
    print("[WS] Mobile client connected")
    stats = compute_analytics('today')
    socketio.emit('status_update', {
        "total_inspected": stats["total_inspections"],
        "good_count": stats["good_count"],
        "bad_count": stats["bad_count"],
    })


@socketio.on('disconnect')
def handle_disconnect():
    print("[WS] Mobile client disconnected")


if __name__ == '__main__':
    generate_initial_data()

    sim_thread = threading.Thread(target=auto_simulate, daemon=True)
    sim_thread.start()

    print()
    print("=" * 55)
    print("  MOCK INSPECTION SERVER")
    print("  Simulating Raspberry Pi 5 for mobile app testing")
    print("=" * 55)
    print()
    print("  Server running at: http://0.0.0.0:5000")
    print()
    print("  A new fake inspection generates every 15 seconds.")
    print("=" * 55)
    print()

    socketio.run(app, host='0.0.0.0', port=5000, debug=False)