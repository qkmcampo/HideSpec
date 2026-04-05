from flask import Flask, Response, jsonify
from ultralytics import YOLO
from picamera2 import Picamera2
import cv2
import time
import threading
import requests
import serial
from pathlib import Path
from datetime import datetime

app = Flask(__name__)

print("=" * 60)
print("HIDESPEC - STREAM + MACHINE CONTROL")
print("YOLOv8n Detection with Pi Camera Module 3 + Arduino")
print("=" * 60)

# ============================================
# LOW-LAG STREAM SETTINGS
# ============================================
FRAME_WIDTH = 640
FRAME_HEIGHT = 480

YOLO_IMGSZ = 224
YOLO_CONF = 0.25
DETECT_EVERY_N_FRAMES = 5

JPEG_QUALITY = 50
TARGET_FPS = 8
FRAME_DELAY = 1.0 / TARGET_FPS

# ============================================
# API SETTINGS
# ============================================
API_BASE_URL = "http://127.0.0.1:5000"
INSPECTIONS_API_URL = f"{API_BASE_URL}/api/inspections"

# ============================================
# ARDUINO SETTINGS
# ============================================
ARDUINO_PORT = "/dev/ttyACM0"
ARDUINO_BAUDRATE = 9600
SERVO_HOLD_SECONDS = 2.0

# ============================================
# INSPECTION / MACHINE SETTINGS
# ============================================
VALID_DEFECT_CLASSES = {"color_defect", "hole", "fold"}

CONF_THRESHOLD = 0.25
BAD_DEFECT_THRESHOLD = 3
REQUIRED_CONSECUTIVE_BAD_FRAMES = 3
MISSING_FRAMES_TO_RESET = 15

SAVE_CAPTURE_IMAGE = True

BASE_DIR = Path(__file__).resolve().parent
CAPTURES_DIR = BASE_DIR / "captures"
CAPTURES_DIR.mkdir(parents=True, exist_ok=True)

print("\nLoading YOLO model...")
model = YOLO("best.pt")
print("Model loaded: best.pt")
print(f"Classes: {model.names}")

# Arduino
arduino = None
arduino_connected = False
try:
    arduino = serial.Serial(ARDUINO_PORT, ARDUINO_BAUDRATE, timeout=1)
    time.sleep(2)
    arduino_connected = True
    print(f"Arduino connected on {ARDUINO_PORT}")
except Exception as e:
    print(f"Arduino not connected: {e}")

print("Starting camera...")
picam2 = Picamera2()
config = picam2.create_video_configuration(
    main={"size": (FRAME_WIDTH, FRAME_HEIGHT), "format": "RGB888"},
    buffer_count=2
)
picam2.configure(config)
picam2.start()
time.sleep(2)
print(f"Camera started: {FRAME_WIDTH}x{FRAME_HEIGHT}")
print("Capture loop started.\n")

# Stream state
last_raw_frame = None
last_annotated = None
last_detections = []
frame_counter = 0

last_inference_ms = 0.0
last_encode_ms = 0.0
stream_fps = 0.0
last_stream_time = time.time()

# Machine state
servo_busy = False
bad_triggered = False
consecutive_bad_frames = 0
missing_frames = 0
leather_present = False
max_defects_seen = 0
current_defect_count = 0
current_result = "SCANNING"
last_command_sent = None
last_result = None
last_result_time = None

# Inspection state
inspection_active = False
current_hide_id = None
current_event_detections = {}
current_event_best_frame = None
current_event_best_score = 0.0

state_lock = threading.Lock()


def make_hide_id():
    return f"HIDE-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}"


def filter_target_detections(detections, min_conf=0.0):
    valid = []
    for d in detections:
        if d["type"] in VALID_DEFECT_CLASSES and d["confidence"] >= min_conf:
            valid.append(d)
    return valid


