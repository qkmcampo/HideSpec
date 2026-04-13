from flask import Flask, Response, jsonify
from ultralytics import YOLO
from picamera2 import Picamera2
from db_manager import InspectionDB
import cv2
import time
import threading
import serial
import os
import requests
from datetime import datetime

app = Flask(__name__)

model = YOLO("best.pt")
db = InspectionDB()

# -----------------------------
# Config
# -----------------------------
API_TRIGGER_URL = "http://127.0.0.1:5000/api/trigger-update"
CAPTURES_DIR = os.path.join(os.path.dirname(__file__), "captures")
os.makedirs(CAPTURES_DIR, exist_ok=True)

CONF_THRESHOLD = 0.25
BAD_DEFECT_THRESHOLD = 3
REQUIRED_CONSECUTIVE_BAD_FRAMES = 3
MISSING_FRAMES_TO_RESET = 15

# -----------------------------
# Arduino setup
# -----------------------------
arduino = None
arduino_connected = False
ARDUINO_PORT = "/dev/ttyACM0"
ARDUINO_BAUDRATE = 9600

try:
    arduino = serial.Serial(ARDUINO_PORT, ARDUINO_BAUDRATE, timeout=1)
    time.sleep(2)
    arduino_connected = True
    print(f"Arduino connected on {ARDUINO_PORT}")
except Exception as e:
    print(f"Arduino not connected: {e}")

# -----------------------------
# Camera setup
# -----------------------------
picam2 = Picamera2()
config = picam2.create_video_configuration(
    main={"size": (416, 416), "format": "RGB888"}
)
picam2.configure(config)
picam2.start()
time.sleep(2)

# -----------------------------
# Detection state
# -----------------------------
state_lock = threading.Lock()

bad_triggered = False
servo_busy = False
consecutive_bad_frames = 0
missing_frames = 0
leather_present = False
max_defects_seen = 0
current_defect_count = 0
current_status = "WAITING FOR LEATHER"
last_result = None
last_command_sent = None
last_annotated = None
last_detections = []

# per-hide accumulated state
hide_counter = 0
active_hide_id = None
active_hide_detections = []
active_snapshot_path = None


def notify_api_server():
    try:
        requests.post(API_TRIGGER_URL, timeout=2)
    except Exception as e:
        print(f"Trigger update failed: {e}")


def trigger_bad_servo():
    global servo_busy, last_command_sent

    with state_lock:
        if servo_busy:
            return
        servo_busy = True
        last_command_sent = "B"

    try:
        print("BAD leather detected -> sending B to Arduino")
        if arduino_connected and arduino:
            arduino.write(b'B')
        else:
            print("Arduino not connected, B not sent")
        time.sleep(20)
    finally:
        with state_lock:
            servo_busy = False


def merge_detections(existing, new_items):
    """
    Keep the highest-confidence entry for roughly the same defect.
    Simple dedupe by type + nearby bbox center.
    """
    merged = list(existing)

    for item in new_items:
        matched_index = None
        ix = item.get("x", 0) + item.get("w", 0) / 2
        iy = item.get("y", 0) + item.get("h", 0) / 2

        for idx, old in enumerate(merged):
            if old.get("type") != item.get("type"):
                continue

            ox = old.get("x", 0) + old.get("w", 0) / 2
            oy = old.get("y", 0) + old.get("h", 0) / 2

            if abs(ix - ox) < 40 and abs(iy - oy) < 40:
                matched_index = idx
                break

        if matched_index is None:
            merged.append(item)
        else:
            if item.get("confidence", 0) > merged[matched_index].get("confidence", 0):
                merged[matched_index] = item

    return merged


def classify_hide(defects):
    """
    Match your project rule:
    Bad if 2 or more defects OR any hole/cut detected.
    """
    if len(defects) >= 2:
        return "Bad"

    for defect in defects:
        if defect.get("type") in ["hole", "cut"]:
            return "Bad"

    return "Good"


def save_completed_inspection(hide_id, defects, snapshot_path):
    classification = classify_hide(defects)

    inspection_id = db.save_inspection(
        hide_id=hide_id,
        classification=classification,
        defects=defects,
        total_defects=len(defects),
        image_path=snapshot_path,
        created_at=datetime.utcnow().isoformat(),
    )

    print(
        f"[SAVE] {hide_id} -> {classification} "
        f"({len(defects)} defects: "
        f"{', '.join(d['type'] for d in defects) if defects else 'none'})"
    )

    notify_api_server()
    return inspection_id, classification


