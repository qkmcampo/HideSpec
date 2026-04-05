from flask import Flask, Response, jsonify
from ultralytics import YOLO
from picamera2 import Picamera2
import cv2
import time
import threading
import requests
from pathlib import Path
from datetime import datetime

app = Flask(__name__)

print("=" * 55)
print("HIDESPEC - EVENT CAPTURE CAMERA STREAM SERVER")
print("YOLOv8n Detection with Pi Camera Module 3")
print("=" * 55)

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
# INSPECTION EVENT SETTINGS
# ============================================
VALID_DEFECT_CLASSES = {"color_defect", "hole", "fold"}

# End the inspection event after this many seconds without seeing a valid defect
HIDE_END_TIMEOUT_SECONDS = 1.5

# Save captured image for the event
SAVE_CAPTURE_IMAGE = True

BASE_DIR = Path(__file__).resolve().parent
CAPTURES_DIR = BASE_DIR / "captures"
CAPTURES_DIR.mkdir(parents=True, exist_ok=True)

print("\nLoading YOLO model...")
model = YOLO("best.pt")
print("Model loaded: best.pt")
print(f"Classes: {model.names}")

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

last_raw_frame = None
last_annotated = None
last_detections = []
frame_counter = 0

last_inference_ms = 0.0
last_encode_ms = 0.0
stream_fps = 0.0
last_stream_time = time.time()

# Inspection event state
inspection_active = False
inspection_start_time = None
last_defect_seen_time = None
current_hide_id = None
current_event_detections = {}
current_event_best_frame = None
current_event_best_score = 0.0

state_lock = threading.Lock()


def make_hide_id():
    return f"HIDE-{datetime.now().strftime('%Y%m%d-%H%M%S')}"


def filter_valid_detections(detections):
    return [d for d in detections if d["type"] in VALID_DEFECT_CLASSES]


def merge_event_detections(existing_map, detections):
    """
    Keep only the highest-confidence detection per defect class
    for one inspection event.
    """
    for d in detections:
        defect_type = d["type"]
        if defect_type not in existing_map:
            existing_map[defect_type] = d
        else:
            if d["confidence"] > existing_map[defect_type]["confidence"]:
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


def finalize_inspection_event():
    global inspection_active, inspection_start_time, last_defect_seen_time
    global current_hide_id, current_event_detections
    global current_event_best_frame, current_event_best_score

    if not inspection_active:
        return

    defects = list(current_event_detections.values())
    classification = "Good" if len(defects) == 0 else "Bad"

    snapshot_path = None
    if SAVE_CAPTURE_IMAGE and current_event_best_frame is not None:
        snapshot_path = save_capture_image(current_event_best_frame, current_hide_id)

    send_inspection_to_api(
        hide_id=current_hide_id,
        defects=defects,
        snapshot_path=snapshot_path
    )

    print(f"[INSPECTION] Finalized {current_hide_id} -> {classification} ({len(defects)} defects)")

    inspection_active = False
    inspection_start_time = None
    last_defect_seen_time = None
    current_hide_id = None
    current_event_detections = {}
    current_event_best_frame = None
    current_event_best_score = 0.0


def update_inspection_event(frame_rgb, detections):
    global inspection_active, inspection_start_time, last_defect_seen_time
    global current_hide_id, current_event_detections
    global current_event_best_frame, current_event_best_score

    valid_detections = filter_valid_detections(detections)
    now = time.time()

    # If a valid defect appears, start or update the event
    if valid_detections:
        if not inspection_active:
            inspection_active = True
            inspection_start_time = now
            current_hide_id = make_hide_id()
            current_event_detections = {}
            current_event_best_frame = frame_rgb.copy()
            current_event_best_score = max(d["confidence"] for d in valid_detections)
            print(f"[INSPECTION] Started {current_hide_id}")

        last_defect_seen_time = now
        merge_event_detections(current_event_detections, valid_detections)

        best_conf = max(d["confidence"] for d in valid_detections)
        if best_conf > current_event_best_score:
            current_event_best_score = best_conf
            current_event_best_frame = frame_rgb.copy()

        return

    # If no valid defect is seen for some time, end the event
    if inspection_active and last_defect_seen_time is not None:
        if now - last_defect_seen_time >= HIDE_END_TIMEOUT_SECONDS:
            finalize_inspection_event()


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
            detections.append({
                "type": label,
                "label": label,
                "confidence": conf,
            })

    last_detections = detections
    return annotated, detections


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
                update_inspection_event(frame, detections)

                with state_lock:
                    last_annotated = annotated
            else:
                with state_lock:
                    if last_annotated is None:
                        last_annotated = frame.copy()

            with state_lock:
                frame_to_send = last_annotated.copy()

            frame_bgr = cv2.cvtColor(frame_to_send, cv2.COLOR_RGB2BGR)

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
                b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
            )

            loop_elapsed = time.time() - loop_start
            sleep_time = FRAME_DELAY - loop_elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        except Exception as e:
            print(f"Stream error: {e}")
            time.sleep(0.05)


@app.route("/video_feed")
def video_feed():
    return Response(
        mjpeg_generator(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


@app.route("/api/stream/status")
def stream_status():
    return jsonify({
        "status": "running",
        "resolution": f"{FRAME_WIDTH}x{FRAME_HEIGHT}",
        "detections": last_detections,
        "inspection_event": {
            "active": inspection_active,
            "current_hide_id": current_hide_id,
            "collected_defects": list(current_event_detections.values()),
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
          Inspection event timeout: {HIDE_END_TIMEOUT_SECONDS}s
        </p>
        <img src="/video_feed" width="900" style="max-width:100%;height:auto;border:1px solid #333;" />
      </body>
    </html>
    """


if __name__ == "__main__":
    print("Video stream: http://0.0.0.0:5001/video_feed")
    print("Stream status: http://0.0.0.0:5001/api/stream/status")
    print("Snapshot: http://0.0.0.0:5001/api/stream/snapshot")
    print("\nEvent-capture settings:")
    print(f"- Resolution: {FRAME_WIDTH}x{FRAME_HEIGHT}")
    print(f"- YOLO imgsz: {YOLO_IMGSZ}")
    print(f"- Detect every: {DETECT_EVERY_N_FRAMES} frames")
    print(f"- JPEG quality: {JPEG_QUALITY}")
    print(f"- Target FPS: {TARGET_FPS}")
    print(f"- Valid defect classes: {VALID_DEFECT_CLASSES}")
    print(f"- Inspection timeout: {HIDE_END_TIMEOUT_SECONDS}s")
    print(f"- API: {INSPECTIONS_API_URL}\n")

    app.run(host="0.0.0.0", port=5001, threaded=True, debug=False)