def merge_event_detections(existing_map, detections):
    for d in detections:
        defect_type = d["type"]
        if defect_type not in existing_map:
            existing_map[defect_type] = d
        elif d["confidence"] > existing_map[defect_type]["confidence"]:
            existing_map[defect_type] = d


def save_capture_image(frame_rgb, hide_id):
    frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
    filename = f"{hide_id}.jpg"
    file_path = CAPTURES_DIR / filename
    ok = cv2.imwrite(str(file_path), frame_bgr)
    return str(file_path) if ok else None


def send_inspection_to_api(hide_id, defects, snapshot_path=None):
    payload = {
        "hide_id": hide_id,
        "defects": defects,
        "snapshot_path": snapshot_path,
    }

    try:
        response = requests.post(INSPECTIONS_API_URL, json=payload, timeout=3)
        if response.ok:
            total_defects = len(defects)
            classification = "Good" if total_defects == 0 else "Bad"
            print(f"[INSPECTION] Saved {hide_id} -> {classification} ({total_defects} defects)")
        else:
            print(f"[INSPECTION] API failed: {response.status_code} {response.text}")
    except Exception as e:
        print(f"[INSPECTION] POST error: {e}")


def send_command_to_arduino(command):
    global servo_busy, last_command_sent, last_result_time

    with state_lock:
        if servo_busy:
            return False
        servo_busy = True
        last_command_sent = command
        last_result_time = datetime.utcnow().isoformat()

    try:
        if arduino_connected and arduino:
            print(f"[ARDUINO] Sending command: {command}")
            arduino.write(command.encode("utf-8"))
            time.sleep(SERVO_HOLD_SECONDS)
        else:
            print(f"[ARDUINO] Simulated command: {command}")
            time.sleep(1.0)
        return True
    except Exception as e:
        print(f"[ARDUINO] Command error: {e}")
        return False
    finally:
        with state_lock:
            servo_busy = False


def trigger_result(command):
    threading.Thread(target=send_command_to_arduino, args=(command,), daemon=True).start()


def start_inspection_event(frame_rgb, detections):
    global inspection_active, current_hide_id
    global current_event_detections, current_event_best_frame, current_event_best_score

    if inspection_active:
        return

    inspection_active = True
    current_hide_id = make_hide_id()
    current_event_detections = {}
    current_event_best_frame = frame_rgb.copy()
    current_event_best_score = max((d["confidence"] for d in detections), default=0.0)

    if detections:
        merge_event_detections(current_event_detections, detections)

    print(f"[INSPECTION] Started {current_hide_id}")


def finalize_inspection_event(final_result):
    global inspection_active, current_hide_id
    global current_event_detections, current_event_best_frame, current_event_best_score
    global last_result, last_result_time

    if not inspection_active or not current_hide_id:
        return

    defects = list(current_event_detections.values())
    snapshot_path = None

    if SAVE_CAPTURE_IMAGE and current_event_best_frame is not None:
        snapshot_path = save_capture_image(current_event_best_frame, current_hide_id)

    send_inspection_to_api(
        hide_id=current_hide_id,
        defects=defects,
        snapshot_path=snapshot_path
    )

    last_result = final_result
    last_result_time = datetime.utcnow().isoformat()

    print(f"[INSPECTION] Finalized {current_hide_id} -> {final_result} ({len(defects)} defects)")

    inspection_active = False
    current_hide_id = None
    current_event_detections = {}
    current_event_best_frame = None
    current_event_best_score = 0.0


def run_detection(frame):
    global last_detections, last_inference_ms

    start = time.time()
    results = model(frame, imgsz=YOLO_IMGSZ, conf=YOLO_CONF, verbose=False)
    last_inference_ms = round((time.time() - start) * 1000, 1)

    result = results[0]
    annotated = result.plot()

    detections = []
    boxes = result.boxes
    if boxes is not None:
        for box in boxes:
            cls_id = int(box.cls[0].item())
            conf = float(box.conf[0].item())
            label = model.names.get(cls_id, str(cls_id))
            if label in VALID_DEFECT_CLASSES:
                detections.append({
                    "type": label,
                    "label": label,
                    "confidence": conf,
                })

    last_detections = detections
    return annotated, detections