def generate_frames():
    global bad_triggered, servo_busy, consecutive_bad_frames
    global missing_frames, leather_present, max_defects_seen
    global current_defect_count, current_status, last_result
    global last_annotated, last_detections
    global hide_counter, active_hide_id, active_hide_detections, active_snapshot_path

    frame_count = 0

    while True:
        frame = picam2.capture_array()
        frame_count += 1

        if frame_count % 2 == 0 or last_annotated is None:
            results = model(frame, imgsz=416, conf=CONF_THRESHOLD, verbose=False)
            result = results[0]

            defect_count = 0
            detections = []

            for box in result.boxes:
                conf = float(box.conf[0])
                if conf >= CONF_THRESHOLD:
                    defect_count += 1
                    cls_id = int(box.cls[0].item())
                    label = model.names.get(cls_id, str(cls_id))
                    x1, y1, x2, y2 = box.xyxy[0].tolist()

                    detections.append({
                        "type": label,
                        "label": label,
                        "confidence": round(conf, 2),
                        "x": int(x1),
                        "y": int(y1),
                        "w": int(x2 - x1),
                        "h": int(y2 - y1),
                    })

            current_defect_count = defect_count
            last_detections = detections
            last_annotated = result.plot()

            with state_lock:
                if defect_count > 0:
                    if not leather_present:
                        hide_counter += 1
                        active_hide_id = f"HIDE-{hide_counter:04d}"
                        active_hide_detections = []
                        active_snapshot_path = None
                        last_result = None
                        print(f"[START] New leather detected: {active_hide_id}")

                    leather_present = True
                    missing_frames = 0
                    max_defects_seen = max(max_defects_seen, defect_count)

                    active_hide_detections = merge_detections(active_hide_detections, detections)

                    if last_annotated is not None and active_hide_id is not None:
                        snapshot_path = os.path.join(CAPTURES_DIR, f"{active_hide_id}.jpg")
                        frame_bgr = cv2.cvtColor(last_annotated, cv2.COLOR_RGB2BGR)
                        cv2.imwrite(snapshot_path, frame_bgr)
                        active_snapshot_path = snapshot_path

                else:
                    if leather_present:
                        missing_frames += 1

                # Trigger Arduino only for BAD leather candidate
                if not bad_triggered and not servo_busy:
                    if defect_count >= BAD_DEFECT_THRESHOLD:
                        consecutive_bad_frames += 1
                    else:
                        consecutive_bad_frames = 0

                    if consecutive_bad_frames >= REQUIRED_CONSECUTIVE_BAD_FRAMES:
                        bad_triggered = True
                        threading.Thread(target=trigger_bad_servo, daemon=True).start()

                # Finalize inspection when leather disappears
                if leather_present and missing_frames >= MISSING_FRAMES_TO_RESET:
                    print(f"[END] Leather finished. Max defects seen: {max_defects_seen}")

                    final_defects = list(active_hide_detections)
                    final_classification = classify_hide(final_defects)

                    if active_hide_id is not None:
                        save_completed_inspection(
                            hide_id=active_hide_id,
                            defects=final_defects,
                            snapshot_path=active_snapshot_path,
                        )

                    last_result = final_classification.upper()

                    bad_triggered = False
                    consecutive_bad_frames = 0
                    missing_frames = 0
                    leather_present = False
                    max_defects_seen = 0
                    current_defect_count = 0
                    active_hide_id = None
                    active_hide_detections = []
                    active_snapshot_path = None

                if servo_busy:
                    current_status = "BAD DETECTED | Servo active"
                elif leather_present:
                    current_status = (
                        f"INSPECTING | defects={current_defect_count} | max={max_defects_seen}"
                    )
                else:
                    current_status = "WAITING FOR LEATHER"

        display_frame = last_annotated.copy() if last_annotated is not None else frame.copy()
        display_frame = cv2.cvtColor(display_frame, cv2.COLOR_RGB2BGR)

        success, buffer = cv2.imencode(
            ".jpg",
            display_frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), 70]
        )
        if not success:
            continue

        yield (
            b'--frame\r\n'
            b'Content-Type: image/jpeg\r\n'
            b'Cache-Control: no-cache, no-store, must-revalidate\r\n'
            b'Pragma: no-cache\r\n'
            b'Expires: 0\r\n\r\n' + buffer.tobytes() + b'\r\n'
        )


@app.route("/video_feed")
def video_feed():
    response = Response(
        generate_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.route("/api/stream/status")
def stream_status():
    with state_lock:
        return jsonify({
            "status": "running",
            "machine": {
                "arduino_connected": arduino_connected,
                "leather_present": leather_present,
                "servo_busy": servo_busy,
                "bad_triggered": bad_triggered,
                "consecutive_bad_frames": consecutive_bad_frames,
                "missing_frames": missing_frames,
                "max_defects_seen": max_defects_seen,
                "current_defect_count": current_defect_count,
                "current_result": current_status,
                "last_command_sent": last_command_sent,
                "last_result": last_result,
                "active_hide_id": active_hide_id,
            },
            "detections": last_detections,
        })


@app.route("/api/stream/snapshot")
def snapshot():
    if last_annotated is None:
        return ("No snapshot available", 404)

    frame_bgr = cv2.cvtColor(last_annotated, cv2.COLOR_RGB2BGR)
    success, buffer = cv2.imencode(
        ".jpg",
        frame_bgr,
        [int(cv2.IMWRITE_JPEG_QUALITY), 80]
    )
    if not success:
        return ("Snapshot encode failed", 500)

    return Response(buffer.tobytes(), mimetype="image/jpeg")


@app.route("/")
def index():
    return """
    <html>
      <body style="text-align:center;font-family:Arial">
        <h1>Leather Defect Detection Live Feed</h1>
        <img src="/video_feed" width="720">
      </body>
    </html>
    """


if __name__ == "__main__":
    try:
        print("Video stream: http://0.0.0.0:5001/video_feed")
        print("Stream status: http://0.0.0.0:5001/api/stream/status")
        print("Snapshot: http://0.0.0.0:5001/api/stream/snapshot")
        app.run(host="0.0.0.0", port=5001, threaded=True)
    finally:
        try:
            picam2.stop()
        except Exception:
            pass

        if arduino:
            arduino.close()