def update_machine_state(frame_rgb, detections):
    global bad_triggered, consecutive_bad_frames, missing_frames
    global leather_present, max_defects_seen, current_defect_count, current_result

    valid_detections = filter_target_detections(detections, CONF_THRESHOLD)
    defect_count = len(valid_detections)
    current_defect_count = defect_count

    if defect_count > 0:
        if not leather_present:
            start_inspection_event(frame_rgb, valid_detections)

        leather_present = True
        missing_frames = 0
        max_defects_seen = max(max_defects_seen, defect_count)

        if inspection_active:
            merge_event_detections(current_event_detections, valid_detections)
            best_conf = max((d["confidence"] for d in valid_detections), default=0.0)
            if best_conf > current_event_best_score:
                globals()["current_event_best_score"] = best_conf
                globals()["current_event_best_frame"] = frame_rgb.copy()

        if not bad_triggered and not servo_busy:
            if defect_count >= BAD_DEFECT_THRESHOLD:
                consecutive_bad_frames += 1
            else:
                consecutive_bad_frames = 0

            if consecutive_bad_frames >= REQUIRED_CONSECUTIVE_BAD_FRAMES:
                bad_triggered = True
                current_result = "BAD"
        else:
            current_result = "BAD" if bad_triggered else "INSPECTING"

    else:
        if leather_present:
            missing_frames += 1

        if leather_present and missing_frames >= MISSING_FRAMES_TO_RESET:
            final_result = "BAD" if bad_triggered else "GOOD"
            current_result = final_result

            if final_result == "BAD":
                trigger_result("B")
            else:
                trigger_result("G")

            finalize_inspection_event(final_result)

            print(f"[MACHINE] Leather finished. Result: {final_result}")

            bad_triggered = False
            consecutive_bad_frames = 0
            missing_frames = 0
            leather_present = False
            max_defects_seen = 0
            current_defect_count = 0
            current_result = "SCANNING"
        elif not leather_present:
            current_result = "SCANNING"


def mjpeg_generator():
    global last_raw_frame, last_annotated, frame_counter
    global last_encode_ms, stream_fps, last_stream_time

    while True:
        loop_start = time.time()

        try:
            frame = picam2.capture_array()

            with state_lock:
                last_raw_frame = frame.copy()
                frame_counter += 1
                current_frame_number = frame_counter

            if last_annotated is None or current_frame_number % DETECT_EVERY_N_FRAMES == 0:
                annotated, detections = run_detection(frame)

                with state_lock:
                    update_machine_state(frame, detections)
                    last_annotated = annotated
            else:
                with state_lock:
                    if last_annotated is None:
                        last_annotated = frame.copy()

            with state_lock:
                frame_to_send = last_annotated.copy()
                status_text = (
                    "BAD DETECTED | Servo active" if servo_busy else
                    f"INSPECTING | defects={current_defect_count} | max={max_defects_seen}" if leather_present else
                    "SCANNING..."
                )

            frame_bgr = cv2.cvtColor(frame_to_send, cv2.COLOR_RGB2BGR)
            cv2.putText(
                frame_bgr,
                status_text,
                (20, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 0, 0),
                2
            )

            encode_start = time.time()
            ok, buffer = cv2.imencode(
                ".jpg",
                frame_bgr,
                [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY]
            )
            last_encode_ms = round((time.time() - encode_start) * 1000, 1)

            if not ok:
                continue

            now = time.time()
            elapsed = now - last_stream_time
            if elapsed > 0:
                stream_fps = round(1.0 / elapsed, 1)
            last_stream_time = now

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Cache-Control: no-cache, no-store, must-revalidate\r\n"
                b"Pragma: no-cache\r\n"
                b"Expires: 0\r\n\r\n" + buffer.tobytes() + b"\r\n"
            )

            loop_elapsed = time.time() - loop_start
            sleep_time = FRAME_DELAY - loop_elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        except GeneratorExit:
            break
        except Exception as e:
            print(f"Stream error: {e}")
            time.sleep(0.05)


@app.route("/video_feed")
def video_feed():
    response = Response(
        mjpeg_generator(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers["X-Accel-Buffering"] = "no"
    return response


@app.route("/api/stream/status")
def stream_status():
    with state_lock:
        return jsonify({
            "status": "running",
            "resolution": f"{FRAME_WIDTH}x{FRAME_HEIGHT}",
            "detections": list(last_detections),
            "inspection_event": {
                "active": inspection_active,
                "current_hide_id": current_hide_id,
                "collected_defects": list(current_event_detections.values()),
            },
            "machine": {
                "arduino_connected": arduino_connected,
                "leather_present": leather_present,
                "servo_busy": servo_busy,
                "bad_triggered": bad_triggered,
                "consecutive_bad_frames": consecutive_bad_frames,
                "missing_frames": missing_frames,
                "max_defects_seen": max_defects_seen,
                "current_defect_count": current_defect_count,
                "current_result": current_result,
                "last_command_sent": last_command_sent,
                "last_result": last_result,
                "last_result_time": last_result_time,
            },
            "performance": {
                "detect_every_n_frames": DETECT_EVERY_N_FRAMES,
                "imgsz": YOLO_IMGSZ,
                "jpeg_quality": JPEG_QUALITY,
                "target_fps": TARGET_FPS,
                "actual_stream_fps": stream_fps,
                "last_inference_ms": last_inference_ms,
                "last_encode_ms": last_encode_ms,
            }
        })


@app.route("/api/stream/snapshot")
def snapshot():
    try:
        with state_lock:
            frame = last_raw_frame.copy() if last_raw_frame is not None else None

        if frame is None:
            frame = picam2.capture_array()

        annotated, _ = run_detection(frame)
        frame_bgr = cv2.cvtColor(annotated, cv2.COLOR_RGB2BGR)

        ok, buffer = cv2.imencode(
            ".jpg",
            frame_bgr,
            [int(cv2.IMWRITE_JPEG_QUALITY), 70]
        )
        if not ok:
            return ("Snapshot encode failed", 500)

        return Response(buffer.tobytes(), mimetype="image/jpeg")

    except Exception as e:
        return (f"Snapshot failed: {e}", 500)


@app.route("/")
def home():
    return f"""
    <html>
      <body style="text-align:center;background:#111;color:white;font-family:Arial">
        <h1>HideSpec Live Stream</h1>
        <p>
          Resolution: {FRAME_WIDTH}x{FRAME_HEIGHT} |
          YOLO imgsz: {YOLO_IMGSZ} |
          Detect every: {DETECT_EVERY_N_FRAMES} frames |
          JPEG quality: {JPEG_QUALITY}
        </p>
        <p>
          Bad threshold: {BAD_DEFECT_THRESHOLD} |
          Required bad frames: {REQUIRED_CONSECUTIVE_BAD_FRAMES} |
          Missing frames reset: {MISSING_FRAMES_TO_RESET}
        </p>
        <img src="/video_feed" width="900" style="max-width:100%;height:auto;border:1px solid #333;" />
      </body>
    </html>
    """


if __name__ == "__main__":
    print("Video stream: http://0.0.0.0:5001/video_feed")
    print("Stream status: http://0.0.0.0:5001/api/stream/status")
    print("Snapshot: http://0.0.0.0:5001/api/stream/snapshot")
    print(f"Arduino connected: {arduino_connected}")
    app.run(host="0.0.0.0", port=5001, threaded=True, debug=False)